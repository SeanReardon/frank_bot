"""Integration tests for the meta routes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from meta.jobs import JobStatus
from server.app import create_starlette_app


@pytest.fixture
def client(monkeypatch):
    """Create a test client for the Starlette app."""
    # Most tests assume meta endpoints are unauthenticated unless explicitly testing auth.
    monkeypatch.delenv("ACTIONS_API_KEY", raising=False)
    from config import get_settings

    get_settings.cache_clear()
    app = create_starlette_app()
    return TestClient(app)


@pytest.fixture
def tmp_data_dirs(tmp_path, monkeypatch):
    """Set up temporary directories for scripts and jobs."""
    scripts_dir = tmp_path / "scripts"
    jobs_dir = tmp_path / "jobs"
    scripts_dir.mkdir()
    jobs_dir.mkdir()

    # Patch the default directories
    monkeypatch.setattr("meta.scripts.DEFAULT_SCRIPTS_DIR", scripts_dir)
    monkeypatch.setattr("meta.jobs.DEFAULT_JOBS_DIR", jobs_dir)
    monkeypatch.setattr("meta.executor.DEFAULT_SCRIPTS_DIR", scripts_dir)
    monkeypatch.setattr("meta.executor.DEFAULT_JOBS_DIR", jobs_dir)

    return {"scripts": scripts_dir, "jobs": jobs_dir}


class TestGetMeta:
    """Tests for GET /frank/meta endpoint."""

    def test_get_meta_returns_markdown(self, client):
        """Test that GET /frank/meta returns markdown documentation."""
        response = client.get("/frank/meta")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "# FrankAPI Documentation" in response.text

    def test_get_meta_contains_services(self, client):
        """Test that documentation includes all services."""
        response = client.get("/frank/meta")

        assert "frank.calendar" in response.text
        assert "frank.contacts" in response.text
        assert "frank.sms" in response.text
        assert "frank.swarm" in response.text
        assert "frank.ups" in response.text
        assert "frank.time" in response.text

    def test_get_meta_contains_execution_workflow(self, client):
        """Test that documentation includes execution workflow."""
        response = client.get("/frank/meta")

        assert "Execution Workflow" in response.text
        assert "/frank/script/task/start" in response.text
        assert "/frank/script/task/status" in response.text


class TestListScripts:
    """Tests for GET /frank/script/list endpoint."""

    def test_list_scripts_empty(self, client, tmp_data_dirs):
        """Test listing scripts when none exist."""
        response = client.get("/frank/script/list")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["scripts"] == []

    def test_list_scripts_with_scripts(self, client, tmp_data_dirs):
        """Test listing scripts when some exist."""
        scripts_dir = tmp_data_dirs["scripts"]

        # Create a test script
        script_content = '''"""Test script for finding hotels.

Parameters:
    city (str): The city to search
