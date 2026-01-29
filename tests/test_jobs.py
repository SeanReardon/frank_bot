"""Unit tests for job storage and management."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta.jobs import (
    Job,
    JobStatus,
    create_job,
    generate_job_filename,
    generate_job_id,
    get_job,
    job_to_summary_dict,
    list_jobs,
    update_job,
)


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self):
        """All expected status values exist."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.TIMEOUT.value == "timeout"

    def test_status_from_string(self):
        """Status can be created from string."""
        assert JobStatus("pending") == JobStatus.PENDING
        assert JobStatus("completed") == JobStatus.COMPLETED


class TestJob:
    """Tests for Job dataclass."""

    def test_to_dict(self):
        """Job converts to dict correctly."""
        job = Job(
            job_id="2024-01-15T10-30-00Z-test-run",
            script_id="2024-01-15T10-00-00Z-test",
            status=JobStatus.COMPLETED,
            params={"city": "SF"},
            started_at="2024-01-15T10:30:00Z",
            completed_at="2024-01-15T10:31:00Z",
            stdout="Hello",
            stderr="",
            result={"hotels": []},
            error=None,
        )

        data = job.to_dict()

        assert data["job_id"] == "2024-01-15T10-30-00Z-test-run"
        assert data["script_id"] == "2024-01-15T10-00-00Z-test"
        assert data["status"] == "completed"
        assert data["params"] == {"city": "SF"}
        assert data["started_at"] == "2024-01-15T10:30:00Z"
        assert data["completed_at"] == "2024-01-15T10:31:00Z"
        assert data["stdout"] == "Hello"
        assert data["stderr"] == ""
        assert data["result"] == {"hotels": []}
        assert data["error"] is None

    def test_from_dict(self):
        """Job can be created from dict."""
        data = {
            "job_id": "2024-01-15T10-30-00Z-test-run",
            "script_id": "2024-01-15T10-00-00Z-test",
            "status": "running",
            "params": {"x": 1},
            "started_at": "2024-01-15T10:30:00Z",
        }

        job = Job.from_dict(data)

        assert job.job_id == "2024-01-15T10-30-00Z-test-run"
        assert job.script_id == "2024-01-15T10-00-00Z-test"
        assert job.status == JobStatus.RUNNING
        assert job.params == {"x": 1}
        assert job.started_at == "2024-01-15T10:30:00Z"
        assert job.completed_at is None
        assert job.stdout == ""
        assert job.stderr == ""
        assert job.result is None
        assert job.error is None


class TestGenerateJobFilename:
    """Tests for job filename generation."""

    def test_with_timestamp(self):
        """Filename is generated with provided timestamp."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        filename = generate_job_filename("my-script", ts)
        assert filename == "2024-01-15T10-30-00Z-my-script-run.json"

    def test_without_timestamp(self):
        """Filename uses current time when no timestamp provided."""
        filename = generate_job_filename("test")
        assert filename.endswith("-test-run.json")
        assert "T" in filename
        assert "Z" in filename


class TestGenerateJobId:
    """Tests for job ID generation."""

    def test_with_timestamp(self):
        """Job ID is generated correctly."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        job_id = generate_job_id("my-script", ts)
        assert job_id == "2024-01-15T10-30-00Z-my-script-run"


