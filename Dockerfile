# =============================================================================
# Stage 1 — Build
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install only build-time deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# =============================================================================
# Stage 2 — Runtime (slim)
# =============================================================================
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY main.py .
COPY src/ src/
COPY scripts/ scripts/

# Create data directory at runtime
RUN mkdir -p data/articles

ENTRYPOINT ["python"]
CMD ["main.py"]
