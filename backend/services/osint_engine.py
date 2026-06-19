"""
Unified OSINT Engine — Individual profiling with real correlation and metadata extraction
LLM Comprehension: Ollama (Primary and Default)
Tools: Custom Agent Workflow (Sherlock/Holehe/Scraping)
"""
import asyncio
import json
import os
import re
import tempfile
from backend.core.proxy_config import PROXY
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from backend.services.searxng_client import SearxngClient, DuckDuckGoClient
from backend.core.config import settings

# LLM Comprehension — lazy import to avoid startup failures if packages missing
try:
    from backend.services.llm_comprehension import get_provider_singleton as _get_llm
except ImportError:
    _get_llm = lambda: None  # noqa

# Removed MCP wrappers. Everything goes through agent_workflow now.


@dataclass
class OSINTFinding:
    source: str
    entity_type: str
    entity_value: str
    platform: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = None
    confidence: float = 0.5
    timestamp: str = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Tool wrappers
# ---------------------------------------------------------------------------
class SherlockWrapper:
    def __init__(self, sherlock_path: str = "sherlock"):
        self.sherlock_path = sherlock_path

    async def investigate(self, username: str, timeout: int = 90) -> List[OSINTFinding]:
        findings = []
        cmd = [self.sherlock_path, username, "--timeout", "5"]
        
        # Merge proxy env vars with current environment
        env = os.environ.copy()
        env.update(PROXY.as_env_vars())
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env  # <-- ADD THIS
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            for line in stdout.decode('utf-8', errors='ignore').split('\n'):
                if '[+]' in line:
                    match = re.search(r'\[\+\]\s+(.+?):\s+(http.+)', line)
                    if match:
                        site = match.group(1).strip()
                        url = match.group(2).strip()
                        findings.append(OSINTFinding(
                            source="sherlock", entity_type="username",
                            entity_value=username, platform=site,
                            url=url,
                            confidence=0.9
                        ))
        except asyncio.TimeoutError:
            print(f"Sherlock timeout for {username}")
        except Exception as e:
            print(f"Sherlock error: {e}")
        return findings

class HoleheWrapper:
    async def investigate(self, email: str) -> List[OSINTFinding]:
        findings = []
        env = os.environ.copy()
        env.update(PROXY.as_env_vars())
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "holehe", email,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env  # <-- ADD THIS
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            for line in stdout.decode('utf-8', errors='ignore').split('\n'):
                if '[+]' in line:
                    match = re.search(r'\[\+\]\s+(.+?)\s+', line)
                    if match:
                        findings.append(OSINTFinding(
                            source="holehe", entity_type="email",
                            entity_value=email, platform=match.group(1).strip(),
                            confidence=0.85
                        ))
        except Exception as e:
            print(f"Holehe error: {e}")
        return findings


# ---------------------------------------------------------------------------
# GitHub API client (free, unauthenticated — 60 req/hour)
# ---------------------------------------------------------------------------

class GitHubAPIClient:
    BASE = "https://api.github.com"
    HEADERS = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "OSINT-Analysis-Tool/1.0"
    }

    async def _get(self, path: str, params: dict = None) -> dict:
        import aiohttp
        proxy = PROXY.as_aiohttp_proxy()
        try:
            async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                async with session.get(
                    f"{self.BASE}{path}", 
                    params=params,
                    proxy=proxy,  # <-- ADD THIS
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        return await r.json()
                    print(f"[GitHub API] {path} returned {r.status}")
        except Exception as e:
            print(f"[GitHub API] error: {e}")
        return {}

    async def search_users(self, name: str, limit: int = 5) -> List[dict]:
        data = await self._get("/search/users", {"q": name, "per_page": limit})
        return data.get("items", [])

    async def get_user_profile(self, username: str) -> dict:
        return await self._get(f"/users/{username}")

    async def get_user_repos(self, username: str, limit: int = 5) -> List[dict]:
        data = await self._get(f"/users/{username}/repos", {"per_page": limit, "sort": "updated"})
        return data if isinstance(data, list) else []

    async def profile_name(self, name: str) -> List[dict]:
        """Search GitHub for a real name and return enriched profiles."""
        users = await self.search_users(name, limit=5)
        profiles = []
        for u in users:
            login = u.get("login", "")
            detail = await self.get_user_profile(login)
            repos = await self.get_user_repos(login, limit=3)
            profiles.append({
                "login": login,
                "name": detail.get("name", ""),
                "bio": detail.get("bio", ""),
                "email": detail.get("email", ""),
                "location": detail.get("location", ""),
                "company": detail.get("company", ""),
                "blog": detail.get("blog", ""),
                "followers": detail.get("followers", 0),
                "public_repos": detail.get("public_repos", 0),
                "profile_url": f"https://github.com/{login}",
                "avatar_url": u.get("avatar_url", ""),
                "top_repos": [r.get("full_name", "") for r in repos],
                "created_at": detail.get("created_at", ""),
            })
        return profiles


# ---------------------------------------------------------------------------
# Web scraper with metadata extraction
# ---------------------------------------------------------------------------

_FALLBACK_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]


