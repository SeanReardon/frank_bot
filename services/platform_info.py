"""
Platform diagnostics: system resources, container info, network.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any

import requests


def get_platform_diagnostics() -> dict[str, Any]:
    """Gather comprehensive platform diagnostics."""
    return {
        "host": _get_host_info(),
        "memory": _get_memory_info(),
        "cpu": _get_cpu_info(),
        "network": _get_network_info(),
        "process": _get_process_info(),
    }


def _get_host_info() -> dict[str, Any]:
    """Get host/system information."""
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
    }
    
    # System uptime from /proc/uptime
    try:
        uptime_str = Path("/proc/uptime").read_text().split()[0]
        uptime_seconds = int(float(uptime_str))
        info["uptime_seconds"] = uptime_seconds
        info["uptime_human"] = _format_duration(uptime_seconds)
    except Exception:
        info["uptime_seconds"] = None
        info["uptime_human"] = "unavailable"
    
    # Load average
    try:
        load_str = Path("/proc/loadavg").read_text()
        parts = load_str.split()
        info["load_average"] = {
            "1min": float(parts[0]),
            "5min": float(parts[1]),
            "15min": float(parts[2]),
        }
    except Exception:
        info["load_average"] = None
    
    return info


def _get_memory_info() -> dict[str, Any]:
    """Get memory utilization info."""
    info: dict[str, Any] = {}
    
    # System memory from /proc/meminfo
    try:
        meminfo = Path("/proc/meminfo").read_text()
        mem_data = {}
        for line in meminfo.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                # Parse value (usually in kB)
                val_parts = val.strip().split()
                if val_parts:
                    mem_data[key.strip()] = int(val_parts[0]) * 1024  # Convert to bytes
        
        total = mem_data.get("MemTotal", 0)
        available = mem_data.get("MemAvailable", 0)
        used = total - available
        
        info["system"] = {
            "total_bytes": total,
            "total_human": _format_bytes(total),
            "used_bytes": used,
            "used_human": _format_bytes(used),
            "available_bytes": available,
            "available_human": _format_bytes(available),
            "used_percent": round((used / total) * 100, 1) if total > 0 else 0,
        }
    except Exception:
        info["system"] = None
    
    # Container memory limit (cgroups v2 or v1)
    container_limit = None
    try:
        # Try cgroups v2 first
        cg_path = Path("/sys/fs/cgroup/memory.max")
        if cg_path.exists():
            val = cg_path.read_text().strip()
            if val != "max":
                container_limit = int(val)
        else:
            # Try cgroups v1
            cg_path = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            if cg_path.exists():
                val = int(cg_path.read_text().strip())
                # Check if it's actually limited (huge values mean unlimited)
                if val < 2**62:
                    container_limit = val
    except Exception:
        pass
    
    if container_limit:
        info["container_limit"] = {
            "bytes": container_limit,
            "human": _format_bytes(container_limit),
        }
    
    return info


def _get_cpu_info() -> dict[str, Any]:
    """Get CPU info and recent utilization."""
    info: dict[str, Any] = {}
    
    # CPU count
    try:
        info["cores"] = os.cpu_count()
    except Exception:
        info["cores"] = None
    
    # CPU times from /proc/stat (snapshot)
    try:
        stat = Path("/proc/stat").read_text()
        for line in stat.splitlines():
            if line.startswith("cpu "):
                parts = line.split()[1:]
                # user, nice, system, idle, iowait, irq, softirq, steal
                times = [int(x) for x in parts[:8]]
                total = sum(times)
                idle = times[3] + times[4]  # idle + iowait
                
                info["snapshot"] = {
                    "idle_percent": round((idle / total) * 100, 1) if total > 0 else 0,
                    "busy_percent": round(((total - idle) / total) * 100, 1) if total > 0 else 0,
                }
                break
    except Exception:
        info["snapshot"] = None
    
    return info


def _get_network_info() -> dict[str, Any]:
    """Get network information including public IP."""
    info: dict[str, Any] = {}
    
    # Local hostname/IP
    try:
        info["hostname"] = socket.gethostname()
        info["local_ip"] = socket.gethostbyname(socket.gethostname())
    except Exception:
        pass
    
    # Public IP (with timeout to avoid hanging)
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=3)
        if response.status_code == 200:
            info["public_ip"] = response.json().get("ip")
    except Exception:
        info["public_ip"] = "unavailable"
    
    return info


def _get_process_info() -> dict[str, Any]:
    """Get info about this process/container."""
    info: dict[str, Any] = {}
    
    # Process memory from /proc/self/status
    try:
        status = Path("/proc/self/status").read_text()
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                # Resident Set Size (actual memory in use)
                val = int(line.split()[1]) * 1024  # kB to bytes
                info["memory_rss"] = {
                    "bytes": val,
                    "human": _format_bytes(val),
                }
            elif line.startswith("VmSize:"):
                # Virtual memory size
                val = int(line.split()[1]) * 1024
                info["memory_virtual"] = {
                    "bytes": val,
                    "human": _format_bytes(val),
                }
            elif line.startswith("Threads:"):
                info["threads"] = int(line.split()[1])
    except Exception:
        pass
    
    # Process ID
    info["pid"] = os.getpid()
    
    # Open file descriptors
    try:
        fd_path = Path("/proc/self/fd")
        info["open_fds"] = len(list(fd_path.iterdir()))
    except Exception:
        pass
    
    return info


def _format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def _format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    
    return " ".join(parts)

