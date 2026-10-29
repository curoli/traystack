FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY pyproject.toml alembic.ini ./
COPY traystack ./traystack
COPY alembic ./alembic
RUN pip install --no-deps . && useradd --uid 10001 --create-home app && mkdir -p /data/blobs && chown -R app:app /data
USER app
EXPOSE 8000
CMD ["uvicorn", "traystack.main:app", "--host", "0.0.0.0", "--port", "8000"]
