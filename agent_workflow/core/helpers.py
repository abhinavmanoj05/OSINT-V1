import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor
from tools.profile_scraper import scrape_profile

def resolve_gravatar_profile(email: str) -> dict | None:
    print(f"  -> [Orchestrator] Attempting to query Gravatar profile for email '{email}'...")
    email_hash = hashlib.md5(email.strip().lower().encode('utf-8')).hexdigest()
    url = f"https://en.gravatar.com/{email_hash}.json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            entry = data.get("entry", [{}])[0]
            profile = {
                "username": entry.get("preferredUsername"),
                "display_name": entry.get("displayName"),
                "about_me": entry.get("aboutMe"),
                "urls": [u.get("value") for u in entry.get("urls", []) if u.get("value")]
            }
            print(f"  -> [Orchestrator] Resolved Gravatar profile details: {profile['display_name']} ({profile['username']})")
            return profile
    except Exception:
        pass
    return None

def resolve_github_url_from_email(email: str) -> str | None:
    print(f"  -> [Orchestrator] Attempting to resolve GitHub profile for email '{email}' via commit history...")
    url = f"https://api.github.com/search/commits?q=author-email:{email}"
    headers = {"Accept": "application/vnd.github.cloak-preview"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("total_count", 0) > 0:
                item = data["items"][0]
                author = item.get("author")
                if author and "html_url" in author:
                    profile_url = author["html_url"]
                    print(f"  -> [Orchestrator] Resolved GitHub profile: {profile_url}")
                    return profile_url
    except Exception as e:
        print(f"  -> [Orchestrator] GitHub resolution error: {e}")
    return None

def scrape_urls_concurrently(urls: list) -> list:
    results = []
    if not urls:
        return results
    
    max_workers = min(len(urls), 5)
    print(f"  -> [Worker] Scraping {len(urls)} profile(s) concurrently with {max_workers} workers...")
    
    def worker(url):
        print(f"  -> [Worker] Automatically scraping discovered profile: {url}...")
        try:
            scrape_res = scrape_profile.invoke(url)
            return {
                "url": url,
                "output": scrape_res
            }
        except Exception as e:
            return {
                "url": url,
                "error": str(e)
            }
            
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, url) for url in urls]
        for future in futures:
            results.append(future.result())
            
    return results
