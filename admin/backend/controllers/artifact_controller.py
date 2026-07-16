# 이 파일은 완료되거나 실패한 관리자 작업의 산출물 다운로드 API를 제공한다.
# workspace 밖의 파일에 접근하지 못하도록 경로를 검증한다.
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from admin.backend.config import ADMIN_API_PREFIX
from admin.backend.controllers.controller_dependencies import authorize_admin


router = APIRouter(
    prefix=f"{ADMIN_API_PREFIX}/jobs/{{job_id}}/artifacts",
    dependencies=[Depends(authorize_admin)],
)


@router.get("/{artifact_name}")
def download_artifact(job_id: str, artifact_name: str, request: Request):
    repository = request.app.state.job_repository
    settings = request.app.state.settings
    try:
        job = repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    filename = job["artifacts"].get(artifact_name)
    if not filename:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = (settings.workspace_dir / job_id / filename).resolve()
    workspace = (settings.workspace_dir / job_id).resolve()
    if workspace not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, filename=path.name)