def _random_ua() -> str:
    import random
    try:
        from fake_useragent import UserAgent
        return UserAgent().random
    except Exception:
        import random
        return random.choice(_FALLBACK_UAS)


class WebScraper:
    def _fetch_sync(self, url: str, timeout: int) -> bytes:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': _random_ua(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        )
        
        # Build opener with proxy
        proxy_dict = PROXY.as_urllib_dict()
        if proxy_dict:
            proxy_handler = urllib.request.ProxyHandler(proxy_dict)
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()
            
        with opener.open(req, timeout=timeout) as res:
            return res.read()

    def _extract_metadata(self, soup) -> dict:
        """Extract structured metadata from BeautifulSoup object."""
        meta = {}

        # Standard meta tags
        for tag in soup.find_all("meta"):
            name = tag.get("name", tag.get("property", "")).lower()
            content = tag.get("content", "")
            if not content:
                continue
            if name in ("og:title", "twitter:title"):
                meta.setdefault("title", content)
            elif name in ("og:description", "twitter:description", "description"):
                meta.setdefault("description", content)
            elif name == "og:image":
                meta.setdefault("image", content)
            elif name in ("og:url", "canonical"):
                meta.setdefault("canonical_url", content)
            elif name == "author":
                meta.setdefault("author", content)
            elif name in ("article:published_time", "date", "publishdate", "pubdate"):
                meta.setdefault("published_date", content)
            elif name == "keywords":
                meta["keywords"] = [k.strip() for k in content.split(",")]

        # <time> elements
        time_tag = soup.find("time")
        if time_tag:
            meta.setdefault("published_date", time_tag.get("datetime", time_tag.get_text(strip=True)))

        # Title tag fallback
        title_tag = soup.find("title")
        if title_tag:
            meta.setdefault("title", title_tag.get_text(strip=True))

        # Schema.org JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                schema_type = data.get("@type", "")
                if "Person" in schema_type:
                    meta["schema_person"] = {
                        "name": data.get("name", ""),
                        "jobTitle": data.get("jobTitle", ""),
                        "email": data.get("email", ""),
                        "telephone": data.get("telephone", ""),
                        "url": data.get("url", ""),
                        "address": str(data.get("address", "")),
                        "affiliation": str(data.get("affiliation", "")),
                        "alumniOf": str(data.get("alumniOf", "")),
                    }
                elif "Article" in schema_type or "NewsArticle" in schema_type:
                    meta.setdefault("published_date", data.get("datePublished", ""))
                    meta.setdefault("author", str(data.get("author", {}).get("name", "")))
            except Exception:
                pass

        return meta

    async def scrape_with_metadata(self, url: str, timeout: int = 15) -> dict:
        """Returns {'text': str, 'metadata': dict}"""
        result = {"text": "", "metadata": {}}
        try:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, self._fetch_sync, url, timeout)
            html = raw.decode('utf-8', errors='ignore')

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            result["metadata"] = self._extract_metadata(soup)

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.extract()
            result["text"] = soup.get_text(separator=' ', strip=True)[:60000]
        except Exception as e:
            print(f"Scrape failed for {url}: {e}")
        return result

    async def scrape(self, url: str, timeout: int = 15) -> str:
        result = await self.scrape_with_metadata(url, timeout)
        return result["text"]

    async def extract_pdf_text(self, url: str, timeout: int = 20) -> str:
        """Download a PDF URL and extract its text."""
        try:
            import io
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, self._fetch_sync, url, timeout)
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(raw))
                return '\n'.join(p.extract_text() or '' for p in reader.pages)[:60000]
            except ImportError:
                pass
            try:
                import pdfminer.high_level
                return pdfminer.high_level.extract_text(io.BytesIO(raw))[:60000]
            except ImportError:
                pass
        except Exception as e:
            print(f"PDF extraction failed for {url}: {e}")
        return ""

