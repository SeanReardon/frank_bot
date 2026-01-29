"""
Script executor for Frank Bot meta module.

Provides script execution with timeout and output capture.
Scripts define a main(frank, **params) function that receives
a FrankAPI instance and keyword parameters.
"""

from __future__ import annotations

import io
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from meta.api import FrankAPI
from meta.jobs import (
    DEFAULT_JOBS_DIR,
    Job,
    JobStatus,
    create_job,
    get_job,
    update_job,
)
from meta.scripts import (
    DEFAULT_SCRIPTS_DIR,
    get_script,
    parse_script_filename,
    save_script,
)

# Default timeout: 10 minutes in seconds
DEFAULT_TIMEOUT_SECONDS = 600


@dataclass
class ExecutionResult:
    """Result of a script execution."""

    status: JobStatus
    stdout: str
    stderr: str
    result: Any
    error: str | None


def _capture_output(func: Callable[[], Any]) -> tuple[Any, str, str]:
    """
    Execute a function and capture its stdout and stderr.

    Args:
        func: The function to execute

    Returns:
        Tuple of (return_value, stdout, stderr)
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    try:
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        result = func()

        return result, captured_stdout.getvalue(), captured_stderr.getvalue()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def execute_script(
    code: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """
    Execute a script's main() function with timeout and output capture.

    The script must define a main(frank, **kwargs) function.
    FrankAPI is passed as the first argument, and params as keyword args.

    Args:
        code: The Python source code to execute
        params: Parameters to pass as keyword arguments to main()
        timeout_seconds: Maximum execution time (default: 600 = 10 minutes)

    Returns:
        ExecutionResult with status, stdout, stderr, result, and error
    """
    if params is None:
        params = {}

    # Prepare execution context
    frank = FrankAPI()
    global_namespace: dict[str, Any] = {"__name__": "__main__"}

    def _execute() -> Any:
        # Execute the script code to define main()
        exec(code, global_namespace)

        # Get the main function
        main_func = global_namespace.get("main")
        if main_func is None:
            raise ValueError("Script must define a main(frank, **params) function")

        if not callable(main_func):
            raise ValueError("main must be a callable function")

        # Call main with FrankAPI and params
        return main_func(frank, **params)

    # Execute with timeout in a thread pool
    executor = ThreadPoolExecutor(max_workers=1)

    try:
        future = executor.submit(_capture_output, _execute)
        try:
            result, stdout, stderr = future.result(timeout=timeout_seconds)
            return ExecutionResult(
                status=JobStatus.COMPLETED,
                stdout=stdout,
                stderr=stderr,
                result=result,
                error=None,
            )
        except FuturesTimeoutError:
            # Cancel the future (may not interrupt running code)
            future.cancel()
            return ExecutionResult(
                status=JobStatus.TIMEOUT,
                stdout="",
                stderr="",
                result=None,
                error=f"Script execution timed out after {timeout_seconds} seconds",
            )
        except Exception as exc:
            # Get the traceback
            tb_str = traceback.format_exc()
            return ExecutionResult(
                status=JobStatus.FAILED,
                stdout="",
                stderr=tb_str,
                result=None,
                error=str(exc),
            )
    finally:
        executor.shutdown(wait=False)


def execute_script_async(
    script_id: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    scripts_dir: Path | str | None = None,
    jobs_dir: Path | str | None = None,
) -> Job:
    """
    Execute an existing script asynchronously in a background thread.

    Creates a job record and starts execution immediately. The job is
    updated with results when execution completes, fails, or times out.

    Args:
        script_id: The ID of the script to execute
        params: Parameters to pass to main()
        timeout_seconds: Maximum execution time
        scripts_dir: Directory containing scripts
        jobs_dir: Directory for job storage

    Returns:
        The created Job with status='running'

    Raises:
        ValueError: If script not found
    """
    if scripts_dir is None:
        scripts_dir = DEFAULT_SCRIPTS_DIR
    else:
        scripts_dir = Path(scripts_dir)

    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    # Load the script
    code = get_script(script_id, scripts_dir)
    if code is None:
        raise ValueError(f"Script not found: {script_id}")

    # Parse script ID to get slug
    parsed = parse_script_filename(f"{script_id}.py")
    if parsed is None:
        slug = script_id  # Fall back to using ID as slug
    else:
        _, slug = parsed

    # Create job record
    job = create_job(
        script_id=script_id,
        slug=slug,
        params=params,
        jobs_dir=jobs_dir,
    )

    # Update job to running
    update_job(job.job_id, status=JobStatus.RUNNING, jobs_dir=jobs_dir)

    # Start background execution
    def _run_in_background():
        try:
            result = execute_script(code, params, timeout_seconds)
            update_job(
                job.job_id,
                status=result.status,
                stdout=result.stdout,
                stderr=result.stderr,
                result=result.result,
                error=result.error,
                jobs_dir=jobs_dir,
            )
        except Exception as exc:
            update_job(
                job.job_id,
                status=JobStatus.FAILED,
                error=f"Execution error: {exc}",
                jobs_dir=jobs_dir,
            )

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    # Return job with running status
    return Job(
        job_id=job.job_id,
        script_id=job.script_id,
        status=JobStatus.RUNNING,
        params=job.params,
        started_at=job.started_at,
    )


def execute_new_script(
    slug: str,
    code: str,
    params: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    scripts_dir: Path | str | None = None,
    jobs_dir: Path | str | None = None,
) -> Job:
    """
    Save a new script and execute it asynchronously.

    Saves the script with the given slug, then starts background execution.
    Returns immediately with a running job.

    Args:
        slug: The script slug (e.g., "find-restaurants")
        code: The Python source code
        params: Parameters to pass to main()
        timeout_seconds: Maximum execution time
        scripts_dir: Directory for script storage
        jobs_dir: Directory for job storage

    Returns:
        The created Job with status='running'
    """
    if scripts_dir is None:
        scripts_dir = DEFAULT_SCRIPTS_DIR
    else:
        scripts_dir = Path(scripts_dir)

    if jobs_dir is None:
        jobs_dir = DEFAULT_JOBS_DIR
    else:
        jobs_dir = Path(jobs_dir)

    # Save the script
    script_id = save_script(slug, code, scripts_dir)

    # Execute asynchronously
    return execute_script_async(
        script_id=script_id,
        params=params,
        timeout_seconds=timeout_seconds,
        scripts_dir=scripts_dir,
        jobs_dir=jobs_dir,
    )


__all__ = [
    "ExecutionResult",
    "execute_script",
    "execute_script_async",
    "execute_new_script",
    "DEFAULT_TIMEOUT_SECONDS",
]
