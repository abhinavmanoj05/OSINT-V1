"""
Database connection management
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from neo4j import AsyncGraphDatabase

from backend.core.config import settings

# PostgreSQL setup
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    poolclass=NullPool,
    future=True
)

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions"""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    import os
    if settings.USE_SQLITE:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        os.makedirs(os.path.join(root_dir, "data"), exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Neo4j setup
class Neo4jConnection:
    _instance = None
    _driver = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jConnection, cls).__new__(cls)
        return cls._instance
    
    async def connect(self):
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
    
    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None
    
    @property
    def driver(self):
        if self._driver is None:
            raise RuntimeError("Neo4j not connected. Call connect() first.")
        return self._driver
    
    async def verify_connectivity(self):
        await self.driver.verify_connectivity()


neo4j_conn = Neo4jConnection()


async def get_neo4j():
    """Dependency for getting Neo4j connection"""
    await neo4j_conn.connect()
    return neo4j_conn.driver


async def close_neo4j():
    """Cleanup Neo4j connection"""
    await neo4j_conn.close()