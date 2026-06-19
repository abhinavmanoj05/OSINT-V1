from typing import Optional, Dict
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import asyncio

from backend.search.search_client import DuckDuckGoClient


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