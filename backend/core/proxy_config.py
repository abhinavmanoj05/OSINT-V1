from typing import Optional, Dict
from backend.core.config import settings


class ProxyConfig:
    """Central proxy configuration for the entire OSINT engine."""
    
    @staticmethod
    def _get_proxy_url() -> Optional[str]:
        """Get active proxy URL from settings."""
        if getattr(settings, "USE_TOR_PROXY", False) and getattr(settings, "TOR_PROXY_URL", None):
            return getattr(settings, "TOR_PROXY_URL", None)
        return getattr(settings, "HTTP_PROXY_URL", None)

    @classmethod
    def as_requests_dict(cls) -> Dict[str, str]:
        """For requests library."""
        proxy = cls._get_proxy_url()
        if proxy:
            return {"http": proxy, "https": proxy}
        return {}

    @classmethod
    def as_aiohttp_proxy(cls) -> Optional[str]:
        """For aiohttp - returns single proxy URL."""
        return cls._get_proxy_url()

    @classmethod
    def as_urllib_dict(cls) -> Dict[str, str]:
        """For urllib.request."""
        proxy = cls._get_proxy_url()
        if proxy:
            return {"http": proxy, "https": proxy}
        return {}

    @classmethod
    def as_env_vars(cls) -> Dict[str, str]:
        """Environment variables for subprocess tools."""
        env = {}
        proxy = cls._get_proxy_url()
        if proxy:
            if "socks" in proxy.lower():
                env["SOCKS_PROXY"] = proxy
                env["ALL_PROXY"] = proxy
            else:
                env["HTTP_PROXY"] = proxy
                env["HTTPS_PROXY"] = proxy
        return env

    _last_tor_renew = 0.0

    @classmethod
    def renew_tor_identity(cls, port: int = 9051, password: Optional[str] = None) -> bool:
        """
        Force Tor to establish a new circuit / IP address.
        Requires the Tor Control Port (default 9051) to be exposed.
        """
        import time
        now = time.time()
        if now - cls._last_tor_renew < 10.0:
            print(f"[Tor] Skipping renewal (cooldown active: {10.0 - (now - cls._last_tor_renew):.1f}s remaining).")
            return True
            
        try:
            from stem import Signal
            from stem.control import Controller
            
            with Controller.from_port(port=port) as controller:
                controller.authenticate(password=password)
                controller.signal(Signal.NEWNYM)
            cls._last_tor_renew = time.time()
            print("[Tor] Successfully requested a new circuit/identity.")
            return True
        except Exception as e:
            print(f"[Tor] Failed to renew identity: {e}")
            return False


# Backward-compatible global instance
PROXY = ProxyConfig