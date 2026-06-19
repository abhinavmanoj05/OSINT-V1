"""
API client for backend communication
"""
import requests
from typing import Optional, Dict, Any
import streamlit as st


class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.token = None
    
    def set_token(self, token: str):
        self.token = token
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def get(self, endpoint: str, params: Optional[Dict] = None, timeout: int = 60) -> Any:
        """GET request"""
        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(),
                params=params,
                timeout=timeout
            )
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.json()
            else:
                return response.text
        except requests.exceptions.RequestException as e:
            st.error(f"API Error: {str(e)}")
            return {"error": str(e)}
    
    def post(self, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None, timeout: int = 180) -> Dict[str, Any]:
        """POST request - timeout defaults to 180s for long-running OSINT operations"""
        try:
            if files:
                # Multipart request for file upload
                # Timeout is 300s: OCR can take ~30s, LLM analysis (Ollama qwen2.5:3b) can take 60-120s
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    headers={"Authorization": self._get_headers().get("Authorization", "")},
                    data=data,
                    files=files,
                    timeout=300
                )
            else:
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    headers=self._get_headers(),
                    json=data,
                    timeout=timeout
                )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            if files:
                st.error("Document upload timed out (300s). The file may be too large or Ollama LLM is slow — try again or reduce file size.")
            else:
                st.error(f"Request timed out after {timeout}s. The OSINT engine is still processing — try again or increase patience.")
            return {"error": "timeout"}
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to backend API. Ensure the FastAPI server is running on port 8000.")
            return {"error": "connection_error"}
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            st.error(f"API Error {e.response.status_code}: {detail or str(e)}")
            return {"error": str(e), "detail": detail}
        except requests.exceptions.RequestException as e:
            st.error(f"API Error: {str(e)}")
            return {"error": str(e)}
    
    def put(self, endpoint: str, data: Dict) -> Dict[str, Any]:
        """PUT request"""
        try:
            response = requests.put(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(),
                json=data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"API Error: {str(e)}")
            return {"error": str(e)}
    
    def delete(self, endpoint: str) -> Dict[str, Any]:
        """DELETE request"""
        try:
            response = requests.delete(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            return {"success": True}
        except requests.exceptions.RequestException as e:
            st.error(f"API Error: {str(e)}")
            return {"error": str(e)}


# Singleton instance
api_client = APIClient()