import subprocess
from langchain_core.tools import tool

@tool
def email_osint(email: str):
    """
    Run OSINT enumeration on an email address using Holehe.

    This tool checks whether an email is registered on various online platforms
    by executing the Holehe CLI and parsing its output.

    Input:
    - email (str): target email address (e.g. user@gmail.com)

    Returns:
    - email (str): input email
    - raw (str): partial CLI output (truncated to 3000 characters)
    - error (str, optional): error message if execution fails

    Use when:
    - user provides an email address
    - checking account presence across services
    - performing OSINT email footprinting or breach surface analysis

    Notes:
    - Uses subprocess to call Holehe
    - Output is raw CLI text (not structured per-platform)
    - Limited to 3000 chars to avoid LLM context overflow
    - Requires Holehe installed in system PATH
    """
    try:
        import os
        from backend.core.proxy_config import PROXY
        env = os.environ.copy()
        env.update(PROXY.as_env_vars())
        
        result = subprocess.run(
            ["holehe", email, "--no-color"],
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )

        lines = result.stdout.splitlines()
        registered = []
        rate_limited = []
        not_registered = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("[+]"):
                domain = line[3:].strip()
                if "Email used" not in domain:
                    registered.append(domain)
            elif line.startswith("[x]"):
                domain = line[3:].strip()
                if "Rate limit" not in domain:
                    rate_limited.append(domain)
            elif line.startswith("[-]"):
                domain = line[3:].strip()
                if "Email not used" not in domain:
                    not_registered.append(domain)

        return {
            "email": email,
            "registered": registered,
            "rate_limited": rate_limited,
            "not_registered_count": len(not_registered),
            "registered_count": len(registered),
            "rate_limited_count": len(rate_limited),
        }

    except Exception as e:
        return {
            "email": email,
            "error": str(e),
            "registered": [],
            "rate_limited": []
        }