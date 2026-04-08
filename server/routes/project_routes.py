"""
Project upload and calculation routes for CarbonPilot.
Handles file uploading, carbon emission calculations, and SSE streaming.
"""

import json
import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import StreamingResponse

from configs.llm_wrapper import LLMWrapper
from configs.neo4j_wrapper import Neo4jWrapper
from utils.running import CarbonEmissionEngine
from server.sse_manager import SSEManager

logger = logging.getLogger(__name__)

# Create static directory for storing uploaded files
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 0 for highest similarity, 1 for llm rerank with highest probability,
# 2 for llm rerank with average value, 3 for llm rerank with largest value
factor_mode_str = {0: "similarity", 1: "prob", 2: "avg", 3: "max_ef"}

router = APIRouter()
sse_manager = SSEManager()


async def _send_sse(project_name: str, event_type: str, payload: Dict[str, Any]):
    try:
        await sse_manager.send_event(project_name, event_type, payload)
    except Exception as e:
        logger.warning("SSE send failed: %s", e)


def _build_engine(
    project_name: str,
    file_path: str,
    config: Optional[Any],
    sse_callback,
    llm_wrapper: Optional[LLMWrapper] = None,
    neo4j_wrapper: Optional[Neo4jWrapper] = None
) -> CarbonEmissionEngine:

    project_root = Path(__file__).resolve().parent.parent.parent
    static_dir = project_root / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    result_dir = static_dir / "result" / project_name
    result_dir.mkdir(parents=True, exist_ok=True)

    extraction_cache_dir = static_dir / "extraction_cache"
    extraction_cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Project root: {project_root}")
    print(f"Static dir: {static_dir}")
    print(f"Result dir: {result_dir}")
    print(f"Extraction cache dir: {extraction_cache_dir}")

    # 环境变量配置
    enhance_s1 = int(os.getenv("INFORMATION_ENHANCEMENT", 0))
    enhance_s2 = int(os.getenv("WBS_CORRECTION", 0))

    agent_query = int(os.getenv("AGNETIC_SEARCH", 1))

    mem_info = int(os.getenv("MEMORY_INFORAMTION", 1))
    mem_unit = int(os.getenv("MEMORY_UNIT", 1))

    factor_mode_index_raw = os.getenv("FACTOR_ALIGNMENT_MODE", "2")
    try:
        factor_mode_index = int(factor_mode_index_raw)
    except ValueError:
        factor_mode_index = 2

    alignment_mode = factor_mode_str.get(factor_mode_index, "avg")

    member_add = False
    use_reranker = True
    k = 10
    max_steps = 5
    max_backtracks = 5
    enable_transport = True

    if config is not None:
        agent_query = getattr(config, "agent_query", agent_query)
        member_add = getattr(config, "member_add", member_add)
        use_reranker = getattr(config, "use_reranker", use_reranker)
        mem_info = getattr(config, "use_memory", mem_info)
        enable_transport = getattr(config, "transport_use_memory", enable_transport)

        cfg_align = getattr(config, "alignment_mode", None)
        if cfg_align is not None:
            alignment_mode = cfg_align

        k = getattr(config, "search_topk", k)
        max_steps = getattr(config, "max_steps", max_steps)
        max_backtracks = getattr(config, "max_backtracks", max_backtracks)

    engine = CarbonEmissionEngine(
        project_file=file_path,
        project_name=project_name,
        extraction_cache_dir=str(extraction_cache_dir),
        result_dir=str(result_dir),

        enhance_s1=bool(enhance_s1),
        enhance_s2=bool(enhance_s2),
        agent_query=bool(agent_query),
        member_add=member_add,
        use_reranker=use_reranker,
        k=k,
        max_steps=max_steps,
        max_backtracks=max_backtracks,
        mem_info=bool(mem_info),
        mem_unit=bool(mem_unit),
        alignment_mode=alignment_mode,
        enable_transport=enable_transport,

        llm_wrapper=llm_wrapper,
        neo4j_wrapper=neo4j_wrapper,
        sse_callback=sse_callback,
        logger_instance=logger,
    )

    return engine


