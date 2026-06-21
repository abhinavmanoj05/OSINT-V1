"""
SearXNG and DuckDuckGo search clients — DDGS-backed for reliability
"""
import asyncio
import aiohttp
from typing import List, Dict, Optional
from dataclasses import dataclass

from backend.core.config import settings
from functools import wraps

try:
    from aiocache import cached, Cache
except ImportError:
    class Cache:
        MEMORY = 1

    def cached(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    engine: str = "duckduckgo"
    score: float = 0.0
    published_date: str = ""


class SearxngClient:
    """Self-hosted meta-search client"""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or settings.SEARXNG_URL).rstrip('/')
        self.search_endpoint = f"{self.base_url}/search"

    async def search(self, query: str, categories: Optional[List[str]] = None,
                     engines: Optional[List[str]] = None, pages: int = 1) -> List[SearchResult]:
        results = []
        from backend.core.proxy_config import PROXY
        proxy = PROXY.as_aiohttp_proxy()
        async with aiohttp.ClientSession() as session:
            for page in range(1, pages + 1):
                params = {'q': query, 'format': 'json', 'pageno': page, 'safesearch': '0'}
                if categories:
                    params['categories'] = ','.join(categories)
                if engines:
                    params['engines'] = ','.join(engines)
                try:
                    async with session.get(self.search_endpoint, params=params,
                                           proxy=proxy,
                                           timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 429:
                            print(f"[SearXNG] 429 Rate Limit on page {page}. Renewing Tor identity...")
                            from backend.core.proxy_config import PROXY
                            PROXY.renew_tor_identity()
                            await asyncio.sleep(2)
                            continue
                        if response.status == 200:
                            data = await response.json()
                            for r in data.get('results', []):
                                results.append(SearchResult(
                                    title=r.get('title', ''),
                                    url=r.get('url', ''),
                                    content=r.get('content', ''),
                                    engine=r.get('engine', 'searxng'),
                                    score=r.get('score', 0.0),
                                    published_date=r.get('publishedDate', '')
                                ))
                except Exception as e:
                    print(f"SearXNG search error on page {page}: {e}")
        return results

    async def search_persona(self, **kwargs) -> Dict[str, List[SearchResult]]:
        return await _build_persona_queries(self.search, **kwargs)


class DuckDuckGoClient:
    """
    Search client using the duckduckgo-search library (DDGS v7+).
    Falls back to LangChain DuckDuckGoSearchResults if DDGS is rate-limited.
    """

    def _ddgs_search_sync(self, query: str, max_results: int, retries: int = 3) -> list:
        """Synchronous DDGS call using core proxy config, then LangChain DDG fallback on rate limit."""
        try:
            from ddgs import DDGS
            from ddgs.exceptions import DDGSException
            from backend.core.proxy_config import PROXY
            import time

            for attempt in range(retries + 1):
                proxy = PROXY.as_aiohttp_proxy()
                try:
                    proxy_kwargs = {"proxy": proxy} if proxy else {}
                    
                    with DDGS(**proxy_kwargs) as ddgs:
                        results = list(ddgs.text(query, max_results=max_results))
                        return results
                except DDGSException as e:
                    if ('202' in str(e) or 'Ratelimit' in str(e) or 'timeout' in str(e).lower() or 'proxy' in str(e).lower()) and attempt < retries:
                        print(f"[DDGS] Rate limited/Failed on proxy '{proxy}', retrying...")
                        try:
                            from backend.core.proxy_config import PROXY
                            PROXY.renew_tor_identity()
                        except Exception:
                            pass
                        time.sleep(2)
                        continue
                    
                    # Rate limit exhausted after retries — fall through to LangChain
                    print(f"[DDGS] Exhausted for '{query[:60]}'. Trying LangChain DDG...")
                    return self._langchain_ddg_search_sync(query, max_results)
                except Exception as e:
                    if attempt < retries:
                        time.sleep(1)
                        continue
                    print(f"[DDGS] search error for '{query[:60]}': {e}")
                    return []
        except ImportError:
            print("[DDGS] ddgs not installed. Trying LangChain DDG...")
            return self._langchain_ddg_search_sync(query, max_results)
        return []

    def _langchain_ddg_search_sync(self, query: str, max_results: int = 10) -> list:
        """
        LangChain DuckDuckGoSearchResults fallback.
        Uses the 'ddgs' library under the hood (different request path,
        more resilient to rate limits). Returns DDGS-compatible dicts.
        """
        from backend.core.proxy_config import PROXY
        import os
        proxy_env = PROXY.as_env_vars()
        for k, v in proxy_env.items():
            os.environ[k] = v
            
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from langchain_community.tools import DuckDuckGoSearchResults
                tool = DuckDuckGoSearchResults(num_results=max_results, output_format="list")
                raw = tool.run(query)
            if not isinstance(raw, list):
                import ast
                try:
                    raw = ast.literal_eval(raw)
                except Exception:
                    raw = []
            results = []
            for r in raw:
                if isinstance(r, dict):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("link", r.get("url", "")),
                        "body": r.get("snippet", r.get("body", "")),
                    })
            print(f"[LangChain-DDG] {len(results)} results for '{query[:60]}'")
            return results
        except Exception as e:
            print(f"[LangChain-DDG] fallback failed for '{query[:60]}': {e}")
            return []

    @cached(ttl=3600, cache=Cache.MEMORY)
    async def search(self, query: str, max_results: int = 20) -> List[SearchResult]:
        import random
        try:
            loop = asyncio.get_running_loop()
            # Random jitter to stagger concurrent persona queries
            await asyncio.sleep(random.uniform(0.1, 0.4))
            raw = await loop.run_in_executor(None, self._ddgs_search_sync, query, max_results)
            clean_results = []
            for r in raw:
                url = r.get('href', r.get('url', ''))
                if not url:
                    continue
                # Skip junk pages that DDG sometimes surfaces
                junk_paths = ['/login', '/signup', '/recover', '/password', '/captcha', '/accounts/login', 'auth/login', 'signin']
                if any(junk in url.lower() for junk in junk_paths):
                    continue
                    
                clean_results.append(SearchResult(
                    title=r.get('title', ''),
                    url=url,
                    content=r.get('body', r.get('content', '')),
                    engine='duckduckgo',
                    published_date=r.get('published', '')
                ))
            return clean_results
        except Exception as e:
            print(f"[DDGS] async search error: {e}")
            return []

    async def search_persona(self, **kwargs) -> Dict[str, List[SearchResult]]:
        return await _build_persona_queries(self.search, **kwargs)



