FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
RUN addgroup --system karna && adduser --system --ingroup karna karna
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/data/uploads /app/data/backups /app/data/exports && chown -R karna:karna /app
USER karna
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["sh","-c","python -m uvicorn backend.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --workers 1 --proxy-headers"]
