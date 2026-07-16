# 이 파일은 관리자 적재 작업을 단일 background worker에서 순서대로 실행한다.
# 동시에 여러 연보가 DB를 변경하지 못하도록 프로세스 실행 큐를 제공한다.
from concurrent.futures import Future, ThreadPoolExecutor

from admin.backend.services.load_pipeline import YearbookIngestionService


class AdminJobOrchestrator:
    def __init__(self, service: YearbookIngestionService):
        self.service = service
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yearbook-admin")
        self.futures: dict[str, Future] = {}

    def submit(self, job_id: str) -> None:
        self.futures[job_id] = self.executor.submit(self.service.run, job_id)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