async def _build_persona_queries(search_fn, **kwargs) -> Dict[str, List[SearchResult]]:
    """
    Shared persona search logic for both SearXNG and DDGS clients.
    Builds targeted, context-aware OSINT queries for individual profiling.
    """
    # Resolve primary target identifier
    target = (
        kwargs.get('name') or kwargs.get('full_name') or
        kwargs.get('username') or kwargs.get('email') or
        kwargs.get('phone') or kwargs.get('domain') or
        kwargs.get('ip') or ''
    )
    if not target:
        return {}

    # Optional context that narrows results to a specific individual
    institution = (kwargs.get('institution') or '').strip()
    location = (kwargs.get('location') or '').strip()

    # Build context suffix for queries that benefit from narrowing
    ctx = ''
    if institution:
        ctx += f' "{institution}"'
    if location:
        ctx += f' "{location}"'

    # Quoted name for exact-match queries (critical for common names)
    q = f'"{target}"'

    queries = {
        # Social profiles — avoid site: operator (rate-limited); use platform name as keyword
        'social':       f'{q} instagram bio OR twitter profile OR facebook',
        # LinkedIn specifically — snippet often has name + headline + location
        'professional': f'{q} linkedin profile{ctx}',
        # GitHub, GitLab, Stack Overflow
        'dev':          f'{q} github OR gitlab OR stackoverflow',
        # News, blogs, interviews — use context to disambiguate common names
        'news_context': f'{q}{ctx} news OR interview OR article OR blog',
        # Breach/leak databases
        'breaches':     f'{q} breach OR leak OR pastebin OR "data exposed"',
        # PDFs from official sources — admission lists, results, directories
        'documents':    f'{q}{ctx} filetype:pdf OR admission OR enrollment OR result OR directory',
        # Academic profile pages, college websites
        'academic':     f'{q}{ctx} college OR university OR student OR department OR graduation',
        # Contact/identity info
        'identity':     f'{q}{ctx} phone OR email OR contact OR address OR whatsapp',
        # Government/official records
        'government':   f'{q} site:gov.in OR site:nic.in OR site:ac.in',
    }

    # If institution given, add a direct institution-site search
    if institution:
        # Derive domain hint from institution name (e.g. "Marian Engineering" -> "marian")
        inst_slug = institution.lower().split()[0]
        queries['institution_site'] = f'"{target}" site:{inst_slug}.ac.in OR "{target}" "{institution}"'

    sem = asyncio.Semaphore(2)

    async def throttled_search(key, query):
        async with sem:
            try:
                res = await search_fn(query, max_results=10)
                await asyncio.sleep(2.5)
                return key, res
            except Exception as e:
                print(f"[DDGS] Error on '{key}' search: {e}")
                return key, []

    tasks = [throttled_search(k, v) for k, v in queries.items()]
    completed = await asyncio.gather(*tasks)
    return {key: res for key, res in completed if res}