"""
Document processing models
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    text: str
    confidence: float
    bounding_box: Optional[List[int]] = None
    page_number: int = 1


class ExtractedEntity(BaseModel):
    entity_type: str
    value: str
    confidence: float
    context: Optional[str] = None
    position: Optional[Dict[str, int]] = None


class DocumentMetadata(BaseModel):
    filename: str
    file_type: str
    file_size: int
    page_count: Optional[int] = None
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None


class DocumentProcessingResult(BaseModel):
    document_id: str
    metadata: DocumentMetadata
    ocr_results: List[OCRResult]
    extracted_entities: List[ExtractedEntity]
    llm_analysis: Optional[Dict[str, Any]] = None
    tables: Optional[List[Dict]] = None
    processing_time: float
    status: str