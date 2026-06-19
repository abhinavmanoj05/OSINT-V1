"""
Pydantic schemas for OSINT operations
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from uuid import UUID


class OSINTRequest(BaseModel):
    case_id: UUID
    target_type: str = Field(..., pattern="^(name|organization|username|email|phone|domain|ip|upi|bank_account)$")
    target_value: str = Field(..., min_length=1)
    tools: Optional[List[str]] = Field(default=None)  # Specific tools to run, None for all
    priority: int = Field(default=3, ge=1, le=5)
    llm_model: Optional[str] = None


class OSINTFinding(BaseModel):
    source: str
    entity_type: str
    entity_value: str
    platform: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: Optional[datetime] = None


class OSINTResponse(BaseModel):
    target_type: str
    target_value: str
    findings: List[OSINTFinding]
    risk_score: float
    risk_indicators: List[str]
    related_entities: List[Dict[str, Any]]
    processing_time: float


class OSINTJobResponse(BaseModel):
    id: UUID
    case_id: UUID
    job_type: str
    target_value: str
    status: str
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True