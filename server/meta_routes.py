"""
Starlette routes for Frank Bot meta module (script execution API).

These endpoints provide script management and execution capabilities:
- GET /frank/meta - API documentation
- GET /frank/scripts - List saved scripts
- GET /frank/scripts/{id} - Get script code
- POST /frank/execute - Execute a script
- GET /frank/jobs - List job executions
- GET /frank/jobs/{id} - Get job details
"""

from __future__ import annotations

import json
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from config import Settings
from meta.executor import execute_new_script, execute_script_async
from meta.introspection import generate_meta_documentation
from meta.jobs import Job, JobStatus, get_job, job_to_summary_dict, list_jobs
from meta.scripts import get_script, list_scripts, script_metadata_to_dict


def build_meta_routes(settings: Settings) -> list[Route]:
    """
    Return a list of Starlette Routes for the meta API.
    """

    async def _require_api_key(request: Request) -> JSONResponse | None:
        """Check API key if configured. Returns error response or None."""
        if not settings.actions_api_key:
            return None
        provided = request.headers.get("x-api-key")
        if provided != settings.actions_api_key:
            return JSONResponse(
                {"detail": "Missing or invalid X-API-Key header"},
                status_code=401,
            )
        return None

    async def _read_json_body(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        """Read and parse JSON body from request. Returns (payload, error)."""
        try:
            body = await request.body()
        except Exception as exc:
            return None, JSONResponse({"detail": str(exc)}, status_code=400)

        if not body:
            return {}, None
        try:
            return json.loads(body.decode()), None
        except json.JSONDecodeError:
            return None, JSONResponse({"detail": "Invalid JSON payload"}, status_code=400)

    # GET /frank/meta - Return API documentation
    async def get_meta_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error
        documentation = generate_meta_documentation()
        return PlainTextResponse(documentation, media_type="text/markdown")

    # GET /frank/scripts - List all scripts
    async def list_scripts_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error
        scripts = list_scripts()
        return JSONResponse({
            "count": len(scripts),
            "scripts": [script_metadata_to_dict(s) for s in scripts],
        })

    # GET /frank/scripts/{id} - Get a specific script's code
    async def get_script_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error
        script_id = request.path_params["script_id"]
        code = get_script(script_id)
        if code is None:
            return JSONResponse(
                {"detail": f"Script not found: {script_id}"},
                status_code=404,
            )
        return PlainTextResponse(code, media_type="text/x-python")

    # POST /frank/execute - Execute a script
    async def execute_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error

        payload, parse_error = await _read_json_body(request)
        if parse_error:
            return parse_error

        # Either script_id (for existing) or slug+code (for new script)
        script_id = payload.get("script_id")
        slug = payload.get("slug")
        code = payload.get("code")
        params = payload.get("params", {})

        if script_id:
            # Execute existing script
            try:
                job = execute_script_async(
                    script_id=script_id,
                    params=params,
                )
            except ValueError as exc:
                return JSONResponse({"detail": str(exc)}, status_code=404)
        elif slug and code:
            # Save and execute new script
            job = execute_new_script(
                slug=slug,
                code=code,
                params=params,
            )
        else:
            return JSONResponse(
                {"detail": "Must provide either 'script_id' or both 'slug' and 'code'"},
                status_code=400,
            )

        return JSONResponse({
            "job_id": job.job_id,
            "script_id": job.script_id,
            "status": job.status.value,
            "started_at": job.started_at,
        })

    # GET /frank/jobs - List all jobs
    async def list_jobs_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error

        # Optional status filter
        status_filter = request.query_params.get("status")

        if status_filter:
            try:
                status = JobStatus(status_filter)
                jobs = list_jobs(status=status)
            except ValueError:
                return JSONResponse(
                    {"detail": f"Invalid status: {status_filter}. Valid values: pending, running, completed, failed, timeout"},
                    status_code=400,
                )
        else:
            jobs = list_jobs()

        return JSONResponse({
            "count": len(jobs),
            "jobs": [job_to_summary_dict(j) for j in jobs],
        })

    # GET /frank/jobs/{id} - Get a specific job
    async def get_job_handler(request: Request):
        auth_error = await _require_api_key(request)
        if auth_error:
            return auth_error
        job_id = request.path_params["job_id"]
        job = get_job(job_id)
        if job is None:
            return JSONResponse(
                {"detail": f"Job not found: {job_id}"},
                status_code=404,
            )
        return JSONResponse(job.to_dict())

    routes = [
        Route("/frank/meta", get_meta_handler, methods=["GET"]),
        Route("/frank/scripts", list_scripts_handler, methods=["GET"]),
        Route("/frank/scripts/{script_id:path}", get_script_handler, methods=["GET"]),
        Route("/frank/execute", execute_handler, methods=["POST"]),
        Route("/frank/jobs", list_jobs_handler, methods=["GET"]),
        Route("/frank/jobs/{job_id:path}", get_job_handler, methods=["GET"]),
    ]

    return routes


__all__ = ["build_meta_routes"]
