FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_PROFILE=main \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /service
RUN groupadd --system app && useradd --system --gid app --home-dir /service app

COPY admin/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY admin ./admin
COPY utils ./utils
RUN mkdir -p /service/models /service/admin/state /service/admin/workspaces \
    && chown -R app:app /service

USER app
VOLUME ["/service/models", "/service/admin/state", "/service/admin/workspaces"]
EXPOSE 8100
CMD ["python", "-m", "admin", "serve"]
