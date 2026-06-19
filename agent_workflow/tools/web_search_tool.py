from typing import Optional, Dict
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import asyncio

from backend.services.searxng_client import DuckDuckGoClient


class PersonaSearchInput(BaseModel):
    name: Optional[str] = Field(default=None)
    full_name: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    domain: Optional[str] = Field(default=None)
    ip: Optional[str] = Field(default=None)

    institution: Optional[str] = Field(default="")
    location: Optional[str] = Field(default="")
class WebSearchPersonaTool(BaseTool):
    name: str = "web_search_persona"
    description: str = "Perform web search for a persona"
    args_schema: type[BaseModel] = PersonaSearchInput

    def _run(self, **kwargs):
        client = DuckDuckGoClient()
        return asyncio.run(client.search_persona(**kwargs))

web_search_persona = WebSearchPersonaTool()
