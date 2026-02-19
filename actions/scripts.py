"""
Script management and execution actions for Frank Bot.

Provides a clean API for ChatGPT:
- frankScriptApiLearn - Learn what scripts can do (FrankAPI capabilities)
- frankScriptList/Create/Get/Update/Delete - CRUD on scripts
- frankScriptTaskStart/Status/Cancel - Async execution
"""

from __future__ import annotations

from typing import Any

from meta.api import (
    CalendarNamespace,
    ClaudiaNamespace,
    ContactsNamespace,
    DiagnosticsNamespace,
    EarshotNamespace,
    JorbsNamespace,
    SMSNamespace,
    StyleNamespace,
    SwarmNamespace,
    SystemNamespace,
    TelegramNamespace,
    TimeNamespace,
    UPSNamespace,
)
from meta.executor import execute_script_async, execute_new_script
from meta.jobs import JobStatus, get_job, list_jobs, update_job
from meta.scripts import (
    DEFAULT_SCRIPTS_DIR,
    get_script,
    list_scripts,
    save_script,
    script_metadata_to_dict,
)


def _get_namespace_info(namespace_class: type) -> dict[str, Any]:
    """Extract method info from a namespace class."""
    import inspect

    methods = []
    for name in dir(namespace_class):
        if name.startswith("_"):
            continue
        attr = getattr(namespace_class, name)
        if not callable(attr):
            continue

        # Get docstring
        doc = attr.__doc__ or ""
        # First paragraph as description
        desc_lines = []
        for line in doc.strip().split("\n"):
            stripped = line.strip()
            if not stripped or stripped.endswith(":"):
                break
            desc_lines.append(stripped)
        description = " ".join(desc_lines)

        # Get signature
        try:
            sig = inspect.signature(attr)
            params = []
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                if param.default is inspect.Parameter.empty:
                    params.append(pname)
                else:
                    params.append(f"{pname}={repr(param.default)}")
            signature = f"({', '.join(params)})"
        except Exception:
            signature = "()"

        methods.append({
            "name": name,
            "signature": signature,
            "description": description,
        })

    return {"methods": methods}


