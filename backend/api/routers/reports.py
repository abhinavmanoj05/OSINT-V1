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
    format: str = Query("html", pattern="^(html|json|pdf)$"),
    report_type: str = Query("full", pattern="^(full|osint|network)$"),
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
        findings = res.get("findings", [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
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
            "created_at": case.created_at.isoformat() if hasattr(case.created_at, 'isoformat') else str(case.created_at) if case.created_at else None
        }
        
        # Filter data based on report type to generate unique reports
        filtered_osint = osint_results if report_type in ["full", "osint"] else []
        filtered_network = network_data if report_type in ["full", "network"] else {"nodes": [], "edges": []}
        
        report_content = report_gen.generate_investigation_report(
            case_data=case_dict,
            osint_results=filtered_osint,
            network_data=filtered_network,
            output_format="html" if format == "pdf" else format
        )
        
        if format == "html":
            return HTMLResponse(content=report_content)
        elif format == "pdf":
            import os
            import tempfile
            from markdown_pdf import MarkdownPdf, Section
            from fastapi.responses import FileResponse
            
            # Since report_generator generates HTML, we could use pdfkit. 
            # But we can also generate a quick markdown version to pass to MarkdownPdf
            # Let's use the reporting_agent to generate a dossier for this case instead!
            from backend.agent_workflow.agents.reporting_agent import reporting_agent
            
            # Recreate the correlation JSON structure expected by reporting_agent
            correlation_json = {
                "narrative_summary": filtered_osint[0].get("summary", "Investigation Report") if filtered_osint else "Investigation Report",
                "nodes": filtered_network.get("nodes", []),
                "edges": filtered_network.get("edges", [])
            }
            target_name = filtered_osint[0].get("target_value", case.case_number) if filtered_osint else case.case_number
            
            pdf_path = reporting_agent.generate_dossier(correlation_json, target_name).replace(".md", ".pdf")
            
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=500, detail="Failed to generate PDF. Check backend logs for details.")
                
            return FileResponse(
                path=pdf_path, 
                media_type="application/pdf", 
                filename=f"Report_{case.case_number}.pdf"
            )
        else:
            import json
            return JSONResponse(content=json.loads(report_content))
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")
