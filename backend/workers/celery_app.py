"""
Celery configuration and tasks
"""
import os
import asyncio
from datetime import datetime
from celery import Celery
from celery.signals import task_prerun, task_postrun

from backend.core.config import settings

# Ensure absolute paths for celery folders
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
celery_out = os.path.join(base_dir, ".celery", "out")
celery_proc = os.path.join(base_dir, ".celery", "processed")

# Create directories to prevent FileNotFoundError during worker startup
os.makedirs(celery_out, exist_ok=True)
os.makedirs(celery_proc, exist_ok=True)

celery_app = Celery(
    "crime_mapper",
    broker="filesystem://",
    backend=f"db+sqlite:///{os.path.join(base_dir, 'celery_results.db')}",
    include=["backend.workers.celery_app"]
)

celery_app.conf.update(
    broker_transport_options={
        'data_folder_in': celery_out,
        'data_folder_out': celery_out,
        'data_folder_processed': celery_proc
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    worker_prefetch_multiplier=1,
    task_always_eager=False,  # Actually use the worker process
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
)


@task_prerun.connect
def task_started_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    print(f"Starting task {task.name} [{task_id}]")


@task_postrun.connect
def task_completed_handler(sender=None, task_id=None, task=None, retval=None, state=None, **extras):
    print(f"Completed task {task.name} [{task_id}] with state {state}")


import logging

logger = logging.getLogger(__name__)

# ... (rest of the file is the same)

@celery_app.task(bind=True, max_retries=3)
def run_osint_investigation(self, job_id: str, target_type: str, target_value: str, tools: list = None, user_id: str = None, llm_model: str = None):
    """
    Run OSINT investigation as background task
    """
    logger.info(f"Celery task 'run_osint_investigation' started for job_id: {job_id}")
    async def _run():
        from backend.core.database import async_session_maker
        from backend.models.case import OSINTJob
        from sqlalchemy import select
        
        async with async_session_maker() as db:
            try:
                logger.info(f"Looking up OSINTJob with id: {job_id}")
                import uuid
                job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
                result = await db.execute(select(OSINTJob).where(OSINTJob.id == job_uuid))
                job = result.scalar_one_or_none()
                
                if not job:
                    logger.error(f"OSINTJob with id: {job_id} not found in database.")
                    return {"error": "Job not found"}
                
                job.status = "running"
                job.started_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Job {job_id} status updated to 'running'.")
                
                from backend.models.case import Case
                case_result = await db.execute(select(Case).where(Case.id == job.case_id))
                case_obj = case_result.scalar_one_or_none()
                
                institution = ""
                location = ""
                if case_obj and case_obj.target_profile:
                    profile = case_obj.target_profile
                    if isinstance(profile, dict):
                        institution = profile.get("institution", "")
                        location = profile.get("location", "")
                
                from backend.services.osint_engine import EntityProfiler
                
                profiler = EntityProfiler(llm_model=llm_model)
                logger.info(f"Profiling target '{target_value}' of type '{target_type}' (Institution: '{institution}', Location: '{location}')")
                
                result_data = await profiler.profile_target(target_type, target_value, institution=institution, location=location)
                
                job.status = "completed"
                job.result_data = result_data
                job.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Job {job_id} completed successfully. Result data stored.")
                
                logger.info(f"Storing entities from job {job_id} into graph database.")
                try:
                    await _store_entities(target_type, target_value, result_data)
                    logger.info(f"Entities from job {job_id} stored successfully.")
                except Exception as neo_err:
                    logger.warning(f"Could not connect to Neo4j. Graph storage skipped: {neo_err}")
                
                return result_data
                
            except Exception as e:
                logger.error(f"Celery task for job {job_id} failed: {e}", exc_info=True)
                # Ensure db is not None before trying to use it
                if 'db' in locals() and db:
                    # Reload job object in case of session issues
                    import uuid
                    job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
                    result = await db.execute(select(OSINTJob).where(OSINTJob.id == job_uuid))
                    job = result.scalar_one_or_none()
                    if job:
                        job.status = "failed"
                        job.error_message = str(e)
                        await db.commit()
                
    try:
        loop = asyncio.get_running_loop()
        # We are in eager mode inside FastAPI's event loop. Run in a new thread.
        import threading
        result = None
        ex = None
        def thread_worker():
            nonlocal result, ex
            try:
                result = asyncio.run(_run())
            except Exception as e:
                import traceback
                traceback.print_exc()
                ex = e
        t = threading.Thread(target=thread_worker)
        t.start()
        t.join()
        if ex:
            raise ex
        return result
    except RuntimeError:
        # No running event loop (Celery worker process)
        return asyncio.run(_run())


async def _store_entities(target_type: str, target_value: str, result_data: dict):
    """Store discovered entities in Neo4j"""
    from backend.services.graph_builder import CrimeGraphBuilder
    from backend.core.database import neo4j_conn
    from backend.models.graph import EntityNode, Relationship
    
    await neo4j_conn.connect()
    builder = CrimeGraphBuilder(neo4j_conn.driver)
    
    # Core target entity
    entity = EntityNode(
        node_type="DigitalIdentity",
        properties={
            target_type: target_value,
            "discovered_via": "osint_investigation"
        }
    )
    entity_id = await builder.create_entity(entity)
    
    extracted_entities = result_data.get("extracted_entities", {})
    
    def map_node_type(etype: str) -> str:
        if etype in ["name", "aliases"]: return "Person"
        if etype in ["bank_account_id", "upi_id", "crypto_wallet"]: return "FinancialInstrument"
        if etype in ["ip_address", "device_fingerprint"]: return "Device"
        if etype in ["locations"]: return "Location"
        if etype in ["affiliations", "institutions", "organization"]: return "Organization"
        return "DigitalIdentity"

    related_ids = []
    for entity_type, values in extracted_entities.items():
        if not values or entity_type in ["modus_operandi", "active_hours", "key_findings", "roll_numbers", "flags"]:
            continue
            
        for value in values:
            if value == target_value:
                continue
                
            related = EntityNode(
                node_type=map_node_type(entity_type),
                properties={
                    "type": entity_type,
                    "value": value,
                    "name": value
                }
            )
            related_id = await builder.create_entity(related)
            related_ids.append(related_id)
            
            rel = Relationship(
                source_id=entity_id,
                target_id=related_id,
                rel_type="HAS_IDENTIFIER",
                properties={"confidence": 0.8}
            )
            await builder.create_relationship(rel)