async def api_learn_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Learn the FrankAPI capabilities available to scripts.

    Call this FIRST before creating scripts. Returns comprehensive
    documentation about what scripts can access via the `frank` object.

    Scripts define a `main(frank, **params)` function that receives a
    FrankAPI instance. This endpoint documents all available namespaces
    and methods.

    Returns:
        overview: How scripts work
        namespaces: All available frank.* namespaces with their methods
        example_script: A complete working example
        execution_workflow: How to run scripts
        tips: Best practices
    """
    namespaces = {
        "calendar": {
            "description": "Google Calendar - events, scheduling, calendar list",
            **_get_namespace_info(CalendarNamespace),
            "examples": [
                "frank.calendar.events(day='2026-02-05')",
                "frank.calendar.events(time_min='2026-02-01', time_max='2026-02-28')",  # noqa: E501
                "frank.calendar.create(summary='Dinner', start='2026-02-05T19:00:00', end='2026-02-05T21:00:00')",  # noqa: E501
                "frank.calendar.list()  # list all calendars",
            ],
            "common_params": {
                "day": "YYYY-MM-DD for single day",
                "time_min/time_max": "ISO8601 for range",
                "calendar_name": "fuzzy match calendar name",
                "attendees": "list of email addresses",
            },
        },
        "contacts": {
            "description": "Google Contacts - search by name/email/phone",
            **_get_namespace_info(ContactsNamespace),
            "examples": [
                "frank.contacts.search('Mom')",
                "frank.contacts.search('john@example.com')",
                "frank.contacts.search('+1555', max_results=5)",
            ],
            "notes": "Fuzzy matching on name, email, phone. Returns full contact info.",  # noqa: E501
        },
        "sms": {
            "description": "SMS messaging via Telnyx (from Sean's number)",
            **_get_namespace_info(SMSNamespace),
            "examples": [
                "frank.sms.send('Mom', 'Running 10 min late!')",
                "frank.sms.send('+15551234567', 'Hello from Frank')",
            ],
            "notes": "Recipient can be contact name (auto-lookup) or phone number.",  # noqa: E501
        },
        "swarm": {
            "description": "Swarm/Foursquare check-in history and location data",
            **_get_namespace_info(SwarmNamespace),
            "examples": [
                "frank.swarm.checkins(year=2024)",
                "frank.swarm.checkins(category='restaurant', max_results=20)",
                "frank.swarm.checkins(with_companion='Lauren', year=2024)",
                "frank.swarm.checkins(after_date='2024-06-01', before_date='2024-06-30')",  # noqa: E501
            ],
            "categories": ["restaurant", "bar", "coffee", "hotel", "airport", "gym"],  # noqa: E501
            "common_params": {
                "year": "Filter by year (e.g., 2024)",
                "category": "Venue category",
                "with_companion": "Person's name",
                "has_photos": "Only checkins with photos",
                "include_photos": "Include photo URLs",
            },
        },
        "telegram": {
            "description": "Telegram messaging via Sean's personal account",
            **_get_namespace_info(TelegramNamespace),
            "examples": [
                "frank.telegram.send('@username', 'Hey!')",
                "frank.telegram.send('+15551234567', 'Hello')",
                "frank.telegram.messages('@friend', limit=10)",
                "frank.telegram.chats(limit=20)  # recent conversations",
            ],
            "notes": "Uses Sean's personal account, not a bot.",
        },
        "ups": {
            "description": "UPS battery/power status monitoring",
            **_get_namespace_info(UPSNamespace),
            "examples": ["frank.ups.status()"],
            "returns": "runtime, charge_percent, temperature",
        },
        "time": {
            "description": "Current time with timezone awareness",
            **_get_namespace_info(TimeNamespace),
            "examples": ["frank.time.now()"],
            "returns": "iso_time, timezone, offset_minutes",
        },
        "diagnostics": {
            "description": "System diagnostics and health checks",
            **_get_namespace_info(DiagnosticsNamespace),
            "examples": [
                "frank.diagnostics.full()  # comprehensive system diagnostics",
                "frank.diagnostics.health()  # quick health check",
            ],
            "returns": "Dict with server stats, subsystem status, build info",
        },
        "system": {
            "description": "System status, server info, and orchestration machinery",
            **_get_namespace_info(SystemNamespace),
            "examples": [
                "frank.system.status()  # orchestration machinery status",
                "frank.system.server()  # server uptime info",
                "frank.system.hello(name='Frank')",
            ],
        },
        "jorbs": {
            "description": "Jorb management - create, list, approve, cancel autonomous tasks",
            **_get_namespace_info(JorbsNamespace),
            "examples": [
                "frank.jorbs.list()  # open jorbs",
                "frank.jorbs.list(status='all')",
                "frank.jorbs.get('jorb_42', include_messages=True)",
                "frank.jorbs.create(name='Research flights', plan='Find cheapest SFO→NYC flights for March 15-20')",
                "frank.jorbs.approve('jorb_42', decision='go ahead')",
                "frank.jorbs.cancel('jorb_42', reason='no longer needed')",
                "frank.jorbs.stats()  # aggregate metrics",
                "frank.jorbs.brief(hours=24)  # activity summary",
                "frank.jorbs.messages('jorb_42', limit=20)",
            ],
            "common_params": {
                "jorb_id": "The jorb ID (e.g. 'jorb_42')",
                "status": "'open', 'closed', or 'all'",
            },
        },
        "claudia": {
            "description": "Claudia AI coding assistant - repo management, chat sessions, prompt execution",
            **_get_namespace_info(ClaudiaNamespace),
            "examples": [
                "frank.claudia.repos()  # list managed repos",
                "frank.claudia.chat_create('frank_bot', 'Fix login bug', message='The login page crashes on Safari')",
                "frank.claudia.chat_get(repo_id='repo_1', chat_id='chat_42')",
                "frank.claudia.chat_send(repo_id='repo_1', chat_id='chat_42', message='Try a different approach')",
                "frank.claudia.chat_end(repo_id='repo_1', chat_id='chat_42')",
                "frank.claudia.prompts(repo_id='repo_1')",
                "frank.claudia.prompt_execute(repo_id='repo_1', prompt_id='prompt_5')",
                "frank.claudia.queue(repo_id='repo_1')",
                "frank.claudia.executions(repo_id='repo_1', status='running')",
                "frank.claudia.execution_get(execution_id='exec_99')",
            ],
            "common_params": {
                "repo_id": "Repository ID",
                "repo_name": "Repository name (for chat_create)",
                "chat_id": "Chat session ID",
            },
        },
        "style": {
            "description": "Style guide generation from message analysis",
            **_get_namespace_info(StyleNamespace),
            "examples": [
                "frank.style.generate(dry_run=True)  # preview without sending",
                "frank.style.generate()  # generate and apply SEAN.md",
                "frank.style.generate(before_date='2026-01-01')",
            ],
            "common_params": {
                "dry_run": "If True, generate but don't send (default False)",
                "before_date": "Only analyze messages before this date (ISO 8601)",
            },
        },
        "earshot": {
            "description": "Earshot transcript search, LLM-powered queries, and analytics",
            **_get_namespace_info(EarshotNamespace),
            "examples": [
                "frank.earshot.search(q='meeting', limit=10)",
                "frank.earshot.search(since='2026-02-01', until='2026-02-19')",
                "frank.earshot.count(earliest='2026-01-01', latest='2026-02-19')",
                "frank.earshot.query(earliest='2026-02-01', latest='2026-02-19', prompt='Find action items and to-dos')",
                "frank.earshot.query(earliest='2026-01-01', latest='2026-02-19', prompt='Summarize discussions about home renovations', terms=['renovation', 'house'])",
                "frank.earshot.date_parse('last week')",
                "frank.earshot.get(42)  # get transcript by ID",
                "frank.earshot.dashboard()  # dashboard grid with standard query results",
                "frank.earshot.diagnostics()  # transcript count and system info",
            ],
            "common_params": {
                "earliest/latest": "Date range as YYYY-MM-DD",
                "prompt": "Natural language description of what to find/extract",
                "terms": "Optional keyword pre-filter (AND-matched before LLM)",
                "q": "Full-text search query for transcript search",
                "since/until": "Date filter for transcript search (YYYY-MM-DD or ISO 8601)",
            },
            "notes": (
                "query() blocks until LLM processing completes (30-60s for large ranges). "
                "For non-blocking use, call query_start() then poll query_results(). "
                "date_parse() converts natural language dates to YYYY-MM-DD ranges."
            ),
        },
    }

    return {
        "overview": (
            "Scripts are Python files with a main(frank, **params) function. "
            "The 'frank' object provides access to calendar, contacts, SMS, "
            "Swarm check-ins, Telegram, UPS status, time, diagnostics, "
            "system, jorbs, claudia (AI coding assistant), earshot "
            "(transcript search and LLM queries), and style. "
            "Scripts run async - you get a task_id and poll for results."
        ),
        "quick_start": (
            "To check tomorrow's calendar: write a script calling "
            "frank.calendar.events(day='2026-02-05'), start it with "
            "frankScriptTaskStart, then poll frankScriptTaskStatus."
        ),
        "namespaces": namespaces,
        "example_scripts": [
            {
                "name": "Get calendar events",
                "code": '''def main(frank, day):
    return frank.calendar.events(day=day)''',
                "params": {"day": "2026-02-05"},
            },
            {
                "name": "Send SMS",
                "code": '''def main(frank, recipient, message):
    return frank.sms.send(recipient, message)''',
                "params": {"recipient": "Mom", "message": "Running late!"},
            },
            {
                "name": "Find restaurants with companion",
                "code": '''def main(frank, companion, year=2024):
    result = frank.swarm.checkins(
        category="restaurant",
        with_companion=companion,
        year=year,
        max_results=50
    )
    return {
        "restaurants": [c["venue"]["name"] for c in result.get("checkins", [])],
        "count": len(result.get("checkins", []))
    }''',
                "params": {"companion": "Lauren", "year": 2024},
            },
        ],
        "execution_workflow": [
            "1. frankScriptTaskStart with slug+code (or script_id) + params",
            "2. Returns task_id immediately (status='running')",
            "3. frankScriptTaskStatus with task_id to poll",
            "4. When status='completed', result field has the return value",
        ],
        "tips": [
            "Can run inline: frankScriptTaskStart with slug+code+params",
            "No need to pre-create scripts for one-off tasks",
            "Scripts have 10-minute timeout",
            "Return dicts for structured results",
            "Use print() for debugging; captured in stdout",
        ],
    }


async def script_list_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List all saved scripts.

    Returns metadata for each script including description, parameters,
    and example from the docstring.
    """
    scripts = list_scripts()
    return {
        "count": len(scripts),
        "scripts": [script_metadata_to_dict(s) for s in scripts],
    }


