"""
Graph analysis API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncGraphDatabase

from backend.core.database import get_neo4j
from backend.core.security import get_current_user
from backend.schemas.graph import NetworkGraph, PathFindRequest, PathResponse, SyndicateDetectionRequest
from backend.services.graph_builder import CrimeGraphBuilder

router = APIRouter()


@router.get("/network/{entity_id}", response_model=NetworkGraph)
async def get_network(
    entity_id: str,
    depth: int = 2,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Get network graph for an entity.

    entity_id can be a UUID (node id), a person name, or a username.
    depth controls how many hops to traverse (default 2, max 4).
    """
    if driver is None:
        raise HTTPException(
            status_code=503,
            detail="Neo4j graph database is not available. Please ensure it is running."
        )
    depth = max(1, min(depth, 4))  # clamp depth to safe range
    service = CrimeGraphBuilder(driver)
    try:
        network = await service.get_network_graph(entity_id, depth)
        return network
    except RuntimeError as e:
        # Neo4j driver reports connectivity issues as RuntimeError
        raise HTTPException(status_code=503, detail=f"Graph database error: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/path", response_model=PathResponse)
async def find_path(
    request: PathFindRequest,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Find shortest path between two entities"""
    service = CrimeGraphBuilder(driver)
    try:
        path = await service.shortest_path(request.source_id, request.target_id)
        if not path:
            raise HTTPException(status_code=404, detail="No path found")
        return path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/syndicates")
async def detect_syndicates(
    request: SyndicateDetectionRequest,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Detect criminal syndicates"""
    service = CrimeGraphBuilder(driver)
    try:
        syndicates = await service.find_syndicates(request.min_connections)
        return {"syndicates": syndicates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entities")
async def create_entity(
    entity_data: dict,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Create a new entity in the graph"""
    service = CrimeGraphBuilder(driver)
    try:
        from backend.models.graph import EntityNode
        entity = EntityNode(
            node_type=entity_data["type"],
            properties=entity_data["properties"]
        )
        entity_id = await service.create_entity(entity)
        return {"id": entity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Delete an entity node and all its relationships"""
    service = CrimeGraphBuilder(driver)
    try:
        success = await service.delete_entity(entity_id)
        if not success:
            raise HTTPException(status_code=404, detail="Entity not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relationships")
async def create_relationship(
    rel_data: dict,
    driver: AsyncGraphDatabase = Depends(get_neo4j),
    current_user: dict = Depends(get_current_user)
):
    """Create a relationship between entities"""
    service = CrimeGraphBuilder(driver)
    try:
        from backend.models.graph import Relationship
        rel = Relationship(
            source_id=rel_data["source_id"],
            target_id=rel_data["target_id"],
            rel_type=rel_data["type"],
            properties=rel_data.get("properties", {})
        )
        success = await service.create_relationship(rel)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))