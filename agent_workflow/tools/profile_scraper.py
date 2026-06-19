from langchain.tools import tool
from patchright.sync_api import sync_playwright
from curl_cffi import requests as curl_requests
from lxml import html


@tool
def scrape_profile(url: str):
    """
    Scrape public web page content from a URL.

    Process:
    - Attempts curl_cffi + lxml first for speed and basic anti-bot bypass.
    - Falls back to browser-based scraping using Patchright if blocked or failed.

    Input:
    - url (str): full webpage URL

    Returns:
    - page title, h1 tag, and meta description (if available)

    Use when:
    - user provides a direct URL
    - need to extract visible page metadata
    - enrich OSINT investigation with webpage content
    """
    curl_cffi_error = None

    # --------------------------------
    # 1. CURL_CFFI (Fast, lightweight Chrome impersonation)
    # --------------------------------
    try:
        from backend.core.proxy_config import PROXY
        proxy_url = PROXY._get_proxy_url()
        proxies = {"all": proxy_url} if proxy_url else None

        resp = curl_requests.get(
            url,
            timeout=15,
            impersonate="chrome110",
            proxies=proxies
        )

        resp.raise_for_status()

        tree = html.fromstring(resp.text)

        title = tree.xpath("//title/text()")
        title = title[0].strip() if title else ""

        # Check for Cloudflare/anti-bot challenge pages in title
        if title and any(term in title.lower() for term in ["just a moment", "cloudflare", "attention required", "ddos"]):
            raise ValueError(f"Blocked by Cloudflare challenge (detected in title): {title}")

        h1 = tree.xpath("//h1/text()")
        h1 = h1[0].strip() if h1 else None

        desc = tree.xpath(
            "//meta[@name='description']/@content"
        )
        desc = desc[0].strip() if desc else None

        # Clean scripts and styles to extract visible text
        for element in tree.xpath('//script | //style | //noscript | //meta | //link'):
            if element.getparent() is not None:
                element.getparent().remove(element)
        
        # Extract visible text and truncate to avoid blowing up the LLM context
        body_text = " ".join(tree.text_content().split())[:15000]

        return {
            "url": url,
            "status_code": resp.status_code,
            "title": title,
            "h1": h1,
            "description": desc,
            "content": body_text,
            "source": "curl_cffi"
        }

    except Exception as e:
        curl_cffi_error = str(e)
        # Proceed to Playwright fallback
        if any(err in curl_cffi_error.lower() for err in ["cloudflare", "403", "429", "just a moment"]):
            try:
                from backend.core.proxy_config import PROXY
                PROXY.renew_tor_identity()
                import time
                time.sleep(2)
            except Exception:
                pass

    # --------------------------------
    # 2. PATCHRIGHT (Heavyweight browser-based fallback)
    # --------------------------------
    try:
        import sys
        import asyncio
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass

        with sync_playwright() as p:
            from backend.core.proxy_config import PROXY
            proxy_url = PROXY._get_proxy_url()
            proxy_args = {}
            if proxy_url:
                proxy_args = {"proxy": {"server": proxy_url}}

            browser = p.chromium.launch(headless=True, **proxy_args)

            try:
                page = browser.new_page()

                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=30000
                )

                title = page.title()

                h1 = None
                if page.query_selector("h1"):
                    h1 = page.eval_on_selector(
                        "h1",
                        "el => el.textContent.trim()"
                    )

                desc = page.evaluate("""
                    () => {
                        const meta =
                            document.querySelector(
                                "meta[name='description']"
                            );
                        return meta ? meta.content : null;
                    }
                """)
                
                body_text = page.evaluate("() => document.body ? document.body.innerText.substring(0, 15000) : ''")

                return {
                    "url": url,
                    "title": title,
                    "h1": h1,
                    "description": desc,
                    "content": body_text,
                    "source": "patchright",
                    "curl_cffi_error": curl_cffi_error
                }

            finally:
                browser.close()

    except Exception as e:
        return {
            "url": url,
            "error": str(e),
            "curl_cffi_error": curl_cffi_error
        }