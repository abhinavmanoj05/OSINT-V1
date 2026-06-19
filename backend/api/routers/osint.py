"""
OSINT investigation API endpoints
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.core.logging import audit_logger
from backend.schemas.osint import OSINTRequest, OSINTJobResponse
from backend.services.osint_engine import EntityProfiler
from backend.workers.celery_app import run_osint_investigation

router = APIRouter()


@router.post("/investigate", response_model=OSINTJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_investigation(
    request: OSINTRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Start an OSINT investigation job"""
    # Create job record
    from backend.models.case import OSINTJob
    
    job = OSINTJob(
        case_id=request.case_id,
        job_type=f"{request.target_type}_search",
        target_value=request.target_value,
        status="pending"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Queue Celery task
    task = run_osint_investigation.delay(
        job_id=str(job.id),
        target_type=request.target_type,
        target_value=request.target_value,
        tools=request.tools,
        user_id=current_user["user_id"],
        llm_model=request.llm_model
    )
    
    # Update job with task ID
    job.status = "running"
    await db.commit()
    
    audit_logger.log_action(
        user_id=current_user["user_id"],
        action="OSINT_STARTED",
        case_id=str(request.case_id),
        details={
            "job_id": str(job.id),
            "target_type": request.target_type,
            "target_value": request.target_value
        }
    )
    
    return job


@router.get("/jobs/{job_id}", response_model=OSINTJobResponse)
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get status and results of an OSINT job"""
    from backend.models.case import OSINTJob
    
    result = await db.execute(select(OSINTJob).where(OSINTJob.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@router.post("/quick-search")
async def quick_search(
    target_type: str,
    target_value: str,
    institution: str = "",
    location: str = "",
    llm_model: str = "",
    current_user: dict = Depends(get_current_user)
):
    """Quick search without creating a case."""
    import asyncio
    import urllib.parse

    decoded_value = urllib.parse.unquote(target_value)
    decoded_institution = urllib.parse.unquote(institution)
    decoded_location = urllib.parse.unquote(location)
    decoded_llm_model = urllib.parse.unquote(llm_model)

    profiler = EntityProfiler(llm_model=decoded_llm_model)

    try:
        result = await asyncio.wait_for(
            profiler.profile_target(
                target_type, decoded_value,
                institution=decoded_institution,
                location=decoded_location
            ),
            timeout=600
        )
        result["target_type"] = target_type
        result["target_value"] = decoded_value
        return result

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="OSINT search timed out (>10 min). Try a more specific query.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))