from backend.api.routers.cases import router as cases_router
from backend.api.routers.osint import router as osint_router
from backend.api.routers.graph import router as graph_router
from backend.api.routers.documents import router as documents_router
from backend.api.routers.reports import router as reports_router

__all__ = ["cases_router", "osint_router", "graph_router", "documents_router", "reports_router"]
