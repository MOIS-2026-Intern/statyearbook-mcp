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
