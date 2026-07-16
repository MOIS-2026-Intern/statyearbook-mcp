# -*- coding: utf-8 -*-
from pathlib import Path

from fastapi import UploadFile


class UploadTooLargeError(ValueError):
    pass


class UploadedYearbookService:
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
