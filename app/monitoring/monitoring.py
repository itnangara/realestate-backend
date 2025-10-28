import re
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Response, Request
import time

REQUEST_COUNT = Counter(
    "request_count", "Total HTTP requests", ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", "Request latency", ["endpoint"]
)

def setup_metrics(app: FastAPI):
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        # Normalize dynamic IDs in the path
        endpoint = request.url.path
        # Replace numeric IDs with {id}
        endpoint = re.sub(r"/\d+", "/{id}", endpoint)
        # Optional: replace UUIDs with {uuid}
        endpoint = re.sub(r"/[0-9a-fA-F-]{36}", "/{uuid}", endpoint)

        # Record metrics
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(process_time)
        REQUEST_COUNT.labels(
            method=request.method, endpoint=endpoint, http_status=response.status_code
        ).inc()
        return response

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
