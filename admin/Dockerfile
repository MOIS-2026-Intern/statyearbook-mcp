# 이 파일은 사용자용 서버와 분리된 관리자 backend/frontend 이미지를 빌드한다.
# 로컬 모델과 관리자 코드만 포함하며 기본 포트는 8100이다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admin ./admin
COPY app ./app
COPY models ./models

EXPOSE 8100
CMD ["python", "-m", "admin", "serve"]
