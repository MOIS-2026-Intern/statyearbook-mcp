# -*- coding: utf-8 -*-
from __future__ import annotations

import hmac
import shutil
import uuid

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from admin.config import ADMIN_DIR, AdminSettings, settings
from admin.job_store import AdminJobStore
from admin.orchestrator import AdminJobOrchestrator
from admin.pipeline import AdminIngestionService, IngestionOptions
from load.yearbook_dml import LOAD_MODES


def create_app(config: AdminSettings = settings) -> FastAPI:
    store = AdminJobStore(config.db_path)
    service = AdminIngestionService(config, store)
    orchestrator = AdminJobOrchestrator(service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        orchestrator.close()

    app = FastAPI(
        title="StatYearbook Administration",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/admin-api/docs",
        openapi_url="/admin-api/openapi.json",
    )
    app.state.config = config
    app.state.store = store
    app.state.orchestrator = orchestrator

    def authorize(x_admin_token: str | None = Header(default=None)) -> None:
        if config.api_token and not hmac.compare_digest(x_admin_token or "", config.api_token):
            raise HTTPException(status_code=401, detail="invalid admin token")

    @app.get("/api/health")
    def health(_auth=Depends(authorize)) -> dict:
        return {"status": "ok", "service": "statyearbook-admin"}

    @app.get("/api/options")
    def options(_auth=Depends(authorize)) -> dict:
        return {
            "targets": config.targets(),
            "load_modes": [
                {"id": "reject", "label": "중복 연도 거부", "description": "같은 연도가 있으면 안전하게 중단합니다."},
                {"id": "replace", "label": "해당 연도 교체", "description": "선택 연도의 기존 데이터만 삭제한 뒤 다시 적재합니다."},
            ],
            "embedding_models": [
                {
                    "id": item.id,
                    "label": item.label,
                    "provider": item.provider,
                    "dimension": item.dimension,
                    "enabled": item.enabled,
                    "description": item.description,
                }
                for item in config.embedding_models()
            ],
            "max_upload_mb": config.max_upload_mb,
        }

    @app.get("/api/jobs")
    def list_jobs(_auth=Depends(authorize)) -> list[dict]:
        return store.list()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, _auth=Depends(authorize)) -> dict:
        try:
            return store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        file: UploadFile = File(...),
        year: int = Form(...),
        title: str = Form(...),
        pub_no: str | None = Form(default=None),
        target: str = Form(default="local"),
        load_mode: str = Form(default="reject"),
        embedding_model: str = Form(default="bge-m3"),
        extract_images: bool = Form(default=False),
        _auth=Depends(authorize),
    ) -> dict:
        if not 1900 <= year <= 2200:
            raise HTTPException(status_code=422, detail="invalid publication year")
        if not title.strip():
            raise HTTPException(status_code=422, detail="publication title is required")
        if load_mode not in LOAD_MODES:
            raise HTTPException(status_code=422, detail="invalid load mode")
        try:
            config.target_dsn(target)
            config.embedding_model(embedding_model)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        filename = Path(file.filename or "upload.hwpx").name
        if Path(filename).suffix.lower() != ".hwpx":
            raise HTTPException(status_code=422, detail="only .hwpx files are accepted")

        job_id = uuid.uuid4().hex
        workspace = config.workspace_dir / job_id
        workspace.mkdir(parents=True, exist_ok=False)
        input_path = workspace / "source.hwpx"
        size = 0
        with input_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.max_upload_mb * 1024 * 1024:
                    output.close()
                    shutil.rmtree(workspace)
                    raise HTTPException(status_code=413, detail="upload is too large")
                output.write(chunk)
        await file.close()
        options_payload = IngestionOptions(
            input_path=str(input_path),
            original_filename=filename,
            year=year,
            title=title.strip(),
            pub_no=(pub_no or "").strip() or None,
            target=target,
            load_mode=load_mode,
            embedding_model=embedding_model,
            extract_images=extract_images,
        ).as_dict()
        job = store.create(job_id, options_payload)
        orchestrator.submit(job_id)
        return job

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_name}")
    def download_artifact(job_id: str, artifact_name: str, _auth=Depends(authorize)):
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        filename = job["artifacts"].get(artifact_name)
        if not filename:
            raise HTTPException(status_code=404, detail="artifact not found")
        path = (config.workspace_dir / job_id / filename).resolve()
        workspace = (config.workspace_dir / job_id).resolve()
        if workspace not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path, filename=path.name)

    web_dir = ADMIN_DIR / "web"
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="admin-web")
    return app


app = create_app()


def run() -> None:
    uvicorn.run("admin.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