class TestCreateJob:
    """Tests for job creation."""

    def test_create_job(self):
        """Job is created with correct initial state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="2024-01-15T10-00-00Z-test",
                slug="test",
                params={"city": "SF"},
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            assert job.job_id == "2024-01-15T10-30-00Z-test-run"
            assert job.script_id == "2024-01-15T10-00-00Z-test"
            assert job.status == JobStatus.PENDING
            assert job.params == {"city": "SF"}
            assert job.started_at == "2024-01-15T10:30:00Z"
            assert job.completed_at is None

            # Verify file was created
            filepath = jobs_dir / "2024-01-15T10-30-00Z-test-run.json"
            assert filepath.exists()

    def test_create_job_no_params(self):
        """Job can be created without params."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=tmpdir,
                timestamp=ts,
            )

            assert job.params == {}

    def test_create_job_creates_directory(self):
        """Job creation creates directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir) / "nested" / "jobs"
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            assert jobs_dir.exists()
            assert (jobs_dir / f"{job.job_id}.json").exists()


class TestUpdateJob:
    """Tests for job updates."""

    def test_update_status(self):
        """Job status can be updated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            updated = update_job(
                job_id=job.job_id,
                status=JobStatus.RUNNING,
                jobs_dir=jobs_dir,
            )

            assert updated is not None
            assert updated.status == JobStatus.RUNNING

    def test_update_with_results(self):
        """Job can be updated with results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            updated = update_job(
                job_id=job.job_id,
                status=JobStatus.COMPLETED,
                stdout="Output text",
                stderr="Warning",
                result={"data": [1, 2, 3]},
                jobs_dir=jobs_dir,
            )

            assert updated is not None
            assert updated.status == JobStatus.COMPLETED
            assert updated.stdout == "Output text"
            assert updated.stderr == "Warning"
            assert updated.result == {"data": [1, 2, 3]}
            assert updated.completed_at is not None  # Auto-set

    def test_update_with_error(self):
        """Job can be updated with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            updated = update_job(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                error="KeyError: 'missing_key'",
                jobs_dir=jobs_dir,
            )

            assert updated is not None
            assert updated.status == JobStatus.FAILED
            assert updated.error == "KeyError: 'missing_key'"
            assert updated.completed_at is not None

    def test_update_timeout(self):
        """Timeout status auto-sets completed_at."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            updated = update_job(
                job_id=job.job_id,
                status=JobStatus.TIMEOUT,
                error="Script exceeded 10 minute timeout",
                jobs_dir=jobs_dir,
            )

            assert updated is not None
            assert updated.status == JobStatus.TIMEOUT
            assert updated.completed_at is not None

    def test_update_nonexistent_job(self):
        """Updating nonexistent job returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = update_job(
                job_id="nonexistent-job-id",
                status=JobStatus.RUNNING,
                jobs_dir=tmpdir,
            )

            assert result is None

    def test_update_persists_to_file(self):
        """Updates are persisted to the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            job = create_job(
                script_id="script-id",
                slug="test",
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            update_job(
                job_id=job.job_id,
                status=JobStatus.COMPLETED,
                result="success",
                jobs_dir=jobs_dir,
            )

            # Read from file
            filepath = jobs_dir / f"{job.job_id}.json"
            data = json.loads(filepath.read_text())

            assert data["status"] == "completed"
            assert data["result"] == "success"


class TestGetJob:
    """Tests for getting a job by ID."""

    def test_get_existing_job(self):
        """Existing job can be retrieved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

            created = create_job(
                script_id="script-id",
                slug="test",
                params={"x": 1},
                jobs_dir=jobs_dir,
                timestamp=ts,
            )

            retrieved = get_job(created.job_id, jobs_dir)

            assert retrieved is not None
            assert retrieved.job_id == created.job_id
            assert retrieved.script_id == "script-id"
            assert retrieved.params == {"x": 1}

    def test_get_nonexistent_job(self):
        """Getting nonexistent job returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_job("nonexistent-job-id", tmpdir)
            assert result is None


class TestListJobs:
    """Tests for listing jobs."""

    def test_list_empty(self):
        """Empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs = list_jobs(tmpdir)
            assert jobs == []

    def test_list_nonexistent_dir(self):
        """Nonexistent directory returns empty list."""
        jobs = list_jobs("/nonexistent/path")
        assert jobs == []

    def test_list_multiple_jobs(self):
        """Multiple jobs are listed and sorted by started_at."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)

            ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            ts2 = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
            ts3 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

            create_job("script-1", "test1", jobs_dir=jobs_dir, timestamp=ts1)
            create_job("script-2", "test2", jobs_dir=jobs_dir, timestamp=ts2)
            create_job("script-3", "test3", jobs_dir=jobs_dir, timestamp=ts3)

            jobs = list_jobs(jobs_dir)

            assert len(jobs) == 3
            # Should be sorted newest first
            assert jobs[0].script_id == "script-3"
            assert jobs[1].script_id == "script-2"
            assert jobs[2].script_id == "script-1"

    def test_list_filter_by_status(self):
        """Jobs can be filtered by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)

            ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            ts2 = datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

            job1 = create_job("script-1", "test1", jobs_dir=jobs_dir, timestamp=ts1)
            job2 = create_job("script-2", "test2", jobs_dir=jobs_dir, timestamp=ts2)

            # Update one to completed
            update_job(job1.job_id, status=JobStatus.COMPLETED, jobs_dir=jobs_dir)

            # Filter by status
            pending_jobs = list_jobs(jobs_dir, status=JobStatus.PENDING)
            completed_jobs = list_jobs(jobs_dir, status=JobStatus.COMPLETED)

            assert len(pending_jobs) == 1
            assert pending_jobs[0].job_id == job2.job_id

            assert len(completed_jobs) == 1
            assert completed_jobs[0].job_id == job1.job_id

    def test_list_ignores_invalid_files(self):
        """Invalid files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs_dir = Path(tmpdir)

            # Create valid job
            ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            create_job("script-1", "test", jobs_dir=jobs_dir, timestamp=ts)

            # Create invalid files
            (jobs_dir / "not-a-job.json").write_text("{}")
            (jobs_dir / "readme.txt").write_text("not json")
            (jobs_dir / "2024-01-15T10-00-00Z-invalid-run.json").write_text(
                "not valid json"
            )

            jobs = list_jobs(jobs_dir)

            assert len(jobs) == 1


class TestJobToSummaryDict:
    """Tests for job summary conversion."""

    def test_summary_dict(self):
        """Job converts to summary dict correctly."""
        job = Job(
            job_id="2024-01-15T10-30-00Z-test-run",
            script_id="script-id",
            status=JobStatus.RUNNING,
            params={"x": 1},
            started_at="2024-01-15T10:30:00Z",
            stdout="lots of output",
            stderr="warnings",
            result={"big": "data"},
        )

        summary = job_to_summary_dict(job)

        # Summary should only have key fields
        assert summary == {
            "job_id": "2024-01-15T10-30-00Z-test-run",
            "script_id": "script-id",
            "status": "running",
            "started_at": "2024-01-15T10:30:00Z",
            "completed_at": None,
        }

        # Full data should NOT be in summary
        assert "stdout" not in summary
        assert "stderr" not in summary
        assert "result" not in summary
        assert "params" not in summary
