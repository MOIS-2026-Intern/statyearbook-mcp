# -*- coding: utf-8 -*-
from concurrent.futures import Future, ThreadPoolExecutor

from admin.pipeline import AdminIngestionService


class AdminJobOrchestrator:
    def __init__(self, service: AdminIngestionService):
        self.service = service
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yearbook-admin")
        self.futures: dict[str, Future] = {}

    def submit(self, job_id: str) -> None:
        self.futures[job_id] = self.executor.submit(self.service.run, job_id)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
