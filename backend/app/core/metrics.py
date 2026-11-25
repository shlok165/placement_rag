"""In-process counters exposed at /metrics in Prometheus text format."""

import threading
from collections import defaultdict

_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_sum: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._latency_buckets: dict[tuple[str, float], int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            self._latency_sum[route] += seconds
            self._latency_count[route] += 1
            for bucket in _BUCKETS:
                if seconds <= bucket:
                    self._latency_buckets[(route, bucket)] += 1

    def render(self, gauges: dict[str, float]) -> str:
        lines = ["# TYPE http_requests_total counter"]
        with self._lock:
            for (method, route, status), count in sorted(self._requests.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f"http_requests_total{{{labels}}} {count}")
            lines.append("# TYPE http_request_seconds histogram")
            for route, count in sorted(self._latency_count.items()):
                for bucket in _BUCKETS:
                    value = self._latency_buckets[(route, bucket)]
                    lines.append(
                        f'http_request_seconds_bucket{{route="{route}",le="{bucket}"}} {value}'
                    )
                lines.append(f'http_request_seconds_bucket{{route="{route}",le="+Inf"}} {count}')
                seconds = self._latency_sum[route]
                lines.append(f'http_request_seconds_sum{{route="{route}"}} {seconds:.4f}')
                lines.append(f'http_request_seconds_count{{route="{route}"}} {count}')
        for name, gauge in gauges.items():
            lines += [f"# TYPE {name} gauge", f"{name} {gauge}"]
        return "\n".join(lines) + "\n"


metrics = Metrics()
