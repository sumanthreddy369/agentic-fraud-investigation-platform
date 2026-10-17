"""Per-process HTTP metrics with bounded labels and no request identifiers."""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


class HttpMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "risk_http_requests_total",
            "Completed HTTP requests",
            ["route", "method", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "risk_http_request_duration_seconds",
            "HTTP request duration",
            ["route", "method"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
            registry=self.registry,
        )

    def observe(self, route: str, method: str, status: int, seconds: float) -> None:
        if route == "/metrics":
            return
        method = (
            method
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "OTHER"
        )
        self.requests.labels(route, method, str(status)).inc()
        self.duration.labels(route, method).observe(seconds)

    def render(self) -> bytes:
        return generate_latest(self.registry)
