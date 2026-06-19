import dns.resolver
from langchain_core.tools import tool

@tool
def dns_lookup(domain: str) -> dict:
    """
    Retrieve DNS records for a domain.

    Input:
    - domain (str): domain name like example.com

    Returns:
    - A dictionary of DNS records (A, AAAA, MX, NS, TXT)

    Use when:
    - user provides a domain
    - need infrastructure or network-level information
    - checking email routing (MX), ownership signals, or hosting data
    """

    records = {}

    for record_type in ["A", "AAAA", "MX", "NS", "TXT"]:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            records[record_type] = [str(r) for r in answers]
        except Exception:
            records[record_type] = []

    return {
        "domain": domain,
        "records": records
    }