FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_PROFILE=main \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /service
RUN groupadd --system app && useradd --system --gid app --home-dir /service app

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY app ./app
COPY utils ./utils
RUN mkdir -p /service/models && chown -R app:app /service

USER app
VOLUME ["/service/models"]
EXPOSE 8001
CMD ["python", "-m", "app"]
