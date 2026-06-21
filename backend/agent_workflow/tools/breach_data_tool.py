import json
import requests
import os
from langchain.tools import tool

@tool
def breach_data_search(email: str) -> str:
    """
    Queries breach databases to find if an email has been exposed in known data leaks.
    Returns compromised data classes (e.g., passwords, physical addresses) and breach dates.
    Uses HaveIBeenPwned API (requires HIBP_API_KEY environment variable).
    """
    api_key = os.environ.get("HIBP_API_KEY")
    
    if not api_key:
        # Fallback/stub if no API key is provided
        return json.dumps({
            "email": email,
            "status": "mocked",
            "message": "HIBP_API_KEY not found. Returning mocked breach data for demonstration.",
            "breaches": [
                {
                    "name": "LinkedIn",
                    "domain": "linkedin.com",
                    "breach_date": "2012-05-05",
                    "compromised_data": ["Email addresses", "Passwords"]
                },
                {
                    "name": "Canva",
                    "domain": "canva.com",
                    "breach_date": "2019-05-24",
                    "compromised_data": ["Email addresses", "Geographic locations", "Names", "Passwords", "Usernames"]
                }
            ]
        }, indent=2)

    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
    headers = {
        "hibp-api-key": api_key,
        "user-agent": "OSINT-V1-Agent"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            return json.dumps({"email": email, "status": "clean", "breaches": []})
        elif response.status_code == 200:
            breaches = response.json()
            formatted_breaches = []
            for b in breaches:
                formatted_breaches.append({
                    "name": b.get("Name"),
                    "domain": b.get("Domain"),
                    "breach_date": b.get("BreachDate"),
                    "compromised_data": b.get("DataClasses")
                })
            return json.dumps({
                "email": email, 
                "status": "breached", 
                "breach_count": len(formatted_breaches),
                "breaches": formatted_breaches
            }, indent=2)
        else:
            return f"Error from HIBP API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error executing breach_data_search for {email}: {str(e)}"
