"""
Diagnostics action: service stats, API performance, and health info.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any

from services.platform_info import get_platform_diagnostics
from services.stats import stats

logger = logging.getLogger(__name__)

# Git commit hash baked into Docker image at build time
GIT_COMMIT = os.environ.get("GIT_COMMIT", "unknown")
GITHUB_REPO = "SeanReardon/frank_bot"


async def _check_android_status() -> dict[str, Any]:
    """Check Android device connectivity."""
    try:
        from services.android_client import AndroidClient
        client = AndroidClient()
        connected = await client.check_connection()
        if connected:
            info = await client.get_device_info()
            return {
                "status": "connected",
                "device": info.get("model", "unknown"),
                "android_version": info.get("android_version"),
            }
        return {"status": "disconnected"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_jorbs_status() -> dict[str, Any]:
    """Check jorbs storage status."""
    try:
        from services.jorb_storage import JorbStorage
        storage = JorbStorage()
        metrics = await storage.get_aggregate_metrics(status_filter="all")
        return {
            "status": "ok",
            "total": metrics.get("total_jorbs", 0),
            "by_status": metrics.get("by_status", {}),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_claudia_status() -> dict[str, Any]:
    """Check Claudia service connectivity."""
    try:
        from services.claudia_client import ClaudiaClient
        client = ClaudiaClient()
        repos = client.list_repos()
        return {
            "status": "connected",
            "repos_count": len(repos),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_scripts_status() -> dict[str, Any]:
    """Check script execution status."""
    try:
        from meta.jobs import list_jobs
        jobs = list_jobs()
        by_status = {}
        for job in jobs:
            s = job.status
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "status": "ok",
            "recent_tasks": len(jobs),
            "by_status": by_status,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _check_background_loop() -> dict[str, Any]:
    """Check background loop status."""
    try:
        from services.background_loop import get_background_loop_status
        return get_background_loop_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def health_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Quick health check. Returns OK if server is running.

    Use diagnosticsGet for detailed subsystem status.
    """
    all_stats = stats.get_all_stats()
    server = all_stats.get("server", {})
    return {
        "status": "ok",
        "uptime": server.get("uptime_human", "unknown"),
        "build": GIT_COMMIT[:7] if GIT_COMMIT != "unknown" else "dev",
    }


