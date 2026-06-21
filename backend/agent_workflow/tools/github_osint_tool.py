import requests
import re
import json
from langchain.tools import tool

@tool
def github_osint(username: str) -> str:
    """
    Extracts deep OSINT data from a GitHub profile including their true git email via patch files, 
    their repositories (to check for leaks like dotfiles), and their developer connections (followers/following).
    """
    base_url = f"https://api.github.com/users/{username}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        user_response = requests.get(base_url, headers=headers)
        if user_response.status_code != 200:
            return f"Error: GitHub user {username} not found or API limit reached."
        
        user_data = user_response.json()
        
        # 1. Fetch Repositories
        repos_url = user_data.get("repos_url")
        repos = requests.get(repos_url, headers=headers).json() if repos_url else []
        repo_names = [r.get("name") for r in repos if isinstance(r, dict)]
        
        # 2. Extract true email via Events and Patches
        events_url = f"https://api.github.com/users/{username}/events/public"
        events = requests.get(events_url, headers=headers).json()
        extracted_email = None
        
        if isinstance(events, list):
            for event in events:
                if event.get("type") == "PushEvent":
                    repo_name = event.get("repo", {}).get("name")
                    commits = event.get("payload", {}).get("commits", [])
                    if commits and repo_name:
                        commit_sha = commits[0].get("sha")
                        # Fetch patch file
                        patch_url = f"https://github.com/{repo_name}/commit/{commit_sha}.patch"
                        patch_resp = requests.get(patch_url)
                        if patch_resp.status_code == 200:
                            match = re.search(r"^From: .* <(.*@.*)>", patch_resp.text, re.MULTILINE)
                            if match:
                                email = match.group(1)
                                if "noreply.github.com" not in email:
                                    extracted_email = email
                                    break
        
        # 3. Connections Mapping
        followers_url = user_data.get("followers_url")
        followers = requests.get(followers_url, headers=headers).json() if followers_url else []
        follower_logins = [f.get("login") for f in followers if isinstance(f, dict)]
        
        following_url = user_data.get("following_url", "").replace("{/other_user}", "")
        following = requests.get(following_url, headers=headers).json() if following_url else []
        following_logins = [f.get("login") for f in following if isinstance(f, dict)]
        
        result = {
            "platform": "github",
            "username": username,
            "name": user_data.get("name"),
            "public_email": user_data.get("email"),
            "extracted_patch_email": extracted_email,
            "location": user_data.get("location"),
            "bio": user_data.get("bio"),
            "company": user_data.get("company"),
            "blog": user_data.get("blog"),
            "public_repos_count": user_data.get("public_repos"),
            "repo_names": repo_names[:10], # Top 10 to avoid bloat
            "followers_count": user_data.get("followers"),
            "followers": follower_logins[:10],
            "following_count": user_data.get("following"),
            "following": following_logins[:10]
        }
        
        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error executing github_osint for {username}: {str(e)}"
