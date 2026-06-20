from .sherlock_tool import username_osint
from .profile_scraper import scrape_profile
from .holehe_tool import email_osint
from .dns_tool import dns_lookup
from .whois_tool import whois_lookup
from .web_search_tool import web_search_persona
from .image_extraction_tool import extract_images

tool_map = {
    "username_osint": username_osint,
    "scrape_profile": scrape_profile,
    "email_osint": email_osint,
    "dns_lookup": dns_lookup,
    "whois_lookup": whois_lookup,
    "web_search_persona": web_search_persona,
    "extract_images": extract_images
}
