import subprocess
from langchain.tools import tool

@tool
def username_osint(username: str):
    """
    Perform OSINT username enumeration using Sherlock.

    This tool searches for a given username across multiple public websites
    to identify where the username is registered or in use.

    Input:
    - username (str): target username/handle (without quotes or @)

    Returns:
    - username (str): input username
    - results (list): up to 20 discovered profiles containing:
        - site (str): platform name (e.g., GitHub, Reddit, Twitter)
        - url (str): profile URL where username was found
    - count (int): total number of matches found
    - error (str, optional): error message if execution fails

    Use when:
    - user provides a username or online handle
    - mapping digital footprint across platforms
    - linking identities across social/media services

    Notes:
    - Uses Sherlock CLI via subprocess
    - Output is parsed from CLI text
    - Limited to 20 results to avoid large LLM payloads
    - Requires Sherlock installed and accessible in system PATH
    """
    try:
        import os
        from backend.core.proxy_config import PROXY
        env = os.environ.copy()
        env.update(PROXY.as_env_vars())

        result = subprocess.run(
            ["sherlock", username, "--output", os.devnull],
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )

        lines = result.stdout.splitlines()

        found = []
        for line in lines:
            if "[+]" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    found.append({
                        "site": parts[0].replace("[+]", "").strip(),
                        "url": parts[1].strip()
                    })

        return {
            "username": username,
            "results": found[:20],  # LIMIT SIZE
            "count": len(found)
        }

    except Exception as e:
        return {
            "username": username,
            "error": str(e),
            "results": []
        }