"""
Case management API endpoints
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.core.logging import audit_logger
from backend.models.case import Case, OSINTJob, EvidenceFile, AuditLog
from backend.schemas.case import CaseCreate, CaseUpdate, CaseResponse, CaseListResponse

router = APIRouter()


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new investigation case"""
    # Check for duplicate case number
    result = await db.execute(
        select(Case).where(Case.case_number == case_data.case_number)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Case number {case_data.case_number} already exists"
        )
    
    dump = case_data.model_dump()
    # Serialize target_profile TargetProfile object -> plain dict for JSON column
    if dump.get("target_profile") and hasattr(dump["target_profile"], "model_dump"):
        dump["target_profile"] = dump["target_profile"].model_dump(exclude_none=True)
    elif dump.get("target_profile") is None:
        dump["target_profile"] = {}
    new_case = Case(**dump)
    db.add(new_case)
    await db.commit()
    await db.refresh(new_case)
    
    # Audit log
    audit_logger.log_action(
        user_id=current_user["user_id"],
        action="CASE_CREATED",
        case_id=str(new_case.id),
        details={"case_number": case_data.case_number}
    )
    
    return new_case


@router.get("/", response_model=CaseListResponse)
async def list_cases(
    status: Optional[str] = None,
    crime_type: Optional[str] = None,
    assigned_officer: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List cases with filtering and pagination"""
    query = select(Case)
    
    if status:
        query = query.where(Case.status == status)
    if crime_type:
        query = query.where(Case.crime_type == crime_type)
    if assigned_officer:
        query = query.where(Case.assigned_officer == assigned_officer)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Case.created_at.desc())
    
    result = await db.execute(query)
    cases = result.scalars().all()
    
    return {
        "total": total,
        "cases": cases,
        "page": page,
        "page_size": page_size
    }


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get case details"""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    return case


@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    case_update: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update case details"""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    update_data = case_update.model_dump(exclude_unset=True)
    # Serialize nested TargetProfile if present
    if "target_profile" in update_data and update_data["target_profile"] is not None:
        if hasattr(update_data["target_profile"], "model_dump"):
            update_data["target_profile"] = update_data["target_profile"].model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(case, field, value)
    
    await db.commit()
    await db.refresh(case)
    
    audit_logger.log_action(
        user_id=current_user["user_id"],
        action="CASE_UPDATED",
        case_id=str(case_id),
        details=update_data
    )
    
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a case (soft delete in production)"""
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    await db.delete(case)
    await db.commit()
    
    audit_logger.log_action(
        user_id=current_user["user_id"],
        action="CASE_DELETED",
        case_id=str(case_id)
    )
    
    return None


@router.get("/{case_id}/jobs")
async def get_case_jobs(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all OSINT jobs for a case"""
    result = await db.execute(
        select(OSINTJob).where(OSINTJob.case_id == case_id)
    )
    jobs = result.scalars().all()
    return jobs


@router.get("/{case_id}/evidence")
async def get_case_evidence(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all evidence files for a case"""
    result = await db.execute(
        select(EvidenceFile).where(EvidenceFile.case_id == case_id)
    )
    files = result.scalars().all()
    return files