"""

def main(frank, city="Austin"):
    return {"city": city}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-find-hotels.py"
        script_file.write_text(script_content)

        response = client.get("/frank/script/list")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["scripts"][0]["slug"] == "find-hotels"
        assert data["scripts"][0]["description"] == "Test script for finding hotels."
        assert len(data["scripts"][0]["parameters"]) == 1


class TestGetScript:
    """Tests for GET /frank/script/get endpoint."""

    def test_get_script_not_found(self, client, tmp_data_dirs):
        """Test getting a non-existent script."""
        response = client.get(
            "/frank/script/get",
            params={"script_id": "nonexistent-script"},
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_get_script_success(self, client, tmp_data_dirs):
        """Test getting an existing script."""
        scripts_dir = tmp_data_dirs["scripts"]

        script_content = '''"""Test script."""

def main(frank):
    return {"done": True}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-test-script.py"
        script_file.write_text(script_content)

        response = client.get(
            "/frank/script/get",
            params={"script_id": "2024-01-15T10-30-00Z-test-script"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["script_id"] == "2024-01-15T10-30-00Z-test-script"
        assert "def main(frank)" in data["code"]


class TestTaskStart:
    """Tests for POST /frank/script/task/start endpoint."""

    def test_task_start_missing_params(self, client, tmp_data_dirs):
        """Test task start with missing required parameters."""
        response = client.post("/frank/script/task/start", json={})

        assert response.status_code == 400
        assert "script_id" in response.json()["detail"].lower()

    def test_task_start_new_script(self, client, tmp_data_dirs):
        """Test executing a new script."""
        code = '''"""New test script."""

def main(frank, value=10):
    return {"result": value * 2}
'''
        response = client.post(
            "/frank/script/task/start",
            json={
                "slug": "double-value",
                "code": code,
                "params": {"value": 5},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "running"
        assert "double-value" in data["script_id"]

    def test_task_start_existing_script(self, client, tmp_data_dirs):
        """Test executing an existing script."""
        scripts_dir = tmp_data_dirs["scripts"]

        script_content = '''"""Existing test script."""

def main(frank, multiplier=1):
    return {"result": 42 * multiplier}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-existing-script.py"
        script_file.write_text(script_content)

        response = client.post(
            "/frank/script/task/start",
            json={
                "script_id": "2024-01-15T10-30-00Z-existing-script",
                "params": {"multiplier": 2},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "running"

    def test_task_start_nonexistent_script(self, client, tmp_data_dirs):
        """Test executing a non-existent script."""
        response = client.post(
            "/frank/script/task/start",
            json={"script_id": "nonexistent-script"},
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


class TestListTasks:
    """Tests for GET /frank/script/task/list endpoint."""

    def test_list_tasks_empty(self, client, tmp_data_dirs):
        """Test listing tasks when none exist."""
        response = client.get("/frank/script/task/list")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["tasks"] == []

    def test_list_tasks_with_tasks(self, client, tmp_data_dirs):
        """Test listing tasks after execution."""
        scripts_dir = tmp_data_dirs["scripts"]

        script_content = '''"""Test script."""

def main(frank):
    return {"done": True}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-test-script.py"
        script_file.write_text(script_content)

        # Start a task to create a job record
        client.post(
            "/frank/script/task/start",
            json={"script_id": "2024-01-15T10-30-00Z-test-script"},
        )

        # Wait a moment for the job record to be created
        time.sleep(0.1)

        response = client.get("/frank/script/task/list")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert "task_id" in data["tasks"][0]
        assert "status" in data["tasks"][0]

    def test_list_tasks_with_status_filter(self, client, tmp_data_dirs):
        """Test listing tasks with status filter."""
        response = client.get("/frank/script/task/list?status=running")

        assert response.status_code == 200
        data = response.json()
        # All returned tasks should have running status
        for task in data["tasks"]:
            assert task["status"] == "running"

    def test_list_tasks_invalid_status(self, client, tmp_data_dirs):
        """Test listing tasks with invalid status."""
        response = client.get("/frank/script/task/list?status=invalid")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


class TestTaskStatus:
    """Tests for GET /frank/script/task/status endpoint."""

    def test_task_status_not_found(self, client, tmp_data_dirs):
        """Test getting a non-existent task."""
        response = client.get(
            "/frank/script/task/status",
            params={"task_id": "nonexistent-job"},
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_task_status_success(self, client, tmp_data_dirs):
        """Test getting a task after execution."""
        scripts_dir = tmp_data_dirs["scripts"]

        script_content = '''"""Test script."""

def main(frank):
    return {"done": True}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-test-script.py"
        script_file.write_text(script_content)

        # Start a task to create a job record
        start_response = client.post(
            "/frank/script/task/start",
            json={"script_id": "2024-01-15T10-30-00Z-test-script"},
        )
        task_id = start_response.json()["task_id"]

        # Wait for completion
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = client.get(
                "/frank/script/task/status",
                params={"task_id": task_id},
            )
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "completed":
                    break
            time.sleep(0.1)

        response = client.get(
            "/frank/script/task/status",
            params={"task_id": task_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["job_id"] == task_id
        assert data["status"] == "completed"
        assert data["result"] == {"done": True}

    def test_task_status_includes_all_fields(self, client, tmp_data_dirs):
        """Test that task status includes all expected fields."""
        scripts_dir = tmp_data_dirs["scripts"]

        script_content = '''"""Test script with output."""

def main(frank, **kwargs):
    print("Hello from script")
    return {"value": 42}
'''
        script_file = scripts_dir / "2024-01-15T10-30-00Z-output-script.py"
        script_file.write_text(script_content)

        # Execute
        start_response = client.post(
            "/frank/script/task/start",
            json={
                "script_id": "2024-01-15T10-30-00Z-output-script",
                "params": {"test": "value"},
            },
        )
        task_id = start_response.json()["task_id"]

        # Wait for completion with longer timeout
        max_wait = 10
        start_time = time.time()
        data = None
        while time.time() - start_time < max_wait:
            response = client.get(
                "/frank/script/task/status",
                params={"task_id": task_id},
            )
            data = response.json()
            if data.get("status") == "completed":
                break
            time.sleep(0.2)

        # Check all expected fields
        assert data is not None
        assert "task_id" in data
        assert "job_id" in data
        assert "script_id" in data
        assert "status" in data
        assert "params" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "stdout" in data
        assert "stderr" in data
        assert "result" in data
        assert "error" in data

        # Check specific values - print data for debugging if failed
        if data["status"] != "completed":
            print(f"Job status: {data['status']}")
            print(f"Job error: {data.get('error')}")
            print(f"Job stderr: {data.get('stderr')}")
        assert data["status"] == "completed", f"Expected completed but got {data['status']}: {data.get('error')}"
        assert data["params"] == {"test": "value"}
        assert data["result"] == {"value": 42}
        # stdout should contain the printed message
        assert "Hello from script" in data["stdout"]


class TestApiKeyAuth:
    """Tests for API key authentication on meta endpoints."""

    def test_meta_endpoints_require_auth_when_configured(self, tmp_path, monkeypatch):
        """Test that meta endpoints require API key when configured."""
        # Set up temp dirs
        scripts_dir = tmp_path / "scripts"
        jobs_dir = tmp_path / "jobs"
        scripts_dir.mkdir()
        jobs_dir.mkdir()
        monkeypatch.setattr("meta.scripts.DEFAULT_SCRIPTS_DIR", scripts_dir)
        monkeypatch.setattr("meta.jobs.DEFAULT_JOBS_DIR", jobs_dir)

        # Configure API key
        monkeypatch.setenv("ACTIONS_API_KEY", "test-secret-key")

        # Need to reimport to pick up new settings
        from config import get_settings

        get_settings.cache_clear()

        app = create_starlette_app()
        client = TestClient(app)

        # Request without API key should fail
        response = client.get("/frank/meta")
        assert response.status_code == 401

        # Request with correct API key should succeed
        response = client.get(
            "/frank/meta",
            headers={"X-API-Key": "test-secret-key"},
        )
        assert response.status_code == 200

        # Clean up
        get_settings.cache_clear()
        monkeypatch.delenv("ACTIONS_API_KEY", raising=False)