async def script_create_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new script.

    Args:
        slug: Short identifier for the script (e.g., "find-restaurants")
        code: Python source code with main(frank, **params) function

    Returns:
        script_id: The full ID of the created script
        message: Confirmation message
    """
    args = arguments or {}

    slug = args.get("slug", "").strip()
    if not slug:
        raise ValueError("'slug' is required")

    code = args.get("code", "").strip()
    if not code:
        raise ValueError("'code' is required")

    if "def main(" not in code:
        raise ValueError("Script must define a main(frank, **params) function")

    script_id = save_script(slug, code)

    return {
        "script_id": script_id,
        "slug": slug,
        "message": f"Script '{slug}' created with ID: {script_id}",
    }


async def script_get_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get a script's source code.

    Args:
        script_id: The script ID (filename without .py)

    Returns:
        script_id: The script ID
        code: The Python source code
    """
    args = arguments or {}

    script_id = (args.get("script_id") or "").strip()
    # Backwards compat: some clients use `id`
    if not script_id:
        script_id = (args.get("id") or "").strip()
    if not script_id:
        raise ValueError("'script_id' is required")

    code = get_script(script_id)
    if code is None:
        raise ValueError(f"Script not found: {script_id}")

    return {
        "script_id": script_id,
        "code": code,
    }


