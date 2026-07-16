# ADR 0006: Observability — OpenTelemetry + Prometheus + Structured Logging

## Status
Accepted

## Context
Need production-grade observability:
- Metrics (latency, errors, throughput)
- Distributed tracing (request flows)
- Structured logs (correlation IDs, JSON in prod)

## Decision
Integrate **OpenTelemetry SDK** with **Prometheus metrics** and **structlog**.

### Components
| Concern | Technology | Config |
|---------|------------|--------|
| Metrics | Prometheus client + OpenTelemetry Meter | `/metrics` endpoint |
| Tracing | OpenTelemetry SDK + OTLP exporter | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Logging | structlog (JSON prod, console dev) | `ENVIRONMENT=production` |

### Implementation (`app/core/observability.py`)
```python
# Metrics
request_counter = meter.create_counter("http_requests_total")
request_latency = meter.create_histogram("http_request_duration_seconds")

# Tracing
tracer = trace.get_tracer(__name__)

# Lifecycle
def create_observability_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Init OTel
        init_tracer(settings)
        init_meter(settings)
        yield
        # Shutdown
        tracer_provider.shutdown()
        meter_provider.shutdown()
    return lifespan
```

### Middleware (`app/main.py`)
```python
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = set_request_id(request.headers.get("X-Request-ID"))
    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start

    # Metrics
    record_http_request(request.method, request.url.path, response.status_code, duration)

    # Structured log
    logger.info("HTTP", method=request.method, path=request.url.path, status=response.status_code, duration_ms=duration*1000)
    response.headers["X-Request-ID"] = request_id
    return response
```

### Structured Logging (`app/core/logging.py`)
```python
# Development: pretty console with colors
# Production: JSON with timestamp, level, request_id, fields
configure_logging(settings.is_production)
```

### Health Endpoints
- `GET /health` — liveness (process alive)
- `GET /health/ready` — readiness (DB + MongoDB reachable)
- `GET /metrics` — Prometheus scrape endpoint

## Consequences
### Positive
- Vendor-neutral (OTel standard)
- Kubernetes-ready (readiness/liveness probes)
- Correlation IDs trace requests across services
- Prometheus/Grafana compatible out of the box

### Negative
- OTel setup adds complexity
- In-memory metrics (not clustered) — use external Prometheus in prod
- Tracing requires collector (Jaeger, Tempo, etc.)

## Configuration
```bash
# Observability
ENVIRONMENT=production
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=doctrace-ai
METRICS_ENABLED=true
```

## Validation
- `/metrics` returns Prometheus format
- Traces appear in Jaeger when OTLP endpoint configured
- Logs include `request_id` in JSON (prod) / colorized (dev)