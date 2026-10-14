"""FastAPI app: routes, static frontend mount, error handlers."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .db import Database
from .models import (
    CaseCreateRequest,
    CaseListItem,
    CaseResponse,
    ErrorBody,
    ErrorResponse,
    HealthResponse,
)
from .retrieval import PolicyIndex, load_policies
from .service import CaseService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

_settings = load_settings()
_db = Database(_settings.db_path)
_chunks = load_policies(_settings.policies_dir)
_index = PolicyIndex(_chunks)
_service = CaseService(_settings, _db, _index)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loaded %d policy chunks from %s", len(_chunks), _settings.policies_dir)
    yield


app = FastAPI(title="Case Resolution Desk", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return the standard error shape for all HTTPExceptions."""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=ErrorBody(code="http_error", message=str(detail))).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorBody(code="internal_error", message="An unexpected error occurred.")
        ).model_dump(),
    )


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_configured=bool(_settings.groq_api_key),
        policies_loaded=len(_chunks),
    )


@app.post("/api/cases", response_model=CaseResponse, status_code=201)
async def create_case(req: CaseCreateRequest) -> CaseResponse:
    return _service.create_case(req)


@app.get("/api/cases", response_model=list[CaseListItem])
async def list_cases() -> list[CaseListItem]:
    return [CaseListItem(**row) for row in _service.list_cases()]


@app.get("/api/cases/{case_id}", response_model=CaseResponse)
async def get_case(case_id: int) -> CaseResponse:
    data = _service.get_case(case_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Case {case_id} not found."}},
        )
    return CaseResponse(**data)


@app.delete("/api/cases/{case_id}", status_code=204, response_class=Response)
async def delete_case(case_id: int) -> Response:
    if not _service.delete_case(case_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Case {case_id} not found."}},
        )
    return Response(status_code=204)


# --- Static frontend (same origin). ---
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))