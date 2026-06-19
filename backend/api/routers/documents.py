"""
Document processing API endpoints
"""
import uuid
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.services.document_processor import DocumentProcessor

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_document(
    case_id: Optional[str] = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Upload and process a document"""
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/tiff"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not supported"
        )
    
    file_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix
    storage_path = UPLOAD_DIR / f"{file_id}{file_extension}"
    
    with open(storage_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    service = DocumentProcessor()
    try:
        result = await service.process_document(str(storage_path), file.content_type)
        
        from backend.models.case import EvidenceFile
        import hashlib
        
        with open(storage_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        evidence = EvidenceFile(
            case_id=uuid.UUID(case_id) if case_id and case_id != "null" else None,
            file_type=file.content_type.split("/")[-1],
            original_filename=file.filename,
            storage_path=str(storage_path),
            file_hash=file_hash,
            extracted_text=result.ocr_results[0].text if result.ocr_results else "",
            ocr_confidence={"average": result.ocr_results[0].confidence} if result.ocr_results else {},
            entities_found=[e.model_dump() for e in result.extracted_entities],
            uploaded_by=current_user["user_id"]
        )
        db.add(evidence)
        await db.commit()
        await db.refresh(evidence)
        
        return {
            "document_id": str(evidence.id),
            "processing_result": result.model_dump(),
            "entities_found": len(result.extracted_entities)
        }
        
    except Exception as e:
        import traceback
        print(f"Error in document upload: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get document details"""
    from backend.models.case import EvidenceFile
    from sqlalchemy import select
    
    result = await db.execute(
        select(EvidenceFile).where(EvidenceFile.id == document_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return doc


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Reprocess a document"""
    from backend.models.case import EvidenceFile
    from sqlalchemy import select
    
    result = await db.execute(
        select(EvidenceFile).where(EvidenceFile.id == document_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    service = DocumentProcessor()
    result = await service.process_document(doc.storage_path, f"image/{doc.file_type}")
    
    doc.extracted_text = result.ocr_results[0].text if result.ocr_results else ""
    doc.entities_found = [e.model_dump() for e in result.extracted_entities]
    await db.commit()
    
    return result