FROM python:3.12-slim

WORKDIR /app

# Install curl (for healthcheck) and build tools in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Copy application code
COPY app/ ./app/

EXPOSE 8000

# Model downloads at first startup into a volume, not baked into image.
# This keeps the image small and avoids the export timeout.
ENV HF_HOME=/app/hf-cache

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
