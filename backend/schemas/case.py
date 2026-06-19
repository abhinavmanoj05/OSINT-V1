"""
Pydantic schemas for case management
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID


class TargetProfile(BaseModel):
    """Structured suspect / target information for OSINT seeding"""
    name: Optional[str] = None
    aliases: Optional[List[str]] = Field(default_factory=list)
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    bank_account: Optional[str] = None
    crypto_wallet: Optional[str] = None
    ip_address: Optional[str] = None
    domain: Optional[str] = None
    institution: Optional[str] = None
    location: Optional[str] = None
    modus_operandi: Optional[str] = None
    notes: Optional[str] = None
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CaseBase(BaseModel):
    case_number: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    crime_type: Optional[str] = None
    status: str = Field(default="open")
    priority: int = Field(default=3, ge=1, le=5)
    assigned_officer: Optional[str] = None
    target_profile: Optional[TargetProfile] = None


class CaseCreate(CaseBase):
    pass


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    assigned_officer: Optional[str] = None
    target_profile: Optional[TargetProfile] = None


class CaseResponse(CaseBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    total: int
    cases: List[CaseResponse]
    page: int
    page_size: int