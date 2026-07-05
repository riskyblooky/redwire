FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Build metadata — passed at ``docker build --build-arg`` time by
# scripts/deploy_server.sh. Baked into the image as env vars that
# /health surfaces so an operator can confirm what's actually live.
# Defaults to "unknown" when the build wasn't fed the args (dev, ad-hoc
# rebuilds). See backend/main.py::_resolve_build_info for the read path
# and the dev-only ``git rev-parse`` fallback.
ARG GIT_COMMIT=""
ARG BUILD_TIME=""
ENV GIT_COMMIT=$GIT_COMMIT
ENV BUILD_TIME=$BUILD_TIME

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for uploads
RUN mkdir -p /app/uploads

EXPOSE 8000

# Run database migrations and start server
CMD alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
