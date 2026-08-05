ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CARINA_HOST=0.0.0.0 \
    CARINA_PORT=8787 \
    CARINA_CONFIG_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY carina ./carina

RUN python -m pip install --no-cache-dir . \
    && groupadd --system --gid 10001 carina \
    && useradd --system --uid 10001 --gid carina --create-home carina \
    && mkdir -p /data \
    && chown carina:carina /data

USER carina

VOLUME ["/data"]
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3)"]

CMD ["python", "-m", "carina"]
