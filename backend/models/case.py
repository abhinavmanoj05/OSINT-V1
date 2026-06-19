"""
SQLAlchemy models for case management
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, Enum, Uuid
from sqlalchemy.orm import relationship
import uuid

from backend.core.database import Base


class Case(Base):
    __tablename__ = "cases"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_number = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    crime_type = Column(String(50))
    status = Column(String(20), default="open")
    priority = Column(Integer, default=3)
    assigned_officer = Column(String(100))
    # Suspect / target profile — structured OSINT seed data
    target_profile = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    osint_jobs = relationship("OSINTJob", back_populates="case", cascade="all, delete-orphan")
    evidence_files = relationship("EvidenceFile", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")


class OSINTJob(Base):
    __tablename__ = "osint_jobs"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id = Column(Uuid, ForeignKey("cases.id"), nullable=False)
    job_type = Column(String(50), nullable=False)  # username_search, email_lookup, etc.
    target_value = Column(String(255), nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    result_data = Column(JSON)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    case = relationship("Case", back_populates="osint_jobs")


class EvidenceFile(Base):
    __tablename__ = "evidence_files"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id = Column(Uuid, ForeignKey("cases.id"), nullable=True)
    file_type = Column(String(20))  # pdf, image, document
    original_filename = Column(String(255))
    storage_path = Column(String(500))
    file_hash = Column(String(64))  # SHA-256
    extracted_text = Column(Text)
    ocr_confidence = Column(JSON)  # Store confidence per page/region
    entities_found = Column(JSON)  # Extracted entities
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    case = relationship("Case", back_populates="evidence_files")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id = Column(Uuid, ForeignKey("cases.id"))
    action = Column(String(100), nullable=False)
    performed_by = Column(String(100), nullable=False)
    ip_address = Column(String(45))
    details = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    case = relationship("Case", back_populates="audit_logs")