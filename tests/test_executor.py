"""Tests for the script executor module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meta.executor import (
    DEFAULT_TIMEOUT_SECONDS,
    ExecutionResult,
    execute_new_script,
    execute_script,
    execute_script_async,
)
from meta.jobs import JobStatus, get_job


class TestExecuteScript:
    """Tests for execute_script function."""

    def test_execute_simple_script(self):
        """Test executing a simple script that returns a value."""
        code = """
def main(frank):
    return {"result": "hello"}
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert result.result == {"result": "hello"}
        assert result.error is None

    def test_execute_script_with_params(self):
        """Test executing a script with keyword parameters."""
        code = """
def main(frank, name, count=1):
    return {"name": name, "count": count}
"""
        result = execute_script(code, params={"name": "Alice", "count": 5})

        assert result.status == JobStatus.COMPLETED
        assert result.result == {"name": "Alice", "count": 5}
        assert result.error is None

    def test_capture_stdout(self):
        """Test that print() output is captured in stdout."""
        code = """
def main(frank):
    print("Hello, world!")
    print("Line 2")
    return {"done": True}
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert "Hello, world!" in result.stdout
        assert "Line 2" in result.stdout
        assert result.result == {"done": True}

    def test_capture_stderr(self):
        """Test that stderr output is captured."""
        code = """
import sys

def main(frank):
    print("Error message", file=sys.stderr)
    return {"done": True}
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert "Error message" in result.stderr
        assert result.result == {"done": True}

    def test_execute_script_missing_main(self):
        """Test that missing main() function raises appropriate error."""
        code = """
def other_function():
    pass
"""
        result = execute_script(code)

        assert result.status == JobStatus.FAILED
        assert "main" in result.error.lower()

    def test_execute_script_main_not_callable(self):
        """Test that non-callable main raises appropriate error."""
        code = """
main = "not a function"
"""
        result = execute_script(code)

        assert result.status == JobStatus.FAILED
        assert "callable" in result.error.lower()

    def test_execute_script_syntax_error(self):
        """Test that syntax errors are caught and reported."""
        code = """
def main(frank)
    return {}  # Missing colon
"""
        result = execute_script(code)

        assert result.status == JobStatus.FAILED
        assert result.error is not None

    def test_execute_script_runtime_error(self):
        """Test that runtime errors are caught and reported."""
        code = """
def main(frank):
    x = 1 / 0  # ZeroDivisionError
    return {}
"""
        result = execute_script(code)

        assert result.status == JobStatus.FAILED
        assert "division" in result.error.lower() or "zero" in result.error.lower()

    def test_execute_script_with_frank_api(self):
        """Test that FrankAPI is passed to main()."""
        code = """
def main(frank):
    # Check that frank has expected namespaces
    has_calendar = hasattr(frank, 'calendar')
    has_contacts = hasattr(frank, 'contacts')
    has_swarm = hasattr(frank, 'swarm')
    return {
        "has_calendar": has_calendar,
        "has_contacts": has_contacts,
        "has_swarm": has_swarm,
    }
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert result.result == {
            "has_calendar": True,
            "has_contacts": True,
            "has_swarm": True,
        }

    def test_execute_script_timeout(self):
        """Test that long-running scripts timeout."""
        code = """
import time

def main(frank):
    time.sleep(10)  # Sleep longer than timeout
    return {"done": True}
"""
        # Use a very short timeout for testing
        result = execute_script(code, timeout_seconds=0.1)

        assert result.status == JobStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    def test_execute_script_returns_none(self):
        """Test that returning None works correctly."""
        code = """
def main(frank):
    pass  # Implicit None return
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert result.result is None
        assert result.error is None

    def test_execute_script_returns_list(self):
        """Test that returning a list works correctly."""
        code = """
def main(frank):
    return [1, 2, 3]
"""
        result = execute_script(code)

        assert result.status == JobStatus.COMPLETED
        assert result.result == [1, 2, 3]


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_execution_result_fields(self):
        """Test ExecutionResult has expected fields."""
        result = ExecutionResult(
            status=JobStatus.COMPLETED,
            stdout="output",
            stderr="",
            result={"key": "value"},
            error=None,
        )

        assert result.status == JobStatus.COMPLETED
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.result == {"key": "value"}
        assert result.error is None


