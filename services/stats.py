"""
Centralized statistics tracking for API calls and service health.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ServiceStats:
    """Stats for a single external service (Swarm, Google Calendar, etc.)."""
    
    name: str
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_bytes: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    latencies: deque = field(default_factory=lambda: deque(maxlen=1000))
    last_error: str | None = None
    last_error_time: datetime | None = None
    
    def record_request(
        self,
        latency_ms: float,
        success: bool,
        bytes_received: int = 0,
        error: str | None = None,
    ) -> None:
        """Record a single API request."""
        self.request_count += 1
        self.total_latency_ms += latency_ms
        self.latencies.append(latency_ms)
        
        if latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
        if latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms
            
        if success:
            self.success_count += 1
            self.total_bytes += bytes_received
        else:
            self.failure_count += 1
            self.last_error = error
            self.last_error_time = datetime.now(timezone.utc)
    
    def to_dict(self) -> dict[str, Any]:
        """Export stats as a dictionary."""
        avg_latency = (
            self.total_latency_ms / self.request_count
            if self.request_count > 0
            else 0.0
        )
        
        # Calculate percentiles from recent latencies
        p50 = p95 = p99 = 0.0
        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            n = len(sorted_latencies)
            p50 = sorted_latencies[int(n * 0.50)] if n > 0 else 0.0
            p95 = sorted_latencies[int(n * 0.95)] if n > 0 else 0.0
            p99 = sorted_latencies[int(n * 0.99)] if n > 0 else 0.0
        
        return {
            "service": self.name,
            "requests": {
                "total": self.request_count,
                "success": self.success_count,
                "failure": self.failure_count,
                "success_rate": (
                    f"{(self.success_count / self.request_count * 100):.1f}%"
                    if self.request_count > 0
                    else "N/A"
                ),
            },
            "latency_ms": {
                "avg": round(avg_latency, 1),
                "min": round(self.min_latency_ms, 1) if self.min_latency_ms != float("inf") else 0.0,
                "max": round(self.max_latency_ms, 1),
                "p50": round(p50, 1),
                "p95": round(p95, 1),
                "p99": round(p99, 1),
            },
            "bytes_received": self.total_bytes,
            "bytes_received_human": _format_bytes(self.total_bytes),
            "last_error": self.last_error,
            "last_error_time": (
                self.last_error_time.isoformat() if self.last_error_time else None
            ),
        }


@dataclass
class EndpointStats:
    """Stats for a single API endpoint."""
    
    name: str
    call_count: int = 0
    last_called: datetime | None = None
    
    def record_call(self) -> None:
        self.call_count += 1
        self.last_called = datetime.now(timezone.utc)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.name,
            "calls": self.call_count,
            "last_called": self.last_called.isoformat() if self.last_called else None,
        }


class StatsCollector:
    """Global stats collector singleton."""
    
    _instance: "StatsCollector | None" = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "StatsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._start_time = datetime.now(timezone.utc)
        self._services: dict[str, ServiceStats] = {}
        self._endpoints: dict[str, EndpointStats] = {}
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=50)
        self._lock = threading.Lock()
    
    @property
    def start_time(self) -> datetime:
        return self._start_time
    
    def get_service_stats(self, name: str) -> ServiceStats:
        """Get or create stats for a service."""
        with self._lock:
            if name not in self._services:
                self._services[name] = ServiceStats(name=name)
            return self._services[name]
    
    def get_endpoint_stats(self, name: str) -> EndpointStats:
        """Get or create stats for an endpoint."""
        with self._lock:
            if name not in self._endpoints:
                self._endpoints[name] = EndpointStats(name=name)
            return self._endpoints[name]
    
    def record_error(self, service: str, error: str, context: dict[str, Any] | None = None) -> None:
        """Record an error for debugging."""
        with self._lock:
            self._recent_errors.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "service": service,
                "error": error,
                "context": context or {},
            })
    
    def get_all_stats(self) -> dict[str, Any]:
        """Get comprehensive stats snapshot."""
        now = datetime.now(timezone.utc)
        uptime = now - self._start_time
        uptime_seconds = int(uptime.total_seconds())
        
        # Format uptime nicely
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_human = ""
        if days > 0:
            uptime_human += f"{days}d "
        if hours > 0 or days > 0:
            uptime_human += f"{hours}h "
        uptime_human += f"{minutes}m {seconds}s"
        
        # Total requests across all endpoints
        total_endpoint_calls = sum(e.call_count for e in self._endpoints.values())
        
        with self._lock:
            return {
                "server": {
                    "start_time": self._start_time.isoformat(),
                    "current_time": now.isoformat(),
                    "uptime_seconds": uptime_seconds,
                    "uptime_human": uptime_human.strip(),
                },
                "interactions": {
                    "total_api_calls": total_endpoint_calls,
                    "by_endpoint": [
                        e.to_dict() for e in sorted(
                            self._endpoints.values(),
                            key=lambda x: x.call_count,
                            reverse=True,
                        )
                    ],
                },
                "services": {
                    name: stats.to_dict()
                    for name, stats in self._services.items()
                },
                "recent_errors": list(self._recent_errors),
            }


def _format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


# Global instance
stats = StatsCollector()

