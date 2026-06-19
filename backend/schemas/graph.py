"""
Pydantic schemas for graph operations
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, model_validator


class NetworkNode(BaseModel):
    id: str
    label: str
    group: str
    title: Optional[str] = None


class NetworkEdge(BaseModel):
    """Edge with alias support so both 'from'/'to' and 'source'/'target' keys work."""
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    label: str
    title: Optional[str] = None

    model_config = {"populate_by_name": True}


class NetworkGraph(BaseModel):
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]

    @model_validator(mode="before")
    @classmethod
    def _coerce_edges(cls, data: Any) -> Any:
        """Allow edges to come in as dicts with 'from'/'to' keys (alias) or
        'source'/'target' keys (field name)."""
        if isinstance(data, dict) and "edges" in data:
            coerced = []
            for edge in data["edges"]:
                if isinstance(edge, dict):
                    # If already using field names, convert to alias form so
                    # Pydantic can populate via alias.
                    if "source" in edge and "from" not in edge:
                        edge = {**edge, "from": edge["source"], "to": edge["target"]}
                coerced.append(edge)
            data = {**data, "edges": coerced}
        return data


class PathFindRequest(BaseModel):
    source_id: str
    target_id: str


class PathResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    relationships: List[str]
    path_length: int
    confidence: float


class SyndicateMember(BaseModel):
    person_id: str
    name: str
    connection_count: int
    connected_ids: List[str]


class SyndicateDetectionRequest(BaseModel):
    min_connections: int = Field(default=3, ge=2)


class Syndicate(BaseModel):
    members: List[SyndicateMember]
    primary_activity: Optional[str] = None
    confidence_score: float = 0.0
