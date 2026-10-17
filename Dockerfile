FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY backend/requirements.lock.txt /app/backend/requirements.lock.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt && useradd --create-home --uid 10001 buildgraph
COPY backend/ /app/backend/
COPY examples/quick-check/ /app/examples/quick-check/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN mkdir /app/.data && chown -R buildgraph:buildgraph /app/.data
USER buildgraph
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
