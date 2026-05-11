FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

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
