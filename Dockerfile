FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF and image rasterization
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY packages/ ./packages/
COPY apps/ ./apps/
COPY sdk/ ./sdk/
COPY universal_drm/ ./universal_drm/

RUN pip install --no-cache-dir -e ".[api,demo]"

EXPOSE 8000 5050

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "universal_drm.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