async def get_diagnostics_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Comprehensive diagnostics for all Frank Bot subsystems.

    Checks:
    - Server: uptime, memory, CPU
    - Android Phone: device connected?
    - Jorbs: task counts by status
    - Scripts: recent execution stats
    - Claudia: service connectivity
    - Background Loop: scheduler status
    - Services: Google, Swarm, Telnyx
    """
    all_stats = stats.get_all_stats()

    # Check all subsystems
    subsystems = {}
    subsystems["android_phone"] = await _check_android_status()
    subsystems["jorbs"] = await _check_jorbs_status()
    subsystems["scripts"] = await _check_scripts_status()
    subsystems["claudia"] = await _check_claudia_status()
    subsystems["background_loop"] = _check_background_loop()

    all_stats["subsystems"] = subsystems
    
    # Add system info
    all_stats["system"] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }
    
    # Add build info with git commit
    commit_url = None
    if GIT_COMMIT != "unknown":
        commit_url = f"https://github.com/{GITHUB_REPO}/commit/{GIT_COMMIT}"
    all_stats["build"] = {
        "git_commit": GIT_COMMIT,
        "git_commit_short": GIT_COMMIT[:7] if GIT_COMMIT != "unknown" else "unknown",
        "git_commit_url": commit_url,
    }
    
    # Add platform diagnostics
    all_stats["platform"] = get_platform_diagnostics()
    
    # Build a human-readable summary message
    server = all_stats["server"]
    interactions = all_stats["interactions"]
    services = all_stats.get("services", {})
    plat = all_stats.get("platform", {})
    
    build = all_stats["build"]
    lines = [
        f"🟢 Frank Bot running for {server['uptime_human']}",
        f"🏷️ Build: {build['git_commit_short']}",
        f"📊 Total API calls: {interactions['total_api_calls']}",
    ]
    
    # Platform summary
    host_info = plat.get("host", {})
    mem_info = plat.get("memory", {})
    cpu_info = plat.get("cpu", {})
    net_info = plat.get("network", {})
    proc_info = plat.get("process", {})
    
    # Host uptime
    if host_info.get("uptime_human"):
        lines.append(f"🖥️ Host uptime: {host_info['uptime_human']}")
    
    # Memory
    sys_mem = mem_info.get("system", {})
    proc_mem = proc_info.get("memory_rss", {})
    if sys_mem and proc_mem:
        lines.append(
            f"💾 Memory: {proc_mem.get('human', '?')} used by Frank "
            f"/ {sys_mem.get('used_human', '?')} system "
            f"({sys_mem.get('used_percent', 0)}% of {sys_mem.get('total_human', '?')})"
        )
    
    # CPU
    cpu_snap = cpu_info.get("snapshot", {})
    load = host_info.get("load_average", {})
    if cpu_snap or load:
        cpu_parts = []
        if cpu_snap:
            cpu_parts.append(f"{cpu_snap.get('busy_percent', 0)}% busy")
        if load:
            cpu_parts.append(f"load {load.get('1min', 0):.2f}/{load.get('5min', 0):.2f}/{load.get('15min', 0):.2f}")
        lines.append(f"⚡ CPU: {', '.join(cpu_parts)}")
    
    # Network
    if net_info.get("public_ip"):
        lines.append(f"🌐 Public IP: {net_info['public_ip']}")
    
    lines.append("")  # Blank line before services
    
    # Service stats
    service_icons = {
        "swarm": "🐝",
        "google_calendar": "📅",
        "google_contacts": "👥",
    }
    
    for name, svc in services.items():
        icon = service_icons.get(name, "🔌")
        req = svc["requests"]
        lat = svc["latency_ms"]
        line = (
            f"{icon} {name}: {req['total']} requests "
            f"({req['success_rate']} success), "
            f"avg {lat['avg']}ms"
        )
        if lat["max"] > 0:
            line += f", max {lat['max']}ms"
        if svc.get("bytes_received", 0) > 0:
            line += f", {svc['bytes_received_human']}"
        lines.append(line)
    
    # Recent errors summary
    errors = all_stats.get("recent_errors", [])
    if errors:
        lines.append(f"⚠️ {len(errors)} recent error(s) logged")
    else:
        lines.append("✅ No recent errors")

    # Subsystem status
    lines.append("")
    lines.append("📦 Subsystems:")
    sub_icons = {
        "android_phone": "📱",
        "jorbs": "🤖",
        "scripts": "📜",
        "claudia": "💻",
        "background_loop": "⏰",
    }
    for name, sub in subsystems.items():
        icon = sub_icons.get(name, "🔌")
        status = sub.get("status", "unknown")
        if status == "connected" or status == "ok":
            detail = ""
            if name == "android_phone" and sub.get("device"):
                detail = f" ({sub['device']})"
            elif name == "jorbs":
                by_status = sub.get("by_status", {})
                active = by_status.get("running", 0) + by_status.get("paused", 0)
                if active:
                    detail = f" ({active} active)"
            elif name == "claudia" and sub.get("repos_count"):
                detail = f" ({sub['repos_count']} repos)"
            lines.append(f"  {icon} {name}: ✅{detail}")
        elif status == "disconnected":
            lines.append(f"  {icon} {name}: ⚪ disconnected")
        else:
            err = sub.get("error", "")[:30] if sub.get("error") else ""
            lines.append(f"  {icon} {name}: ❌ {err}")

    all_stats["message"] = "\n".join(lines)

    return all_stats


__all__ = ["health_action", "get_diagnostics_action"]

