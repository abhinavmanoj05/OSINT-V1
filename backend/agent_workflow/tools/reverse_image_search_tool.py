import os
import json
import requests
from langchain.tools import tool

@tool
def reverse_image_search(image_url: str) -> str:
    """
    Takes an image URL and performs a reverse image search across the web 
    to find matching profiles (e.g., dating sites, forums, alt-accounts).
    Uses SerpAPI Google Lens (requires SERPAPI_API_KEY).
    """
    api_key = os.environ.get("SERPAPI_API_KEY")
    
    if not api_key:
        # Simulating a successful response with mock data if no key is provided
        mock_results = {
            "target_image": image_url,
            "status": "mocked",
            "matches": [
                {
                    "title": "User Profile - Reddit",
                    "link": "https://reddit.com/user/alt_account_123",
                    "source": "Reddit",
                    "confidence": "High"
                },
                {
                    "title": "Dating Profile Match",
                    "link": "https://tinder.com/@possible_match",
                    "source": "Tinder",
                    "confidence": "Medium"
                }
            ],
            "note": "SERPAPI_API_KEY not found. Returning mock data."
        }
        return json.dumps(mock_results, indent=2)

    try:
        # Live SerpAPI Call using Google Lens engine
        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": api_key
        }
        response = requests.get("https://serpapi.com/search.json", params=params)
        
        if response.status_code == 200:
            data = response.json()
            matches = []
            
            # Extract visual matches
            visual_matches = data.get("visual_matches", [])
            for i, match in enumerate(visual_matches[:5]):  # Top 5 matches
                matches.append({
                    "title": match.get("title", ""),
                    "link": match.get("link", ""),
                    "source": match.get("source", "Unknown Web Source"),
                    "thumbnail": match.get("thumbnail", ""),
                    "confidence": "High" if i < 2 else "Medium"
                })
                
            return json.dumps({
                "target_image": image_url,
                "status": "success",
                "match_count": len(matches),
                "matches": matches
            }, indent=2)
        else:
            return f"Error from SerpAPI: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"Error executing reverse_image_search for {image_url}: {str(e)}"