# ---------------------------------------------------------------------------
# Main profiler
# ---------------------------------------------------------------------------

PLATFORM_DOMAINS = {
    'instagram.com': 'Instagram',
    'twitter.com': 'Twitter/X',
    'x.com': 'Twitter/X',
    'facebook.com': 'Facebook',
    'linkedin.com': 'LinkedIn',
    'github.com': 'GitHub',
    'gitlab.com': 'GitLab',
    'stackoverflow.com': 'Stack Overflow',
    'youtube.com': 'YouTube',
    'tiktok.com': 'TikTok',
    'reddit.com': 'Reddit',
    'pinterest.com': 'Pinterest',
    'snapchat.com': 'Snapchat',
    'quora.com': 'Quora',
    'medium.com': 'Medium',
}


def _platform_from_url(url: str) -> str:
    for domain, name in PLATFORM_DOMAINS.items():
        if domain in url:
            return name
    return ""


def _extract_handle(url: str) -> str:
    """Extract username/handle from a social profile URL."""
    patterns = [
        r'instagram\.com/([^/?#]+)',
        r'twitter\.com/([^/?#]+)',
        r'x\.com/([^/?#]+)',
        r'github\.com/([^/?#]+)',
        r'linkedin\.com/in/([^/?#]+)',
        r'facebook\.com/([^/?#]+)',
        r'tiktok\.com/@([^/?#]+)',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            handle = m.group(1)
            if handle.lower() not in ('search', 'explore', 'home', 'login', 'signup', 'pub', 'share'):
                return handle
    return ""


class EntityProfiler:
    """Main OSINT orchestrator with LLM comprehension and MCP tool integration."""

    def __init__(self, llm_model: str = None):
        self.llm_model = llm_model
        self.sherlock = SherlockWrapper()
        self.holehe = HoleheWrapper()
        self.github = GitHubAPIClient()
        self.search_client = self._get_search_client()
        self.scraper = WebScraper()
        # MCP tools disabled. Using agent_workflow exclusively.
        # LLM provider (Gemini / OpenAI / Ollama — set LLM_PROVIDER in .env)
        self._llm = None  # lazy-loaded on first use

    def _get_search_client(self):
        try:
            if settings.SEARXNG_URL:
                import urllib.request
                urllib.request.urlopen(f"{settings.SEARXNG_URL}/status", timeout=1)
                return SearxngClient()
        except Exception:
            pass
        return DuckDuckGoClient()

    # LLM property removed; relies 100% on ReAct agent

    async def profile_target(
        self,
        target_type: str,
        target_value: str,
        institution: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Unified profiling with individual-focused search, metadata, and real correlation."""
        start_time = datetime.utcnow()
        text_corpus: List[str] = []
        opsec_warnings: List[str] = []
        recommended_next_steps: List[str] = []
        source_links: List[dict] = []
        github_profiles: List[dict] = []
        page_metadata_store: Dict[str, dict] = {}  # url -> metadata

        text_corpus.append(f"Target: {target_value} ({target_type})")
        if institution:
            text_corpus.append(f"Institution context: {institution}")
        if location:
            text_corpus.append(f"Location context: {location}")

        # --- OpSec checks ---
        if target_type == "ip":
            opsec_warnings.append(f"Direct scanning of IP {target_value} may alert the target. Use passive sources.")
            recommended_next_steps.append("Use Shodan, Censys, or historical DNS lookups passively.")
        elif target_type in ("phone", "email"):
            opsec_warnings.append("Ensure no local investigator metadata leaks during external lookup.")
            recommended_next_steps.append("Check breach databases via localized mirrors.")

        # AgentWorkflow will be called after initial search data is gathered

        # --- GitHub API (name or username) ---
        if target_type in ("name", "username"):
            try:
                github_profiles = await self.github.profile_name(target_value)
                for gp in github_profiles:
                    if gp.get("login"):
                        entry = {
                            "title": f"[GITHUB] {gp['login']}" + (f" ({gp['name']})" if gp.get('name') else ""),
                            "url": gp["profile_url"],
                            "category": "dev",
                            "platform": "GitHub",
                            "snippet": " | ".join(filter(None, [
                                gp.get("bio", ""),
                                gp.get("location", ""),
                                gp.get("company", ""),
                                f"{gp.get('followers',0)} followers",
                                f"{gp.get('public_repos',0)} repos",
                            ])),
                            "engine": "github_api",
                            "metadata": {
                                "email": gp.get("email", ""),
                                "location": gp.get("location", ""),
                                "company": gp.get("company", ""),
                                "blog": gp.get("blog", ""),
                                "avatar_url": gp.get("avatar_url", ""),
                                "created_at": gp.get("created_at", ""),
                            }
                        }
                        source_links.append(entry)
                        corpus_line = f"GitHub profile: {gp['login']} bio={gp.get('bio','')} location={gp.get('location','')} company={gp.get('company','')} email={gp.get('email','')}"
                        text_corpus.append(corpus_line)
            except Exception as e:
                print(f"GitHub API error: {e}")

        # --- Multi-vector DDGS search ---
        print(f"[OSINT] Starting search for {target_type}: {target_value}")
        try:
            search_kwargs = {target_type: target_value, "institution": institution, "location": location}
            if target_type == "name":
                search_kwargs["full_name"] = target_value

            persona_results = await self.search_client.search_persona(**search_kwargs)
            total_hits = sum(len(v) for v in persona_results.values())
            print(f"[OSINT] Persona search: {total_hits} hits across {list(persona_results.keys())}")

            if total_hits == 0:
                print("[OSINT] No persona hits, falling back to broad search.")
                broad = await self.search_client.search(f'"{target_value}"', max_results=15)
                persona_results = {"broad_recon": broad}

            for category, results in persona_results.items():
                for result in results:
                    platform = _platform_from_url(result.url)
                    handle = _extract_handle(result.url)
                    source_links.append({
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.content[:300],
                        "category": category,
                        "platform": platform,
                        "handle": handle,
                        "engine": result.engine,
                        "published_date": getattr(result, 'published_date', ''),
                    })
                    text_corpus.append(f"[{category}] {result.title}: {result.content}")

            # --- Deep scrape with metadata for high-value categories ---
            scrape_categories = {'social', 'dev', 'breaches', 'documents', 'academic',
                                  'government', 'broad_recon', 'news_context', 'identity', 'institution_site'}

            scrape_tasks = []
            scrape_urls = []
            for category, results in persona_results.items():
                if category not in scrape_categories:
                    continue
                for result in results[:2]:
                    if result.url and result.url.startswith('http'):
                        scrape_urls.append((result.url, category))
                        if result.url.lower().endswith('.pdf'):
                            scrape_tasks.append(self.scraper.extract_pdf_text(result.url))
                        else:
                            scrape_tasks.append(self.scraper.scrape_with_metadata(result.url))

            if scrape_tasks:
                scraped = await asyncio.gather(*scrape_tasks, return_exceptions=True)
                for i, sc in enumerate(scraped):
                    url, category = scrape_urls[i]
                    if isinstance(sc, Exception):
                        print(f"Scrape error for {url}: {sc}")
                        continue
                    if isinstance(sc, str):
                        # PDF result
                        if sc:
                            text_corpus.append(sc)
                            _mark_scraped(source_links, url, metadata={})
                    elif isinstance(sc, dict):
                        text = sc.get("text", "")
                        meta = sc.get("metadata", {})
                        if text:
                            print(f"[OSINT] Scraped {len(text)} chars from {url}")
                            text_corpus.append(text)
                        if meta:
                            page_metadata_store[url] = meta
                            _mark_scraped(source_links, url, metadata=meta)
                            # If social profile with Schema.org Person data
                            sp = meta.get("schema_person", {})
                            if sp.get("name"):
                                text_corpus.append(
                                    f"Schema.org Person: name={sp['name']} job={sp.get('jobTitle','')} "
                                    f"email={sp.get('email','')} phone={sp.get('telephone','')} "
                                    f"affiliation={sp.get('affiliation','')} alumniOf={sp.get('alumniOf','')}"
                                )

        except Exception as e:
            print(f"[ERROR] Multi-vector search failed: {e}")
            import traceback; traceback.print_exc()

        # --- Internal document cross-reference ---
        try:
            from backend.core.database import async_session_maker
            from backend.models.case import EvidenceFile
            from sqlalchemy import select
            async with async_session_maker() as db:
                stmt = select(EvidenceFile).where(EvidenceFile.extracted_text.ilike(f"%{target_value}%"))
                res = await db.execute(stmt)
                for doc in res.scalars().all():
                    source_links.append({
                        "title": f"[INTERNAL] {doc.original_filename}",
                        "url": f"#doc-{doc.id}",
                        "category": "internal",
                        "confidence": 1.0,
                        "engine": "internal_db",
                    })
                    if doc.extracted_text:
                        text_corpus.append(doc.extracted_text)
        except Exception as e:
            print(f"Internal OCR cross-link failure: {e}")

        corpus_text = " ".join(text_corpus)
        
        # --- Transfer control to agent_workflow ReAct loop ---
        import sys
        import os
        workflow_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agent_workflow"))
        if workflow_path not in sys.path:
            sys.path.insert(0, workflow_path)
            
        agent_json_data = {}
        confirmed_entities = []
        possible_entities = []
        agent_summary_text = ""
        try:
            from agent_workflow.api import execute_query
            print(f"[AgentWorkflow] Transferring control to ReAct Agent with search context...")
            
            enhanced_context = f"Target Type: {target_type}\n"
            if institution: enhanced_context += f"Institution: {institution}\n"
            if location: enhanced_context += f"Location: {location}\n"
            enhanced_context += f"\nBackend Corpus:\n{corpus_text[:8000]}"
            
            step_report, session_history = execute_query(
                query=target_value, 
                context=enhanced_context
            )
            
            # Incorporate agent's deep reasoning
            if step_report:
                agent_json_data = step_report.get("agent_structured_data", {})
                confirmed_entities = step_report.get("confirmed_entities", [])
                possible_entities = step_report.get("possible_entities", [])
                
                # Merge opsec and next steps early
                opsec_warnings.extend(step_report.get("opsec_warnings", []))
                recommended_next_steps.extend(step_report.get("recommended_next_steps", []))
                
                # Strip the JSON payload from the raw summary so the secondary LLM doesn't get confused
                raw_summary = step_report.get('summary', '')
                import re
                clean_summary = re.sub(r'(\{.*\})', '', raw_summary, flags=re.DOTALL).strip()
                if clean_summary:
                    agent_summary_text = clean_summary
                    text_corpus.append(f"\n[Agent Investigation Summary]\n{clean_summary}")
                
            # Log the agent's tool outputs
            for act in session_history:
                if isinstance(act, dict) and act.get("action") == "tool_execution":
                    tool = act.get("tool")
                    for out in act.get("outputs", []):
                        val = out.get("output")
                        if isinstance(val, str) and len(val) > 0:
                            text_corpus.append(f"[{tool} Agent Data]: {val[:500]}")
                elif isinstance(act, str):
                    text_corpus.append(f"[Agent Action]: {act}")
                    
            if step_report and step_report.get("raw_data"):
                for raw_out in step_report.get("raw_data", []):
                    text_corpus.append(f"[Agent Raw Output]:\n{raw_out}")
                            
            # Re-compile corpus text with agent's findings for the Entity Extraction phase
            corpus_text = " ".join(text_corpus)
            
        except Exception as e:
            print(f"[AgentWorkflow] ReAct Agent integration failed: {e}")

        # --- Entity extraction: Strict Regex baseline ---
        # The deep LLM extraction is now fully handled by the ReAct Agent in agent_workflow.
        extracted = self._extract_entities(
            corpus_text, target_type, target_value, institution, location
        )

        # --- Inject GitHub data into extracted entities ---
        for gp in github_profiles:
            if gp.get("email"):
                extracted["email"].append(gp["email"])
            if gp.get("location"):
                extracted["locations"].append(gp["location"])
            if gp.get("login"):
                extracted["username"].append(gp["login"])
            if gp.get("company"):
                extracted["affiliations"].append(gp["company"])
                
            pass



        # Deduplicate
        for k in extracted:
            if isinstance(extracted[k], list):
                extracted[k] = list(dict.fromkeys([str(v) for v in extracted[k] if v]))

        # --- Threat assessment ---
        threat = self._evaluate_threat_profile(extracted, text_corpus)

        # --- LLM Profile Comprehension (behavioral profile + narrative) ---
        # REMOVED: Outer summarization has been disabled. We now rely exclusively on the ReAct agent's summary.
        llm_profile = {}

        # --- Real correlation ---
        correlated = self._correlate_profiles(extracted, source_links, target_type, target_value, threat)

        # Build a unified summary string for reports
        # Use key_findings but also extract from narrative fields if the 0.5b model put text there
        all_key_findings = extracted.get("key_findings", []) + llm_profile.get("key_findings", [])
        
        # Deduplicate and limit to top 10
        unique_findings = []
        seen = set()
        for f in all_key_findings:
            if not f or not isinstance(f, str): continue
            clean_f = f.strip().strip("•-* ")
            if clean_f and clean_f.lower() not in seen:
                unique_findings.append(clean_f)
                seen.add(clean_f.lower())
        
        unique_findings = unique_findings[:12]
        
        # Prefer the ReAct agent's narrative summary; fallback to bullet points if missing
        if agent_summary_text:
            unified_summary = agent_summary_text
        else:
            unified_summary = "\n".join([f"• {f}" for f in unique_findings])

        from datetime import timezone
        processing_time = (datetime.now(timezone.utc).replace(tzinfo=None) - start_time).total_seconds()

        return {
            "summary": unified_summary or "Intelligence analysis complete (manual review recommended).",
            "extracted_entities": extracted,
            "correlated_profiles": correlated,
            "opsec_warnings": list(dict.fromkeys(opsec_warnings)),
            "recommended_next_steps": list(dict.fromkeys(recommended_next_steps)),
            "source_links": source_links,
            "threat_assessment": threat,
            "github_profiles": github_profiles,
            "llm_profile": llm_profile,
            "agent_structured_data": agent_json_data,
            "confirmed_entities": confirmed_entities,
            "possible_entities": possible_entities,
            "text_corpus": corpus_text,
            "metadata": {
                "processing_time": processing_time,
                "corpus_size": len(corpus_text),
                "target_type": target_type,
                "target_value": target_value,
                "institution": institution,
                "location": location,
                "source_count": len(source_links),
                "mcp_findings_count": 0,
                "llm_provider": "ReAct Agent Workflow",
                "llm_enabled": True,
                "ollama_mcp_enabled": False,
                "ollama_model": "none",
            }
        }


    # (LLM extraction method removed)

    def _build_tool_summary(self, source_links) -> str:
        """Build a concise text summary of what tools found for LLM comprehension."""
        parts = []
        social_links = [sl for sl in source_links if sl.get("category") == "social"]
        if social_links:
            parts.append(f"{len(social_links)} social media profile links discovered.")
        return " ".join(parts)

    # -----------------------------------------------------------------------
    def _evaluate_threat_profile(self, extracted: Dict, text_corpus: List[str]) -> Dict:
        risk = 0.0
        indicators = []
        corpus = " ".join(text_corpus).lower()

        WEIGHTS = {
            "dark_web": 0.45, "anonymity": 0.30, "malicious_context": 0.35,
            "aliases": 0.15, "financial_exposure": 0.20, "official_flag": -0.15
        }

        if any(kw in corpus for kw in ['breach', 'leak', 'pastebin', 'exposed', 'dump', 'hacked', 'combo list']):
            risk += WEIGHTS["dark_web"]
            indicators.append("Identity observed in public data breach or leak repository.")

        if any(kw in corpus for kw in ['vpn', 'proxy', 'tor', 'onion', 'socks5', 'anonymizer']):
            risk += WEIGHTS["anonymity"]
            indicators.append("Subject may be using anonymization tools (VPN/Tor/Proxy).")

        if any(kw in corpus for kw in ['scammer', 'fraud', 'phishing', 'threat actor', 'malware', 'suspicious']):
            risk += WEIGHTS["malicious_context"]
            indicators.append("Keyword correlation with fraud, phishing, or threat actor activity.")

        usernames = [u for u in extracted.get("username", []) if len(u) > 3]
        if len(usernames) >= 3:
            risk += WEIGHTS["aliases"]
            indicators.append(f"Multiple aliases detected across platforms: {len(usernames)} identifiers.")

        if extracted.get("crypto_wallet") or extracted.get("bank_account_id") or extracted.get("upi_id"):
            risk += WEIGHTS["financial_exposure"]
            indicators.append("Financial identifiers (Crypto/Bank/UPI) linked to subject.")

        if any(kw in corpus for kw in ['gov.in', 'nic.in', 'official gazette', 'government of india']):
            risk += WEIGHTS["official_flag"]

        risk = min(max(round(risk, 2), 0.0), 1.0)
        level = "LOW"
        if risk > 0.3: level = "MEDIUM"
        if risk > 0.6: level = "HIGH"
        if risk >= 0.85: level = "CRITICAL"

        return {"score": risk, "level": level, "indicators": indicators}

    def _extract_entities(
        self, text: str, target_type: str, target_value: str,
        institution: str = "", location: str = ""
    ) -> Dict[str, list]:
        extracted = {
            "name": [], "username": [], "aliases": [],
            "bank_account_id": [], "upi_id": [], "crypto_wallet": [],
            "phone_number": [], "email": [], "ip_address": [], "domain": [],
            "device_fingerprint": [], "modus_operandi": [], "active_hours": [],
            "preferred_platforms": [], "locations": [], "flags": [],
            "affiliations": [], "institutions": [], "roll_numbers": [],
            "key_findings": [],
        }

        # Seed with target
        if target_type in extracted:
            extracted[target_type].append(target_value)
        elif target_type == "phone":
            extracted["phone_number"].append(target_value)
        elif target_type in ("name", "full_name"):
            extracted["name"].append(target_value)

        if institution:
            extracted["institutions"].append(institution)
        if location:
            extracted["locations"].append(location)

        # Emails
        extracted["email"].extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))

        # Phone numbers (Indian 10-digit starting with 6-9, OR international requiring a + sign)
        extracted["phone_number"].extend(re.findall(r'(?<!\d)(?:[6-9]\d{9}|\+[1-9]\d{9,14})(?!\d)', text))

        # UPI IDs (separate from emails)
        upis = re.findall(r'[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}', text)
        extracted["upi_id"].extend([u for u in upis if u not in extracted["email"]])

        # IPs (filter out obvious non-IPs)
        ips = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', text)
        extracted["ip_address"].extend([ip for ip in ips if not ip.startswith(('0.', '255.'))])

        # Social handles from URLs
        handles = re.findall(
            r'(?:github\.com|facebook\.com|twitter\.com|x\.com|instagram\.com|'
            r'linkedin\.com/in|tiktok\.com/@?)/([a-zA-Z0-9_.\-]+)',
            text
        )
        bad = {'search', 'explore', 'home', 'login', 'signup', 'pub', 'share', 'p', 'reel', 'stories', 'company', 'jobs', 'about', 'posts', 'github'}
        extracted["username"].extend([h for h in handles if h.lower() not in bad])

        # Platform detection
        for domain, name in PLATFORM_DOMAINS.items():
            if domain in text.lower():
                extracted["preferred_platforms"].append(name)

        # Locations — expanded India-aware list
        loc_pattern = (
            r'\b(India|Kerala|Delhi|Mumbai|Bangalore|Bengaluru|Chennai|Hyderabad|Kolkata|'
            r'Pune|Kochi|Thrissur|Kozhikode|Thiruvananthapuram|Kannur|Malappuram|'
            r'New York|London|Dubai|Singapore|Canada|Australia)\b'
        )
        extracted["locations"].extend(re.findall(loc_pattern, text, re.IGNORECASE))

        # Institutions — College/University/School (Strict Title Case)
        inst_pat = r'\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,3}\s(?:College|University|Institute|School|Academy|Polytechnic|IIT|NIT|AIIMS))\b'
        extracted["institutions"].extend(re.findall(inst_pat, text))

        # Affiliations — Company/Org (Strict Title Case)
        aff_pat = r'\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,3}\s(?:Company|Inc\.|Ltd\.|LLC|Technologies|Solutions|Systems|Pvt\.))\b'
        extracted["affiliations"].extend(re.findall(aff_pat, text))

        # Roll numbers / admission numbers (common Indian college patterns)
        roll_pat = r'\b([A-Z]{2,4}\d{2}[A-Z]{0,3}\d{3,6})\b'
        extracted["roll_numbers"].extend(re.findall(roll_pat, text))

        # Crypto wallets — BTC, ETH
        btc = re.findall(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b', text)
        eth = re.findall(r'\b0x[a-fA-F0-9]{40}\b', text)
        extracted["crypto_wallet"].extend(btc + eth)

        # Deduplicate all lists
        for k in extracted:
            if isinstance(extracted[k], list):
                extracted[k] = list(dict.fromkeys([str(v).strip() for v in extracted[k] if str(v).strip()]))

        return extracted

    def _correlate_profiles(
        self, extracted: Dict, source_links: List[dict],
        target_type: str, target_value: str, threat: Dict
    ) -> List[Dict]:
        correlated = []

        # Group source links by platform
        platform_links: Dict[str, List[dict]] = {}
        for sl in source_links:
            plat = sl.get("platform") or _platform_from_url(sl.get("url", ""))
            if plat:
                platform_links.setdefault(plat, []).append(sl)

        # Platform-specific correlations
        for platform, links in platform_links.items():
            handles = list(dict.fromkeys(
                sl.get("handle", "") or _extract_handle(sl.get("url", ""))
                for sl in links
            ))
            handles = [h for h in handles if h]
            justifications = [f"Found on {platform}: {links[0]['url']}"]
            if handles:
                justifications.append(f"Handle(s): {', '.join(handles[:3])}")
            if len(links) > 1:
                justifications.append(f"{len(links)} references on this platform.")

            correlated.append({
                "profile_id": f"{platform.upper().replace('/', '').replace(' ', '_')}-PROFILE",
                "confidence_score": min(0.60 + len(links) * 0.08, 0.95),
                "justifications": justifications,
                "platform": platform,
                "profile_url": links[0].get("url", ""),
                "handles": handles,
            })

        # Cross-platform identity correlation
        if len(platform_links) > 1:
            correlated.append({
                "profile_id": "CROSS-PLATFORM-IDENTITY",
                "confidence_score": min(0.70 + len(platform_links) * 0.05, 0.99),
                "justifications": [
                    f"Consistent identity found across {len(platform_links)} platforms: "
                    f"{', '.join(platform_links.keys())}"
                ],
                "platforms": list(platform_links.keys()),
            })

        # Official document correlation
        doc_links = [sl for sl in source_links if sl.get("category") in ("documents", "academic", "institution_site")]
        if doc_links:
            correlated.append({
                "profile_id": "OFFICIAL-RECORD-MATCH",
                "confidence_score": 0.90,
                "justifications": [
                    f"Target name appears in {len(doc_links)} official/academic document(s).",
                    *[sl.get("title", "")[:80] for sl in doc_links[:3]],
                ],
                "document_urls": [sl.get("url", "") for sl in doc_links[:5]],
            })

        # Internal evidence match
        internal_links = [sl for sl in source_links if sl.get("category") == "internal"]
        if internal_links:
            correlated.append({
                "profile_id": "INTERNAL-EVIDENCE-MATCH",
                "confidence_score": 1.0,
                "justifications": [f"Target found in {len(internal_links)} uploaded case evidence file(s)."],
                "document_urls": [sl.get("url", "") for sl in internal_links],
            })

        # Email/phone cross-reference
        emails = extracted.get("email", [])
        phones = extracted.get("phone_number", [])
        if emails or phones:
            correlated.append({
                "profile_id": "CONTACT-INFO-EXPOSED",
                "confidence_score": 0.80,
                "justifications": [
                    *(f"Email: {e}" for e in emails[:3]),
                    *(f"Phone: {p}" for p in phones[:3]),
                ],
            })

        # Financial exposure
        if extracted.get("upi_id") or extracted.get("bank_account_id") or extracted.get("crypto_wallet"):
            correlated.append({
                "profile_id": "FINANCIAL-EXPOSURE",
                "confidence_score": 0.88,
                "justifications": ["Financial identifiers (UPI/Bank/Crypto) linked to subject."],
            })

        # Threat actor flag
        if threat.get("level") in ("HIGH", "CRITICAL"):
            correlated.append({
                "profile_id": f"THREAT-ACTOR-{threat['level']}",
                "confidence_score": threat["score"],
                "justifications": threat.get("indicators", []),
            })

        # Sort by confidence score descending (highest confidence first)
        correlated.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)

        return correlated


def _mark_scraped(source_links: List[dict], url: str, metadata: dict):
    """Mark a source link as scraped and attach metadata."""
    for sl in source_links:
        if sl.get("url") == url:
            sl["scraped"] = True
            if metadata:
                # Attach useful metadata fields to the source link
                if metadata.get("published_date"):
                    sl["published_date"] = metadata["published_date"]
                if metadata.get("author"):
                    sl["author"] = metadata["author"]
                if metadata.get("description") and not sl.get("snippet"):
                    sl["snippet"] = metadata["description"][:300]
                if metadata.get("image"):
                    sl["og_image"] = metadata["image"]
            break