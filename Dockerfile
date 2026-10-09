FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=appuser:appuser wizdesk_backend/ ./wizdesk_backend/
COPY --chown=appuser:appuser frontend/ ./frontend/
COPY gunicorn.conf.py ./
WORKDIR /app/wizdesk_backend
# Build-only secret; runtime must supply its own SECRET_KEY and DATABASE_URL.
RUN SECRET_KEY=collectstatic-build-only-not-a-runtime-secret DATABASE_URL=sqlite:///:memory: python manage.py collectstatic --noinput
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "wizdesk_backend.wsgi:application"]
