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


# Backward-compatible global instance
PROXY = ProxyConfig