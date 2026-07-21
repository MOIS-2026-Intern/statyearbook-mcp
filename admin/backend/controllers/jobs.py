# 이 파일은 연보 업로드, 작업 생성, 목록 및 상세 조회 API를 제공한다.
# HTTP 입력 검증 후 실제 처리는 관리자 작업 실행기에 위임한다.
import shutil

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from admin.backend.config import ADMIN_API_PREFIX
from admin.backend.controllers.dependencies import authorize_admin
from admin.backend.models.ingestion_job import ARTIFACT_NAMES, IngestionOptions
from admin.backend.services.upload import (
    UploadedYearbookService,
    UploadTooLargeError,
)
from admin.backend.services.load_dml import YEARBOOK_LOAD_MODES
from admin.backend.services.load_workspace import create_workspace


router = APIRouter(
    prefix=f"{ADMIN_API_PREFIX}/jobs",
    dependencies=[Depends(authorize_admin)],
)


@router.get("")
def list_jobs(request: Request) -> list[dict]:
    return request.app.state.job_repository.select_jobs()


@router.get("/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    try:
        return request.app.state.job_repository.select_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@router.post("", status_code=202)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    year: int = Form(...),
    title: str = Form(...),
    pub_no: str | None = Form(default=None),
    target: str = Form(default="local"),
    load_mode: str = Form(default="reject"),
    embedding_model: str = Form(default="bge-m3"),
) -> dict:
    settings = request.app.state.settings
    if not 1900 <= year <= 2200:
        raise HTTPException(status_code=422, detail="invalid publication year")
    if not title.strip():
        raise HTTPException(status_code=422, detail="publication title is required")
    if load_mode not in YEARBOOK_LOAD_MODES:
        raise HTTPException(status_code=422, detail="invalid load mode")
    try:
        settings.target_dsn(target)
        settings.embedding_model(embedding_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = Path(file.filename or ARTIFACT_NAMES.source_yearbook).name
    if Path(filename).suffix.lower() != ".hwpx":
        raise HTTPException(status_code=422, detail="only .hwpx files are accepted")

    job_id, workspace = create_workspace(settings.workspace_dir)
    input_path = workspace / ARTIFACT_NAMES.source_yearbook
    try:
        await UploadedYearbookService().save(
            file,
            input_path,
            settings.max_upload_mb * 1024 * 1024,
        )
    except UploadTooLargeError as exc:
        shutil.rmtree(workspace)
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    options = IngestionOptions(
        input_path=str(input_path),
        original_filename=filename,
        year=year,
        title=title.strip(),
        pub_no=(pub_no or "").strip() or None,
        target=target,
        load_mode=load_mode,
        embedding_model=embedding_model,
    )
    job = request.app.state.job_repository.insert_job(job_id, options.as_dict())
    request.app.state.job_orchestrator.submit(job_id)
    return job