async def pipeline_worker(
    project_name: str,
    file_path: str,
    file_name: str,
    config: Optional[Any] = None,
):

    loop = asyncio.get_running_loop()
    llm_wrapper = LLMWrapper()
    neo4j_wrapper = Neo4jWrapper()


    def engine_sse_callback(event_type: str, payload: Dict[str, Any]):
        """
        在 worker 线程中被 Engine 调用，
        通过 run_coroutine_threadsafe 把事件丢到主 event loop。
        """
        try:
            asyncio.run_coroutine_threadsafe(
                sse_manager.send_event(project_name, event_type, payload),
                loop,
            )
        except Exception as e:
            logger.warning("engine_sse_callback failed: %s", e)

    engine = _build_engine(
        project_name=project_name,
        file_path=file_path,
        config=config,
        sse_callback=engine_sse_callback,
        llm_wrapper=llm_wrapper,
        neo4j_wrapper=neo4j_wrapper
    )

    try:
        await asyncio.sleep(5)

        await sse_manager.send_event(
            project_name,
            "status",
            {"status": "Calculation started", "project_name": project_name},
        )


        await loop.run_in_executor(None, engine.run_all)


    except Exception as e:
        logger.error("Pipeline error: %s", e)
        await _send_sse(project_name, "error", {"message": str(e)})
        raise

    finally:
        try:

            if getattr(engine, "neo4j_driver", None) is not None:
                engine.neo4j_driver.close()
        except Exception as e:
            logger.warning("Neo4j close error: %s", e)


@router.post("/upload-project")
async def upload_project_file(
    file: UploadFile,
    project_name: str = Form(...),
) -> dict:
    """
    Upload project file and return metadata required to start the
    carbon emission calculation.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    logger.info("Received file for project %s: %s", project_name, file.filename)

    file_hash = hashlib.sha256(content).hexdigest()[:16]

    original_filename = file.filename
    if not original_filename:
        raise HTTPException(status_code=400, detail="File has no name")

    file_path = UPLOAD_DIR / f"{project_name}_{file_hash}_{original_filename}"
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info("File saved to: %s", file_path)

    return {
        "message": "File uploaded successfully",
        "project_name": project_name,
        "file_path": str(file_path),
        "file_hash": file_hash,
        "file_name": original_filename,
        "content_type": file.content_type,
        "sse_endpoint": f"/sse/{project_name}",
        "calculation_endpoint": f"/calculate-emission",
    }


@router.get("/sse/{project_name}")
async def sse_endpoint(project_name: str):
    """
    SSE endpoint for transmitting carbon emission calculation status updates.
    """
    return StreamingResponse(
        sse_manager.stream_events(project_name),
        media_type="text/event-stream",
    )


@router.post("/calculate-emission")
async def start_carbon_emission_calculation(
    project_name: str = Form(...),
    file_hash: str = Form(...),
    background_tasks: BackgroundTasks = None,
) -> dict:
    """
    Start the carbon emission calculation process.
    """
    if not project_name or not file_hash:
        raise HTTPException(
            status_code=400,
            detail="project_name and file_hash are required",
        )

    # Locate the saved file in the uploads directory
    file_path: Optional[str] = None
    for f in UPLOAD_DIR.iterdir():
        if f.name.startswith(f"{project_name}_{file_hash}"):
            file_path = str(f)
            break

    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    logger.info(
        "Starting carbon emission calculation for project %s with file %s",
        project_name,
        file_path,
    )

    if background_tasks is None:

        background_tasks = BackgroundTasks()


    background_tasks.add_task(
        pipeline_worker,
        project_name,
        file_path,
        f"{project_name}_{file_hash}",
        None,
    )

    return {
        "message": "Calculation started",
        "project_name": project_name,
    }
