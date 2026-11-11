FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Unprivileged: the MCP server only talks HTTP to the backend, writes nothing.
RUN groupadd --system --gid 10001 redwire \
    && useradd --system --uid 10001 --gid redwire --no-create-home redwire
USER redwire

EXPOSE 3001

CMD ["python", "server.py"]
