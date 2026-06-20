from langchain.tools import tool
from curl_cffi import requests as curl_requests
from lxml import html
from urllib.parse import urljoin

@tool
def extract_images(url: str):
    """
    Extract images from a public webpage URL.
    Returns a list of image dictionaries containing the image URL and alt text, 
    structured similarly to how the GitHub API stores image URLs.
    
    Input:
    - url (str): full webpage URL
    
    Returns:
    - List of extracted images with 'url' and 'alt' keys.
    """
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
        images = []
        
        # 1. Open Graph Image
        og_image = tree.xpath('//meta[@property="og:image"]/@content')
        if og_image:
            images.append({"avatar_url": urljoin(url, og_image[0]), "alt": "Open Graph Image"})
        
        # 2. Twitter Image
        tw_image = tree.xpath('//meta[@name="twitter:image"]/@content')
        if tw_image:
            images.append({"avatar_url": urljoin(url, tw_image[0]), "alt": "Twitter Card Image"})

        # 3. Common avatar classes/ids
        for img in tree.xpath('//img[contains(translate(@class, "AVATARPROFILE", "avatarprofile"), "avatar") or contains(translate(@class, "AVATARPROFILE", "avatarprofile"), "profile")]'):
            src = img.get('src')
            if src and not src.startswith('data:'):
                images.append({"avatar_url": urljoin(url, src), "alt": img.get('alt', 'Profile Avatar').strip()})
        
        # 4. Fallback to all images if none found (limit to first 10 to avoid bloat)
        if not images:
            for img in tree.xpath('//img')[:10]:
                src = img.get('src')
                if src and not src.startswith('data:'):
                    images.append({
                        "avatar_url": urljoin(url, src),
                        "alt": img.get('alt', '').strip()
                    })
        
        # Deduplicate by URL
        seen = set()
        unique_images = []
        for img in images:
            if img["avatar_url"] not in seen:
                seen.add(img["avatar_url"])
                unique_images.append(img)
        
        return {
            "source_url": url,
            "images": unique_images,
            "total_extracted": len(unique_images)
        }
    except Exception as e:
        return {
            "source_url": url,
            "error": str(e)
        }
