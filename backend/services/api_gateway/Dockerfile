# Cloud Run image for the api_gateway service.
# Multi-stage to keep the final image small.

FROM python:3.11-slim AS builder
WORKDIR /app

# Install the backend project + its deps. We copy the whole backend tree so
# the editable workspace packages resolve.
COPY pyproject.toml ./
COPY packages ./packages
COPY services ./services

# Install with the [gcp] extra so the runtime has google-cloud-storage /
# bigquery / firestore — needed by uploads, the profiler, the edge proposer,
# and the cube-gen job (which runs from this same image).
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir '.[gcp]'

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

ENV PORT=8080
EXPOSE 8080

# Cloud Run sets $PORT at runtime; uvicorn binds to it.
CMD ["sh", "-c", "uvicorn services.api_gateway.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
