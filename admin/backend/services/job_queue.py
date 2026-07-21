# 이 파일은 관리자 적재 작업을 단일 background worker에서 순서대로 실행한다.
# 동시에 여러 연보가 DB를 변경하지 못하도록 프로세스 실행 큐를 제공한다.
from concurrent.futures import Future, ThreadPoolExecutor

from admin.backend.services.load_pipeline import YearbookIngestionService


class AdminJobOrchestrator:
    # DB 변경 작업이 겹치지 않도록 단일 worker 실행기를 준비한다.
    def __init__(self, service: YearbookIngestionService):
        self.service = service
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yearbook-admin")
        self.futures: dict[str, Future] = {}

    # 지정 작업을 순차 실행 큐에 넣고 추적 가능한 future를 보관한다.
    def submit(self, job_id: str) -> None:
        self.futures[job_id] = self.executor.submit(self.service.run, job_id)

    # 진행 중 작업은 유지하면서 더 이상 새 작업을 받지 않도록 실행기를 닫는다.
    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
