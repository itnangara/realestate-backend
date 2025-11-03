# syntax=docker/dockerfile:1

# Multi-stage Dockerfile for production
# Stage 1: Build stage - install dependencies
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim as builder

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    python -m pip install --user --no-warn-script-location -r requirements.txt

# Stage 2: Runtime stage - minimal production image
FROM python:${PYTHON_VERSION}-slim as runtime

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN groupadd -r appuser && useradd -r -g appuser -u ${UID} -d /nonexistent -s /sbin/nologin appuser

# Copy only installed packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY . .

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# Switch to the non-privileged user to run the application.
USER appuser

# Expose the port that the application listensopie on.
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application with gunicorn + uvicorn workers for production
# Workers formula: 2 x CPU cores + 1 (configurable via GUNICORN_WORKERS env var)
# Default: 4 workers, timeout: 120s, keep-alive: 5s
CMD gunicorn main:app \
    --workers ${GUNICORN_WORKERS:-4} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --keep-alive ${GUNICORN_KEEP_ALIVE:-5} \
    --access-logfile - \
    --error-logfile - \
    --log-level info
