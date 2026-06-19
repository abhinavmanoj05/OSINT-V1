class Settings:
    # ... existing settings ...
    
    # Proxy Configuration
    USE_TOR_PROXY: bool = True
    TOR_PROXY_URL: str = "socks5h://127.0.0.1:9050"
    HTTP_PROXY_URL: Optional[str] = None  # Fallback if not using Tor