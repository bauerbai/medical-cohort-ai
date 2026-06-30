from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.academic_workflow import build_academic_workflow_plan
from agent.agent_v2 import run_llm_agent_v2
from agent.workflow import run_rwe_agent
from database import close_db_pool, get_db_connection, init_db_pool, release_db_connection
from dialogue_manager import handle_chat_message, run_session_analysis
from engine import AnalysisRegistry
from metadata_scanner import is_metadata_cached, scan_schema
from research_catalog import format_research_catalog, get_research_options
from stats_engine import get_analysis_result


REPORT_DIR = Path(__file__).resolve().parent / "reports"


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class AgentRequest(BaseModel):
    message: str
    session_id: str = "default"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db_pool()
    try:
        yield
    finally:
        await close_db_pool()


app = FastAPI(title="Medical Cohort API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_capability_question(message: str) -> bool:
    if message == "你能做什么":
        return True
    return any(
        keyword in message
        for keyword in {"能读取数据库", "数据库能做", "能做哪些分析", "可以做哪些分析", "这些数据", "支持哪些分析", "哪些研究"}
    )


@app.get("/api/analyses")
async def list_analyses() -> dict[str, Any]:
    return {"analyses": [spec.model_dump() for spec in AnalysisRegistry.list_specs()]}


@app.get("/api/academic-workflow")
async def academic_workflow() -> dict[str, Any]:
    return {"status": "success", "workflow": build_academic_workflow_plan()}


@app.post("/api/agent")
async def agent_chat(payload: AgentRequest) -> dict[str, Any]:
    return await run_rwe_agent(payload.message, payload.session_id)


@app.post("/api/agent-v2")
async def agent_chat_v2(payload: AgentRequest) -> dict[str, Any]:
    return await run_llm_agent_v2(payload.message, payload.session_id)


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> dict[str, Any]:
    normalized_message = payload.message.strip()

    if _is_capability_question(normalized_message) or not is_metadata_cached():
        metadata = await scan_schema()
        if _is_capability_question(normalized_message):
            return {
                "reply": format_research_catalog(metadata),
                "status": "success",
                "step": "metadata",
                "metadata": metadata,
                "options": get_research_options(),
            }

    if normalized_message in {"开始分析", "[开始分析]"}:
        return await run_session_analysis(payload.session_id)

    dialogue_steps = {
        "select_analysis",
        "select_cohort_type",
        "select_mr_type",
        "select_exposure",
        "select_outcome",
        "select_methods",
        "confirm",
        "analysis_complete",
    }
    dialogue_response = await handle_chat_message(normalized_message, payload.session_id)
    if dialogue_response.get("step") in dialogue_steps:
        return dialogue_response

    connection = await get_db_connection()
    try:
        database_name = await connection.fetchval("SELECT current_database();")
    finally:
        await release_db_connection(connection)

    return {"reply": f"Connected to DB: {database_name}", "status": "success"}


@app.post("/api/analyze/{session_id}")
async def analyze(session_id: str) -> dict[str, Any]:
    return await run_session_analysis(session_id)


@app.get("/api/download/{session_id}")
async def download_report(session_id: str) -> FileResponse:
    result = get_analysis_result(session_id)
    if not result or not result.get("report_path"):
        raise HTTPException(status_code=404, detail="Report not found. Run analysis first.")

    report_path = Path(result["report_path"])
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file is missing.")

    return FileResponse(
        path=report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=report_path.name,
    )


@app.get("/api/download-file/{filename}")
async def download_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = (REPORT_DIR / safe_name).resolve()
    report_root = REPORT_DIR.resolve()
    if report_root not in file_path.parents or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = "text/csv; charset=utf-8" if file_path.suffix.lower() == ".csv" else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)