async def script_update_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update an existing script's code.

    Args:
        script_id: The script ID to update
        code: New Python source code

    Returns:
        script_id: The script ID
        message: Confirmation message
    """
    args = arguments or {}

    script_id = (args.get("script_id") or "").strip()
    # Backwards compat: some clients use `id`
    if not script_id:
        script_id = (args.get("id") or "").strip()
    if not script_id:
        raise ValueError("'script_id' is required")

    code = args.get("code", "").strip()
    if not code:
        raise ValueError("'code' is required")

    if "def main(" not in code:
        raise ValueError("Script must define a main(frank, **params) function")

    # Check script exists
    scripts_dir = DEFAULT_SCRIPTS_DIR
    filepath = scripts_dir / f"{script_id}.py"
    if not filepath.exists():
        raise ValueError(f"Script not found: {script_id}")

    # Overwrite
    filepath.write_text(code, encoding="utf-8")

    return {
        "script_id": script_id,
        "message": f"Script '{script_id}' updated",
    }


async def script_delete_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Delete a script.

    Args:
        script_id: The script ID to delete

    Returns:
        script_id: The deleted script ID
        message: Confirmation message
    """
    args = arguments or {}

    script_id = (args.get("script_id") or "").strip()
    # Backwards compat: some clients use `id`
    if not script_id:
        script_id = (args.get("id") or "").strip()
    if not script_id:
        raise ValueError("'script_id' is required")

    scripts_dir = DEFAULT_SCRIPTS_DIR
    filepath = scripts_dir / f"{script_id}.py"
    if not filepath.exists():
        raise ValueError(f"Script not found: {script_id}")

    filepath.unlink()

    return {
        "script_id": script_id,
        "message": f"Script '{script_id}' deleted",
    }


