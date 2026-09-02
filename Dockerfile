# Dockerfile for WizDesk Backend
# Builds a production-ready container for the Django API + static frontend

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY wizdesk_backend/ ./wizdesk_backend/
COPY frontend/ ./frontend/
COPY build.sh ./
COPY .env.example ./

# Create staticfiles directory and collect static
WORKDIR /app/wizdesk_backend
RUN python manage.py collectstatic --no-input

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "wizdesk_backend.wsgi:application"]