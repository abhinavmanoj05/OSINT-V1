"""
Application configuration management
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Crime Analysis Mapper"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-this-in-production"
    
    # Neo4j Graph Database
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # PostgreSQL / SQLite
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "crime_analysis"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    USE_SQLITE: bool = True  # Default to SQLite for local setup
    
    @property
    def DATABASE_URL(self) -> str:
        if self.USE_SQLITE:
            import os
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            db_path = os.path.join(root_dir, "data", "crime_analysis.db").replace("\\", "/")
            return f"sqlite+aiosqlite:///{db_path}"
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # SearXNG
    SEARXNG_URL: str = "http://localhost:8080"
    
    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "evidence"
    MINIO_SECURE: bool = False
    
    # Security
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Frontend
    STREAMLIT_SERVER_PORT: int = 8501
    STREAMLIT_SERVER_ADDRESS: str = "0.0.0.0"

    # -----------------------------------------------------------------------
    # LLM Comprehension Layer — defaults to local Ollama (no API keys needed)
    # -----------------------------------------------------------------------
    # Provider: ollama | none
    # ollama = local Ollama server, zero-cost, no internet needed
    # none   = disable LLM, use regex-only extraction
    LLM_PROVIDER: str = "ollama"

    # --- Ollama (PRIMARY — local, offline, free) ---
    # Install: https://ollama.ai  |  Pull model: ollama pull qwen2.5:3b
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"  # 3b+ recommended for JSON reliability

    # --- Optional cloud providers (set LLM_PROVIDER to use) ---
    # LLM_PROVIDER=gemini  → needs GEMINI_API_KEY
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    # LLM_PROVIDER=openai  → needs OPENAI_API_KEY (also works with Groq, LM Studio)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    # -----------------------------------------------------------------------
    # MCP Tool Settings
    # -----------------------------------------------------------------------
    # SpiderFoot is very slow (5-30min); set to True only for formal investigations
    USE_SPIDERFOOT: bool = False
    # Paths for tools not in PATH
    SPIDERFOOT_PATH: str = ""
    BLACKBIRD_PATH: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env without failing


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()