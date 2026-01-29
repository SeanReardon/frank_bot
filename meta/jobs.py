"""
Job storage and management for Frank Bot meta module.

Jobs are stored as .json files in ./data/jobs/ directory with filenames
following the pattern: {ISO8601-timestamp}-{slug}-run.json

Job status values: pending, running, completed, failed, timeout
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# Default jobs directory - uses DATA_DIR env var if set (for Docker),
# otherwise falls back to relative path from project root
_data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
DEFAULT_JOBS_DIR = Path(_data_dir) / "jobs"


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Job:
    """Represents a job execution record."""

    job_id: str
    script_id: str
    status: JobStatus
    params: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert job to a JSON-serializable dict."""
        return {
            "job_id": self.job_id,
            "script_id": self.script_id,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "params": self.params,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Create a Job from a dict."""
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = JobStatus(status)
        return cls(
            job_id=data["job_id"],
            script_id=data["script_id"],
            status=status,
            params=data.get("params", {}),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            result=data.get("result"),
            error=data.get("error"),
        )


def generate_job_filename(slug: str, timestamp: datetime | None = None) -> str:
    """
    Generate a job filename from a slug and optional timestamp.

    Args:
        slug: The script slug (e.g., "my-script")
        timestamp: Optional datetime, defaults to now (UTC)

    Returns:
        Filename in format: {ISO8601-timestamp}-{slug}-run.json
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Format timestamp as filesystem-safe ISO8601 (replace : with -)
    ts_str = timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts_str}-{slug}-run.json"


def generate_job_id(slug: str, timestamp: datetime | None = None) -> str:
    """
    Generate a job ID from a slug and optional timestamp.

    Args:
        slug: The script slug
        timestamp: Optional datetime, defaults to now (UTC)

    Returns:
        Job ID in format: {ISO8601-timestamp}-{slug}-run
    """
    filename = generate_job_filename(slug, timestamp)
    return filename[:-5]  # Remove .json


def create_job(
    script_id: str,
    slug: str,
    params: dict[str, Any] | None = None,
    jobs_dir: Path | str | None = None,
    timestamp: datetime | None = None,
) -> Job:
    """
    Create a new job record.

    Args:
        script_id: The ID of the script being executed
        slug: The script slug (used in job filename)
        params: Parameters passed to the script
        jobs_dir: Directory to store jobs (defaults to ./data/jobs/)
        timestamp: Optional timestamp (defaults to now UTC)

    Returns:
        The created Job with status='pending'
    """
    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    # Ensure directory exists
    jobs_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    job_id = generate_job_id(slug, timestamp)
    started_at = timestamp.isoformat().replace("+00:00", "Z")

    job = Job(
        job_id=job_id,
        script_id=script_id,
        status=JobStatus.PENDING,
        params=params or {},
        started_at=started_at,
    )

    # Save to file
    filename = f"{job_id}.json"
    filepath = jobs_dir / filename
    filepath.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")

    return job


def update_job(
    job_id: str,
    status: JobStatus | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    result: Any = None,
    error: str | None = None,
    completed_at: str | None = None,
    jobs_dir: Path | str | None = None,
) -> Job | None:
    """
    Update a job's status and results.

    Args:
        job_id: The job ID to update
        status: New status (optional)
        stdout: Captured stdout (optional)
        stderr: Captured stderr (optional)
        result: Return value from script (optional)
        error: Error message (optional)
        completed_at: Completion timestamp (optional, auto-set if status is terminal)
        jobs_dir: Directory containing jobs (defaults to ./data/jobs/)

    Returns:
        The updated Job, or None if not found
    """
    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    filepath = jobs_dir / f"{job_id}.json"

    if not filepath.exists():
        return None

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        job = Job.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None

    # Update fields
    if status is not None:
        job.status = status

    if stdout is not None:
        job.stdout = stdout

    if stderr is not None:
        job.stderr = stderr

    if result is not None:
        job.result = result

    if error is not None:
        job.error = error

    # Auto-set completed_at for terminal statuses
    if completed_at is not None:
        job.completed_at = completed_at
    elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT):
        if job.completed_at is None:
            job.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Save updated job
    filepath.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")

    return job


def get_job(
    job_id: str,
    jobs_dir: Path | str | None = None,
) -> Job | None:
    """
    Get a job by ID.

    Args:
        job_id: The job ID to retrieve
        jobs_dir: Directory containing jobs (defaults to ./data/jobs/)

    Returns:
        The Job, or None if not found
    """
    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    filepath = jobs_dir / f"{job_id}.json"

    if not filepath.exists():
        return None

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return Job.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def list_jobs(
    jobs_dir: Path | str | None = None,
    status: JobStatus | None = None,
) -> list[Job]:
    """
    List all jobs, optionally filtered by status.

    Args:
        jobs_dir: Directory containing jobs (defaults to ./data/jobs/)
        status: Optional status filter

    Returns:
        List of Jobs sorted by started_at (newest first)
    """
    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    if not jobs_dir.exists():
        return []

    jobs: list[Job] = []

    for filename in os.listdir(jobs_dir):
        if not filename.endswith("-run.json"):
            continue

        filepath = jobs_dir / filename

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            job = Job.from_dict(data)

            # Apply status filter if specified
            if status is not None and job.status != status:
                continue

            jobs.append(job)
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    # Sort by started_at descending (newest first)
    jobs.sort(key=lambda j: j.started_at or "", reverse=True)
    return jobs


def job_to_summary_dict(job: Job) -> dict[str, Any]:
    """Convert a job to a summary dict (for listing)."""
    return {
        "job_id": job.job_id,
        "script_id": job.script_id,
        "status": job.status.value if isinstance(job.status, JobStatus) else job.status,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


__all__ = [
    "JobStatus",
    "Job",
    "generate_job_filename",
    "generate_job_id",
    "create_job",
    "update_job",
    "get_job",
    "list_jobs",
    "job_to_summary_dict",
    "DEFAULT_JOBS_DIR",
]