class TestExecuteScriptAsync:
    """Tests for execute_script_async function."""

    def test_execute_script_async_creates_job(self, tmp_path):
        """Test that execute_script_async creates a job record."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"
        scripts_dir.mkdir()

        # Save a test script
        script_content = '''"""Test script."""

def main(frank):
    return {"done": True}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-test-script.py"
        script_file.write_text(script_content)

        job = execute_script_async(
            script_id="2024-01-15T10-30-00Z-test-script",
            params={"key": "value"},
            scripts_dir=scripts_dir,
            jobs_dir=jobs_dir,
        )

        assert job.job_id is not None
        assert job.script_id == "2024-01-15T10-30-00Z-test-script"
        assert job.status == JobStatus.RUNNING
        assert job.params == {"key": "value"}

    def test_execute_script_async_not_found(self, tmp_path):
        """Test that execute_script_async raises on missing script."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"
        scripts_dir.mkdir()

        with pytest.raises(ValueError, match="Script not found"):
            execute_script_async(
                script_id="nonexistent-script",
                scripts_dir=scripts_dir,
                jobs_dir=jobs_dir,
            )

    def test_execute_script_async_completes(self, tmp_path):
        """Test that execute_script_async updates job on completion."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"
        scripts_dir.mkdir()

        # Save a test script
        script_content = '''"""Test script."""

def main(frank):
    return {"result": 42}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-test-script.py"
        script_file.write_text(script_content)

        job = execute_script_async(
            script_id="2024-01-15T10-30-00Z-test-script",
            scripts_dir=scripts_dir,
            jobs_dir=jobs_dir,
        )

        # Wait for completion
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            completed_job = get_job(job.job_id, jobs_dir)
            if completed_job and completed_job.status == JobStatus.COMPLETED:
                break
            time.sleep(0.1)

        completed_job = get_job(job.job_id, jobs_dir)
        assert completed_job is not None
        assert completed_job.status == JobStatus.COMPLETED
        assert completed_job.result == {"result": 42}

    def test_execute_script_async_handles_error(self, tmp_path):
        """Test that execute_script_async updates job on error."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"
        scripts_dir.mkdir()

        # Save a script that raises an error
        script_content = '''"""Test script with error."""

def main(frank):
    raise RuntimeError("Test error")
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-error-script.py"
        script_file.write_text(script_content)

        job = execute_script_async(
            script_id="2024-01-15T10-30-00Z-error-script",
            scripts_dir=scripts_dir,
            jobs_dir=jobs_dir,
        )

        # Wait for completion
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            completed_job = get_job(job.job_id, jobs_dir)
            if completed_job and completed_job.status == JobStatus.FAILED:
                break
            time.sleep(0.1)

        completed_job = get_job(job.job_id, jobs_dir)
        assert completed_job is not None
        assert completed_job.status == JobStatus.FAILED
        assert "Test error" in completed_job.error


class TestExecuteNewScript:
    """Tests for execute_new_script function."""

    def test_execute_new_script_saves_and_runs(self, tmp_path):
        """Test that execute_new_script saves the script and runs it."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"

        code = '''"""New test script."""

def main(frank, multiplier=2):
    return {"value": 10 * multiplier}
'''
        job = execute_new_script(
            slug="new-test",
            code=code,
            params={"multiplier": 3},
            scripts_dir=scripts_dir,
            jobs_dir=jobs_dir,
        )

        assert job.job_id is not None
        assert job.status == JobStatus.RUNNING
        assert "new-test" in job.script_id

        # Verify script was saved
        script_files = list(scripts_dir.glob("*-new-test.py"))
        assert len(script_files) == 1

        # Wait for completion
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            completed_job = get_job(job.job_id, jobs_dir)
            if completed_job and completed_job.status == JobStatus.COMPLETED:
                break
            time.sleep(0.1)

        completed_job = get_job(job.job_id, jobs_dir)
        assert completed_job is not None
        assert completed_job.status == JobStatus.COMPLETED
        assert completed_job.result == {"value": 30}

    def test_execute_new_script_captures_output(self, tmp_path):
        """Test that execute_new_script captures stdout."""
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"

        code = '''"""Script with output."""

def main(frank):
    print("Debug info")
    return {"done": True}
'''
        job = execute_new_script(
            slug="output-test",
            code=code,
            scripts_dir=scripts_dir,
            jobs_dir=jobs_dir,
        )

        # Wait for completion
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            completed_job = get_job(job.job_id, jobs_dir)
            if completed_job and completed_job.status == JobStatus.COMPLETED:
                break
            time.sleep(0.1)

        completed_job = get_job(job.job_id, jobs_dir)
        assert completed_job is not None
        assert "Debug info" in completed_job.stdout


class TestDefaultTimeout:
    """Tests for default timeout constant."""

    def test_default_timeout_is_10_minutes(self):
        """Test that default timeout is 10 minutes (600 seconds)."""
        assert DEFAULT_TIMEOUT_SECONDS == 600
