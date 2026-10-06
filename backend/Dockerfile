FROM python:3.12-slim

WORKDIR /app

# System deps (curl for healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast package manager)
RUN pip install --no-cache-dir uv

# Install Python deps first (cacheable layer)
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy app code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Data volume for SQLite
RUN mkdir -p /app/data

# Activate uv-managed venv in PATH
ENV PATH="/app/.venv/bin:$PATH"

# This API does not perform parallel matrix workloads. Bound native thread
# pools and glibc arenas so market-data workers do not retain excess memory.
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=2

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
