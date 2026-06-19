"""
FastAPI application entry point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.database import init_db, close_neo4j, neo4j_conn
from backend.api.routers import cases_router, osint_router, graph_router, documents_router, reports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    try:
        await init_db()
        await neo4j_conn.connect()
        print("[OK] Database connections established")
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        print("Continuing startup... make sure your databases are running locally.")

    yield

    # Shutdown
    await close_neo4j()
    print("[OK] Database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    description="OSINT-powered crime analysis and syndicate detection system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(cases_router, prefix="/api/v1/cases", tags=["cases"])
app.include_router(osint_router, prefix="/api/v1/osint", tags=["osint"])
app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])


@app.get("/")
async def root():
    return {
        "message": "Crime Analysis Mapper API",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    import logging
    logger = logging.getLogger("app")
    logger.error(f"Global exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )