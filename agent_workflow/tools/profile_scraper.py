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
        resp = curl_requests.get(
            url,
            timeout=15,
            impersonate="chrome110"
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

        return {
            "url": url,
            "status_code": resp.status_code,
            "title": title,
            "h1": h1,
            "description": desc,
            "source": "curl_cffi"
        }

    except Exception as e:
        curl_cffi_error = str(e)
        # Proceed to Playwright fallback

    # --------------------------------
    # 2. PATCHRIGHT (Heavyweight browser-based fallback)
    # --------------------------------
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

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

                return {
                    "url": url,
                    "title": title,
                    "h1": h1,
                    "description": desc,
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