"""
Report generation API endpoints
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.security import get_current_user
from backend.models.case import Case, OSINTJob, EvidenceFile
from backend.services.report_generator import ReportGenerator

router = APIRouter()
report_gen = ReportGenerator()

@router.get("/{case_id}")
async def generate_report(
    case_id: UUID,
    format: str = Query("html", pattern="^(html|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Generate an investigation report for a case"""
    # 1. Fetch case data
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # 2. Fetch OSINT results
    result = await db.execute(select(OSINTJob).where(OSINTJob.case_id == case_id))
    jobs = result.scalars().all()
    
    osint_results = []
    for job in jobs:
        if job.result_data:
            # Map job data to template expected structure
            source_links = job.result_data.get("source_links", [])
            threat_assessment = job.result_data.get("threat_assessment", {})
            llm_profile = job.result_data.get("llm_profile", {})
            
            osint_results.append({
                "target_value": job.target_value,
                "target_type": job.job_type,
                "findings": source_links,
                "digital_footprint": source_links, 
                "risk_score": threat_assessment.get("score", 0),
                "summary": llm_profile.get("narrative_summary", "") or job.result_data.get("summary", "")
            })
    
    # 3. Construct Network Data from OSINT findings instead of mocking
    nodes = [{"id": "case", "label": case.case_number, "group": "Case"}]
    edges = []
    
    # Add target as a node
    nodes.append({"id": "target", "label": osint_results[0]["target_value"] if osint_results else "Target", "group": "Target"})
    edges.append({"from": "case", "to": "target", "label": "investigates"})

    entity_idx = 1
    for res in osint_results:
        for finding in res.get("findings", []):
            platform = finding.get("platform", "Unknown")
            if platform:
                node_id = f"plat_{entity_idx}"
                nodes.append({"id": node_id, "label": f"{platform}", "group": "Platform"})
                edges.append({"from": "target", "to": node_id, "label": "found_on"})
                entity_idx += 1

    network_data = {"nodes": nodes, "edges": edges}

    # 4. Generate report
    try:
        case_dict = {
            "case_number": case.case_number,
            "title": case.title,
            "description": case.description,
            "crime_type": case.crime_type,
            "status": case.status,
            "priority": case.priority,
            "assigned_officer": case.assigned_officer,
            "created_at": case.created_at.isoformat() if case.created_at else None
        }
        
        report_content = report_gen.generate_investigation_report(
            case_data=case_dict,
            osint_results=osint_results,
            network_data=network_data,
            output_format=format
        )
        
        if format == "html":
            return HTMLResponse(content=report_content)
        else:
            import json
            return JSONResponse(content=json.loads(report_content))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
