import whois
from langchain_core.tools import tool



@tool
def whois_lookup(domain: str) -> dict:
    """
    Retrieve domain registration and ownership details using WHOIS lookup.

    This tool queries WHOIS databases to extract registration metadata
    about a domain name.

    Input:
    - domain (str): target domain (e.g. example.com)

    Returns:
    - domain (str): input domain
    - registrar (str): domain registrar name
    - creation_date (str): domain registration date
    - expiration_date (str): domain expiry date
    - name_servers (list/str): DNS name servers associated with domain
    - emails (list/str): registrant or contact emails (if available)
    - status (str): domain status codes (e.g. active, clientTransferProhibited)
    - error (str, optional): error message if lookup fails

    Use when:
    - user asks who owns a domain
    - investigating domain registration or ownership history
    - correlating infrastructure identity (DNS + ownership data)
    - validating legitimacy or age of a domain

    Notes:
    - Uses python-whois library
    - Data availability depends on registrar privacy protection (WHOIS masking)
    - Some fields may be None depending on domain privacy settings
    """
    try:
        data = whois.whois(domain)

        return {
            "domain": domain,
            "registrar": data.registrar,
            "creation_date": str(data.creation_date),
            "expiration_date": str(data.expiration_date),
            "name_servers": data.name_servers,
            "emails": data.emails,
            "status": data.status,
        }

    except Exception as e:
        return {
            "error": str(e)
        }