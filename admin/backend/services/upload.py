# 이 파일은 업로드된 HWPX 스트림을 크기 제한 안에서 workspace에 저장한다.
# HTTP controller와 파일 쓰기 세부 동작을 분리한다.
from pathlib import Path

from fastapi import UploadFile


class UploadTooLargeError(ValueError):
    pass


class UploadedYearbookService:
    # 업로드를 청크 단위로 저장하며 제한 초과 시 즉시 전용 오류를 발생시킨다.
    async def save(self, upload: UploadFile, destination: Path, max_bytes: int) -> int:
        size = 0
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLargeError("upload is too large")
                output.write(chunk)
        await upload.close()
        return size