async def task_start_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start executing a script (async - returns immediately).

    Args:
        script_id: ID of existing script to run, OR
        slug: Slug for a new script (requires 'code')
        code: Python code for a new script (requires 'slug')
        params: Parameters to pass to main()
        timeout: Timeout in seconds (default: 600 = 10 min)

    Returns:
        task_id: ID to use with frankScriptTaskStatus
        status: "running"
        script_id: The script being executed
    """
    args = arguments or {}

    script_id = args.get("script_id")
    script_id = script_id.strip() if script_id else None
    slug = args.get("slug")
    slug = slug.strip() if slug else None
    code = args.get("code")
    code = code.strip() if code else None
    params = args.get("params", {})
    timeout = int(args.get("timeout", 600))

    if script_id:
        # Execute existing script
        job = execute_script_async(
            script_id=script_id,
            params=params,
            timeout_seconds=timeout,
        )
    elif slug and code:
        # Save and execute new script
        job = execute_new_script(
            slug=slug,
            code=code,
            params=params,
            timeout_seconds=timeout,
        )
    else:
        raise ValueError(
            "Either 'script_id' (for existing) or 'slug'+'code' (for new) required"
        )

    status = job.status.value if isinstance(job.status, JobStatus) else job.status
    return {
        "task_id": job.job_id,
        "status": status,
        "script_id": job.script_id,
        "message": f"Task started. Poll frankScriptTaskStatus({job.job_id})",
    }


async def task_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the status and result of a script execution task.

    Args:
        task_id: The task ID from frankScriptTaskStart

    Returns:
        Task details including status, stdout, stderr, result, error.
        Status: pending, running, completed, failed, timeout
    """
    args = arguments or {}

    task_id = (args.get("task_id") or "").strip()
    # Backwards compat: some clients still send job_id
    if not task_id:
        task_id = (args.get("job_id") or "").strip()
    if not task_id:
        raise ValueError("'task_id' is required")

    job = get_job(task_id)
    if job is None:
        raise ValueError(f"Task not found: {task_id}")

    # Normalize response shape: API uses task_id, underlying storage uses job_id.
    data = job.to_dict()
    data["task_id"] = data.get("job_id")
    return data


async def task_list_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List recent script execution tasks.

    Args:
        status: Filter by status (pending, running, completed, failed, timeout)
        limit: Max tasks to return (default: 20)

    Returns:
        tasks: List of task summaries
        count: Number of tasks
    """
    args = arguments or {}

    status_str = args.get("status", "").strip() if args.get("status") else None
    limit = int(args.get("limit", 20))

    status_filter = None
    if status_str:
        try:
            status_filter = JobStatus(status_str)
        except ValueError:
            raise ValueError(
                f"Invalid status '{status_str}'. "
                "Valid: pending, running, completed, failed, timeout"
            )

    jobs = list_jobs(status=status_filter)[:limit]

    def _task_status(j):
        return j.status.value if isinstance(j.status, JobStatus) else j.status

    return {
        "count": len(jobs),
        "tasks": [
            {
                "task_id": j.job_id,
                "script_id": j.script_id,
                "status": _task_status(j),
                "started_at": j.started_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ],
    }


async def task_cancel_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Cancel a running script task.

    Note: Cancellation is best-effort. Running Python code may not stop
    immediately, but the task will be marked as failed.

    Args:
        task_id: The task ID to cancel

    Returns:
        task_id: The task ID
        status: New status (failed)
        message: Confirmation
    """
    args = arguments or {}

    task_id = (args.get("task_id") or "").strip()
    # Backwards compat: some clients still send job_id
    if not task_id:
        task_id = (args.get("job_id") or "").strip()
    if not task_id:
        raise ValueError("'task_id' is required")

    job = get_job(task_id)
    if job is None:
        raise ValueError(f"Task not found: {task_id}")

    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT):
        return {
            "task_id": task_id,
            "status": job.status.value,
            "message": f"Task already {job.status.value}, cannot cancel",
        }

    # Mark as failed (cancellation)
    update_job(
        task_id,
        status=JobStatus.FAILED,
        error="Cancelled by user",
    )

    return {
        "task_id": task_id,
        "status": "failed",
        "message": "Task cancellation requested",
    }


__all__ = [
    "api_learn_action",
    "script_list_action",
    "script_create_action",
    "script_get_action",
    "script_update_action",
    "script_delete_action",
    "task_start_action",
    "task_status_action",
    "task_list_action",
    "task_cancel_action",
]
