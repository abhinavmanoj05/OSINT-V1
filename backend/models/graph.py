"""
Pydantic models for Neo4j graph database
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EntityType(str, Enum):
    PERSON = "Person"
    DIGITAL_IDENTITY = "DigitalIdentity"
    FINANCIAL_INSTRUMENT = "FinancialInstrument"
    DEVICE = "Device"
    LOCATION = "Location"
    ORGANIZATION = "Organization"
    CASE = "Case"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EntityNode(BaseModel):
    node_type: EntityType
    properties: Dict[str, Any] = Field(default_factory=dict)
    node_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


class PersonEntity(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    date_of_birth: Optional[str] = None
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW


class DigitalIdentityEntity(BaseModel):
    platform: str
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    profile_url: Optional[str] = None


class FinancialInstrumentEntity(BaseModel):
    instrument_type: str  # bank_account, upi_id, crypto_wallet
    identifier: str
    holder_name: Optional[str] = None


class Relationship(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
