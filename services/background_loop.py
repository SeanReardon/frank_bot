"""
Background Event Loop for Jorb System.

Orchestrates jorb event processing including:
- Telegram message listening via Telethon callback
- Processing debounced messages when timers fire
- Hourly heartbeat for stale jorb detection and scheduled actions
- Daily digest email at configured time
- Monthly Android device maintenance
- Weekly Android device health checks
- Graceful shutdown handling
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import datetime, timezone, time as dt_time, timedelta
from typing import Any

from services.agent_runner import AgentRunner
from services.context_reset import ContextResetService
from services.email_service import EmailService
from services.jorb_storage import JorbStorage
from services.telegram_jorb_router import (
    get_router_status,
    initialize_telegram_jorb_router,
    shutdown_telegram_jorb_router,
)
from services.telegram_bot_router import (
    get_bot_router_status,
    initialize_telegram_bot_router,
    shutdown_telegram_bot_router,
)

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds (1 hour)
HEARTBEAT_INTERVAL_SECONDS = 3600

# How often to check if it's digest time (in seconds)
DIGEST_CHECK_INTERVAL_SECONDS = 60

# How often to check scheduled maintenance tasks (in seconds)
MAINTENANCE_CHECK_INTERVAL_SECONDS = 3600  # Check hourly

# How often to tick due jorbs (in seconds)
WORKER_TICK_INTERVAL_SECONDS = 2


class BackgroundLoopService:
    """
    Service for running background tasks for the jorb system.

    Manages Telegram message listening, heartbeat checks, and daily digests.
    """

    def __init__(
        self,
        storage: JorbStorage | None = None,
        email_service: EmailService | None = None,
        context_reset_service: ContextResetService | None = None,
    ):
        """
        Initialize the background loop service.

        Args:
            storage: JorbStorage instance. Creates one if not provided.
            email_service: EmailService instance. Creates one if not provided.
            context_reset_service: ContextResetService instance. Creates one if not provided.
        """
        self._storage = storage or JorbStorage()
        self._email_service = email_service or EmailService()
        self._context_reset_service = context_reset_service or ContextResetService(
            storage=self._storage
        )

        self._running = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._digest_task: asyncio.Task[None] | None = None
        self._maintenance_task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._last_digest_date: str | None = None
        self._last_monthly_maintenance: str | None = None
        self._last_weekly_health_check: str | None = None
        self._started_at: str | None = None
        self._last_tick_at: str | None = None

    @property
    def is_running(self) -> bool:
        """Check if the background loop is running."""
        return self._running

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the background loop.

        Returns:
            Dict with status information
        """
        return {
            "status": "ok" if self._running else "stopped",
            "running": self._running,
            "started_at": self._started_at,
            "last_tick_at": self._last_tick_at,
            "telegram_router": get_router_status(),
            "telegram_bot_router": get_bot_router_status(),
            "heartbeat_task_running": (
                self._heartbeat_task is not None and not self._heartbeat_task.done()
            ),
            "digest_task_running": (
                self._digest_task is not None and not self._digest_task.done()
            ),
            "maintenance_task_running": (
                self._maintenance_task is not None and not self._maintenance_task.done()
            ),
            "worker_task_running": (
                self._worker_task is not None and not self._worker_task.done()
            ),
            "last_digest_date": self._last_digest_date,
            "last_monthly_maintenance": self._last_monthly_maintenance,
            "last_weekly_health_check": self._last_weekly_health_check,
            "context_reset_status": self._context_reset_service.get_reset_status()
            if self._context_reset_service.is_configured
            else None,
        }

    async def start(self) -> None:
        """
        Start the background loop.

        Initializes:
        - Telegram message listening
        - Hourly heartbeat task
        - Daily digest task
        - Signal handlers for graceful shutdown
        """
        if self._running:
            logger.warning("Background loop already running")
            return

        logger.info("Starting jorb background loop...")

        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._last_tick_at = self._started_at
        self._shutdown_event = asyncio.Event()

        # Initialize Telegram router for message listening
        telegram_initialized = await initialize_telegram_jorb_router()
        if telegram_initialized:
            logger.info("Telegram message router initialized")
        else:
            logger.warning(
                "Telegram router not initialized (may not be configured)"
            )

        # Initialize Telegram *bot* router for inbound messages to @Seans_frank_bot
        bot_initialized = await initialize_telegram_bot_router()
        if bot_initialized:
            logger.info("Telegram bot router initialized")
        else:
            logger.warning(
                "Telegram bot router not initialized (may not be configured)"
            )

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name="jorb-heartbeat",
        )
        logger.info("Heartbeat task started")

        # Start digest check task
        self._digest_task = asyncio.create_task(
            self._digest_loop(),
            name="jorb-digest",
        )
        logger.info("Digest task started")

        # Start Android maintenance task
        self._maintenance_task = asyncio.create_task(
            self._maintenance_loop(),
            name="android-maintenance",
        )
        logger.info("Android maintenance task started")

        # Start worker tick loop for scheduled wakes / long-running tasks
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name="jorb-worker",
        )
        logger.info("Worker tick task started")

        # Register signal handlers
        self._register_signal_handlers()

        logger.info("Jorb background loop started successfully")

    async def stop(self) -> None:
        """
        Stop the background loop gracefully.

        Stops all background tasks and cleans up resources.
        """
        if not self._running:
            logger.debug("Background loop not running")
            return

        logger.info("Stopping jorb background loop...")

        self._running = False

        # Signal shutdown
        if self._shutdown_event:
            self._shutdown_event.set()

        # Cancel background tasks
        await self._cancel_task(self._heartbeat_task, "heartbeat")
        await self._cancel_task(self._digest_task, "digest")
        await self._cancel_task(self._maintenance_task, "maintenance")
        await self._cancel_task(self._worker_task, "worker")

        # Shutdown Telegram router
        await shutdown_telegram_jorb_router()
        await shutdown_telegram_bot_router()

        logger.info("Jorb background loop stopped")

    async def _cancel_task(
        self,
        task: asyncio.Task[None] | None,
        name: str,
    ) -> None:
        """Cancel a task and wait for it to finish."""
        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.debug("%s task cancelled", name)

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self._handle_signal(sig)),
                )
                logger.debug("Registered signal handler for %s", sig.name)
            except (ValueError, OSError) as e:
                # Signal handlers may not work in all environments (e.g., Windows)
                logger.debug(
                    "Could not register signal handler for %s: %s",
                    sig.name,
                    e,
                )

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info("Received signal %s, initiating graceful shutdown", sig.name)
        await self.stop()

    async def _worker_loop(self) -> None:
        """
        Run the short-interval worker loop.

        This loop resumes jorbs that have scheduled a wake (`wake_at`) so the LLM
        can poll long-running tasks (Android/meta) and continue multi-step work
        without needing a human message.
        """
        runner = AgentRunner(storage=self._storage)

        async def _poll_android_task_if_awaiting(jorb) -> bool:
            awaiting = str(getattr(jorb, "awaiting", "") or "").strip()
            if not awaiting.startswith("android_task:"):
                return False

            task_id = awaiting.split(":", 1)[1].strip()
            if not task_id:
                return False

            meta = getattr(jorb, "metadata", {}) or {}
            try:
                poll_seconds = int(meta.get("android_poll_seconds") or 10)
            except (TypeError, ValueError):
                poll_seconds = 10
            poll_seconds = max(1, min(300, poll_seconds))

            from actions.android_phone import task_get_action

            success = True
            try:
                task = await task_get_action({"task_id": task_id})
            except Exception as exc:
                success = False
                task = {
                    "id": task_id,
                    "status": "error",
                    "error": str(exc),
                }

            await self._storage.add_script_result(
                jorb.id,
                {
                    "script": "android.task_get",
                    "result": task,
                    "success": success,
                },
            )

            status = str((task or {}).get("status") or "").strip().lower()
            if status in ("pending", "running"):
                wake_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=poll_seconds)).isoformat()
                await self._storage.update_jorb(
                    jorb.id,
                    awaiting=f"android_task:{task_id}",
                    wake_at=wake_at_iso,
                )
                return True

            # Terminal/error: for failures, proactively notify the human once with
            # the exact error, then clear awaiting. For success, let the LLM
            # interpret and summarize.
            if status in ("failed", "error", "not_found") or not success:
                try:
                    meta = getattr(jorb, "metadata", {}) or {}
                    last_notified = str(meta.get("last_android_task_terminal_notified") or "").strip()
                    if last_notified != task_id:
                        error = str((task or {}).get("error") or "").strip()
                        if error:
                            # Keep the message short but verbatim for debugging.
                            err_one_line = " ".join(error.split())
                            if len(err_one_line) > 400:
                                err_one_line = err_one_line[:400] + "..."

                            preferred = str(meta.get("preferred_transport") or "").strip()
                            preferred = preferred or ("telegram_bot" if meta.get("telegram_bot_chat_id") else "")
                            chat_id = str(meta.get("telegram_bot_chat_id") or "").strip() or None
                            recipient = jorb.contacts[0].identifier if getattr(jorb, "contacts", None) else None

                            text = (
                                f"Android diagnostics failed (task_id={task_id}): {err_one_line}\n\n"
                                "If you reconnect the phone/ADB, send another message and I’ll retry."
                            )
                            sent_ok = False
                            if preferred == "telegram_bot" and chat_id:
                                sent_ok = await runner._send_telegram_bot_message(chat_id=chat_id, text=text)
                                if sent_ok:
                                    await runner.store_outbound_message(
                                        jorb_id=jorb.id,
                                        channel="telegram_bot",
                                        recipient=recipient or f"chat_id:{chat_id}",
                                        content=text,
                                        reasoning="auto_task_failure",
                                    )
                            elif preferred == "telegram" and recipient:
                                sent_ok = await runner._send_message("telegram", recipient, text)
                                if sent_ok:
                                    await runner.store_outbound_message(
                                        jorb_id=jorb.id,
                                        channel="telegram",
                                        recipient=recipient,
                                        content=text,
                                        reasoning="auto_task_failure",
                                    )
                            elif preferred == "sms" and recipient:
                                sent_ok = await runner._send_message("sms", recipient, text)
                                if sent_ok:
                                    await runner.store_outbound_message(
                                        jorb_id=jorb.id,
                                        channel="sms",
                                        recipient=recipient,
                                        content=text,
                                        reasoning="auto_task_failure",
                                    )

                            if sent_ok:
                                runner._record_message_sent(jorb.id)
                                meta["last_android_task_terminal_notified"] = task_id
                                await self._storage.update_jorb(
                                    jorb.id, metadata_json=json.dumps(meta), awaiting=None, wake_at=None
                                )
                                return True
                except Exception:
                    logger.exception("Failed to auto-notify android task failure for jorb %s", jorb.id)

                await self._storage.update_jorb(jorb.id, awaiting=None, wake_at=None)
                return True

            await self._storage.update_jorb(jorb.id, awaiting=None, wake_at=None)
            refreshed = await self._storage.get_jorb(jorb.id) or jorb
            await runner.process_jorb_event(refreshed, event=None)
            return True

        async def _poll_meta_task_if_awaiting(jorb) -> bool:
            awaiting = str(getattr(jorb, "awaiting", "") or "").strip()
            if not awaiting.startswith("meta_task:"):
                return False

            task_id = awaiting.split(":", 1)[1].strip()
            if not task_id:
                return False

            meta = getattr(jorb, "metadata", {}) or {}
            try:
                poll_seconds = int(meta.get("meta_poll_seconds") or 5)
            except (TypeError, ValueError):
                poll_seconds = 5
            poll_seconds = max(1, min(60, poll_seconds))

            from meta.jobs import JobStatus, get_job

            job = await asyncio.to_thread(get_job, task_id)
            job_dict = job.to_dict() if job else {"job_id": task_id, "status": "not_found"}

            # Add stdout/stderr tail (TTY-like)
            stdout = str(job_dict.get("stdout") or "")
            stderr = str(job_dict.get("stderr") or "")
            job_dict["stdout_tail"] = stdout[-2000:]
            job_dict["stderr_tail"] = stderr[-2000:]
            job_dict["stdout_len"] = len(stdout)
            job_dict["stderr_len"] = len(stderr)

            await self._storage.add_script_result(
                jorb.id,
                {
                    "script": "meta.poll_task",
                    "result": job_dict,
                    "success": bool(job),
                },
            )

            status = str(job_dict.get("status") or "").strip().lower()
            if status in ("pending", "running") or (job and job.status == JobStatus.RUNNING):
                wake_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=poll_seconds)).isoformat()
                await self._storage.update_jorb(
                    jorb.id,
                    awaiting=f"meta_task:{task_id}",
                    wake_at=wake_at_iso,
                )
                return True

            await self._storage.update_jorb(jorb.id, awaiting=None, wake_at=None)
            refreshed = await self._storage.get_jorb(jorb.id) or jorb
            await runner.process_jorb_event(refreshed, event=None)
            return True

        while self._running and self._shutdown_event and not self._shutdown_event.is_set():
            self._last_tick_at = datetime.now(timezone.utc).isoformat()

            if not runner.is_configured:
                # If OpenAI isn't configured, there's nothing meaningful to do.
                await asyncio.sleep(max(5, WORKER_TICK_INTERVAL_SECONDS))
                continue

            try:
                due = await self._storage.list_due_jorbs(limit=25)
            except Exception as exc:
                logger.error("Worker loop failed to list due jorbs: %s", exc)
                await asyncio.sleep(5)
                continue

            if not due:
                await asyncio.sleep(WORKER_TICK_INTERVAL_SECONDS)
                continue

            for jorb in due:
                # Clear wake_at immediately to prevent duplicate processing
                try:
                    await self._storage.update_jorb(jorb.id, wake_at=None)
                except Exception:
                    logger.exception("Failed to clear wake_at for jorb %s", jorb.id)

                try:
                    # Fast-path: poll awaited long-running tasks without invoking the LLM
                    # on every poll tick. Only invoke the LLM once when the task reaches
                    # a terminal state so it can interpret results and message the human.
                    if await _poll_android_task_if_awaiting(jorb):
                        continue
                    if await _poll_meta_task_if_awaiting(jorb):
                        continue

                    await runner.process_jorb_event(jorb, event=None)
                except Exception:
                    logger.exception("Worker loop error processing jorb %s", jorb.id)

            # Yield between batches
            await asyncio.sleep(0)

    async def _heartbeat_loop(self) -> None:
        """
        Run the hourly heartbeat loop.

        Checks for:
        - Stale jorbs needing attention
        - Scheduled actions
        - Context reset needs
        """
        logger.info("Heartbeat loop starting, interval=%ds", HEARTBEAT_INTERVAL_SECONDS)

        while self._running:
            try:
                # Run heartbeat first, then sleep (ensures immediate first tick)
                await self._run_heartbeat()
                self._last_tick_at = datetime.now(timezone.utc).isoformat()

                if not self._running:
                    break

                # Wait for interval or shutdown
                if self._shutdown_event:
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=HEARTBEAT_INTERVAL_SECONDS,
                        )
                        # Shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        pass  # Timeout expired, loop again

            except asyncio.CancelledError:
                logger.debug("Heartbeat loop cancelled")
                break
            except Exception as e:
                logger.error("Error in heartbeat loop: %s", e, exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)  # Short delay before retry

        logger.info("Heartbeat loop stopped")

    async def _run_heartbeat(self) -> None:
        """Run a single heartbeat check."""
        logger.info("Running heartbeat check...")

        try:
            # Check for stale jorbs
            await self._check_stale_jorbs()

            # Check for context reset
            await self._check_context_reset()

            logger.info("Heartbeat check complete")

        except Exception as e:
            logger.error("Error during heartbeat: %s", e, exc_info=True)

    async def _check_stale_jorbs(self) -> None:
        """
        Check for stale jorbs and auto-pause them.

        A jorb is stale if it's been inactive for more than stale_jorb_hours.
        Also checks for expired jorbs that have exceeded max duration.
        """
        agent_runner = AgentRunner()

        try:
            # Check for stale jorbs (no recent activity)
            stale_ids = await agent_runner.check_stale_jorbs()
            if stale_ids:
                logger.info(
                    "Auto-paused %d stale jorb(s) in heartbeat check: %s",
                    len(stale_ids),
                    stale_ids,
                )

            # Check for expired jorbs (exceeded max duration)
            expired_ids = await agent_runner.check_expired_jorbs()
            if expired_ids:
                logger.info(
                    "Auto-failed %d expired jorb(s) in heartbeat check: %s",
                    len(expired_ids),
                    expired_ids,
                )

        except Exception as e:
            logger.error("Error checking stale/expired jorbs: %s", e)

    async def _check_context_reset(self) -> None:
        """Check if context reset is needed and perform if so."""
        if not self._context_reset_service.is_configured:
            logger.debug("Context reset service not configured, skipping check")
            return

        try:
            if self._context_reset_service.maybe_reset_context():
                logger.info("Context reset needed, performing reset...")
                handoff = await self._context_reset_service.perform_context_reset()
                logger.info(
                    "Context reset complete: %d jorbs processed",
                    len(handoff.jorb_handoffs),
                )

        except Exception as e:
            logger.error("Error during context reset: %s", e)

    async def _digest_loop(self) -> None:
        """
        Run the daily digest loop.

        Sends the daily digest at the configured time.
        """
        digest_time_str = EmailService.get_digest_time()
        logger.info("Digest loop starting, scheduled time=%s", digest_time_str)

        while self._running:
            try:
                # Check digest time first, then sleep (ensures immediate first check)
                await self._check_digest_time()

                if not self._running:
                    break

                # Wait for check interval or shutdown
                if self._shutdown_event:
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=DIGEST_CHECK_INTERVAL_SECONDS,
                        )
                        # Shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        pass  # Timeout expired, loop again

            except asyncio.CancelledError:
                logger.debug("Digest loop cancelled")
                break
            except Exception as e:
                logger.error("Error in digest loop: %s", e, exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)

        logger.info("Digest loop stopped")

    async def _check_digest_time(self) -> None:
        """Check if it's time to send the daily digest."""
        # Parse configured digest time
        digest_time_str = EmailService.get_digest_time()
        try:
            hour, minute = map(int, digest_time_str.split(":"))
            digest_time = dt_time(hour, minute)
        except (ValueError, AttributeError):
            logger.warning("Invalid digest time format: %s", digest_time_str)
            return

        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        # Check if we've already sent today's digest
        if self._last_digest_date == today_str:
            return

        # Check if it's digest time (within the check window)
        current_time = now.time()
        digest_time_utc = dt_time(digest_time.hour, digest_time.minute)

        # Compare hours and minutes
        if (
            current_time.hour == digest_time_utc.hour
            and current_time.minute >= digest_time_utc.minute
            and current_time.minute < digest_time_utc.minute + (DIGEST_CHECK_INTERVAL_SECONDS // 60) + 1
        ):
            logger.info("Digest time reached, sending daily digest...")
            await self._send_daily_digest()
            self._last_digest_date = today_str

    async def _send_daily_digest(self) -> None:
        """Send the daily digest email."""
        if not self._email_service.is_configured:
            logger.debug("Email service not configured, skipping digest")
            return

        try:
            # Get all jorbs with messages from the last 24 hours
            jorbs_with_messages = await self._storage.get_open_jorbs_with_messages()

            # Also get recently closed jorbs
            closed_jorbs = await self._storage.list_jorbs(status_filter="closed")

            # Filter to recent (last 24 hours) closed jorbs
            cutoff = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            recent_closed = []
            for jorb in closed_jorbs:
                if jorb.updated_at >= cutoff:
                    messages = await self._storage.get_messages(jorb.id)
                    from services.jorb_storage import JorbWithMessages
                    recent_closed.append(JorbWithMessages(jorb=jorb, messages=messages))

            # Combine all jorbs for digest
            all_jorbs = jorbs_with_messages + recent_closed

            if not all_jorbs:
                logger.info("No jorb activity for daily digest")
                # Still send empty digest for visibility
                all_jorbs = []

            success = await self._email_service.send_daily_digest(all_jorbs)

            if success:
                logger.info("Daily digest sent successfully")
            else:
                logger.warning("Failed to send daily digest")

        except Exception as e:
            logger.error("Error sending daily digest: %s", e, exc_info=True)

    async def _maintenance_loop(self) -> None:
        """
        Run the Android maintenance check loop.

        Checks for scheduled maintenance and health check times.
        """
        logger.info(
            "Android maintenance loop starting, interval=%ds",
            MAINTENANCE_CHECK_INTERVAL_SECONDS,
        )

        while self._running:
            try:
                # Check schedules first, then sleep (ensures immediate first check)
                await self._check_maintenance_schedules()

                if not self._running:
                    break

                # Wait for interval or shutdown
                if self._shutdown_event:
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=MAINTENANCE_CHECK_INTERVAL_SECONDS,
                        )
                        # Shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        pass  # Timeout expired, loop again

            except asyncio.CancelledError:
                logger.debug("Maintenance loop cancelled")
                break
            except Exception as e:
                logger.error("Error in maintenance loop: %s", e, exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)

        logger.info("Maintenance loop stopped")

    async def _check_maintenance_schedules(self) -> None:
        """Check if it's time for scheduled Android maintenance tasks."""
        from config import get_settings

        settings = get_settings()
        now = datetime.now(timezone.utc)

        # Check monthly maintenance (1st of month at configured time)
        await self._check_monthly_maintenance(
            now,
            settings.android_maintenance_cron,
        )

        # Check weekly health check (Sunday at configured time)
        await self._check_weekly_health_check(
            now,
            settings.android_health_check_cron,
        )

    def _parse_simple_cron(
        self,
        cron_str: str,
    ) -> tuple[int, int, int | None, int | None, int | None]:
        """
        Parse a simple cron string (minute hour day month weekday).

        Returns (minute, hour, day_of_month, month, day_of_week).
        None means "any" for that field.
        """
        parts = cron_str.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron format: {cron_str}")

        minute = int(parts[0]) if parts[0] != "*" else 0
        hour = int(parts[1]) if parts[1] != "*" else 0
        day_of_month = int(parts[2]) if parts[2] != "*" else None
        month = int(parts[3]) if parts[3] != "*" else None
        day_of_week = int(parts[4]) if parts[4] != "*" else None

        return (minute, hour, day_of_month, month, day_of_week)

    async def _check_monthly_maintenance(
        self,
        now: datetime,
        cron_str: str,
    ) -> None:
        """Check and run monthly maintenance if scheduled."""
        try:
            minute, hour, day_of_month, _, _ = self._parse_simple_cron(cron_str)
        except ValueError as e:
            logger.warning("Invalid maintenance cron: %s", e)
            return

        # Default to 1st of month if not specified
        day_of_month = day_of_month or 1

        # Check if we've already run this month
        month_key = now.strftime("%Y-%m")
        if self._last_monthly_maintenance == month_key:
            return

        # Check if it's the right day and hour
        if now.day != day_of_month:
            return

        if now.hour != hour:
            return

        # Within the check window for this minute
        if now.minute < minute or now.minute > minute + (MAINTENANCE_CHECK_INTERVAL_SECONDS // 60):
            return

        logger.info("Monthly Android maintenance time reached")
        await self._run_monthly_maintenance()
        self._last_monthly_maintenance = month_key

    async def _run_monthly_maintenance(self) -> None:
        """Execute monthly Android device maintenance."""
        from services.android_maintenance import get_android_maintenance_service
        from services.telegram_bot import TelegramBot

        logger.info("Running monthly Android maintenance...")

        maintenance = get_android_maintenance_service()
        telegram = TelegramBot()

        results: list[str] = []
        errors: list[str] = []

        # Check device connection first
        from services.android_client import get_android_client

        client = get_android_client()
        try:
            await client.connect()
            is_connected = await client.check_connection()
        except Exception as e:
            logger.warning("Android device not connected for maintenance: %s", e)
            if telegram.is_configured:
                await telegram.send_notification(
                    "📱 <b>Monthly Android Maintenance Skipped</b>\n\n"
                    "Device not connected. Will retry tomorrow.",
                    parse_mode="HTML",
                )
            return

        if not is_connected:
            logger.warning("Android device not responding for maintenance")
            if telegram.is_configured:
                await telegram.send_notification(
                    "📱 <b>Monthly Android Maintenance Skipped</b>\n\n"
                    "Device not responding. Will retry tomorrow.",
                    parse_mode="HTML",
                )
            return

        # Check security patch
        try:
            security_result = await maintenance.check_security_patch()
            if security_result.success:
                patch = security_result.details.get("security_patch") if security_result.details else "unknown"
                results.append(f"Security patch: {patch}")
            else:
                errors.append(f"Security check: {security_result.error}")
        except Exception as e:
            errors.append(f"Security check error: {e}")

        # Check for app updates (note: actual update requires LLM automation)
        try:
            update_result = await maintenance.check_app_updates()
            if update_result.success:
                results.append("Play Store launched for update check")
            else:
                errors.append(f"App update check: {update_result.error}")
        except Exception as e:
            errors.append(f"App update check error: {e}")

        # Check storage
        try:
            storage_result = await maintenance.get_storage_info()
            if storage_result.success:
                details = storage_result.details or {}
                results.append(
                    f"Storage: {details.get('used_percent', '?')}% used "
                    f"({details.get('free_formatted', '?')} free)"
                )
            else:
                errors.append(f"Storage check: {storage_result.error}")
        except Exception as e:
            errors.append(f"Storage check error: {e}")

        # Clear caches if storage is above 90%
        try:
            cache_result = await maintenance.clear_caches(threshold_percent=90.0)
            if cache_result.success:
                details = cache_result.details or {}
                if details.get("action_taken"):
                    results.append(f"Cleared cache for {details.get('apps_cleared', 0)} apps")
                else:
                    results.append("Cache clearing not needed (storage ok)")
        except Exception as e:
            errors.append(f"Cache clearing error: {e}")

        # Send summary via Telegram
        if telegram.is_configured:
            report_parts = [
                "📱 <b>Monthly Android Maintenance Report</b>",
                "",
            ]

            if results:
                report_parts.append("<b>Results:</b>")
                for r in results:
                    report_parts.append(f"• {r}")

            if errors:
                report_parts.append("")
                report_parts.append("<b>Issues:</b>")
                for e in errors:
                    report_parts.append(f"⚠️ {e}")

            report_parts.append("")
            report_parts.append(f"<i>Completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>")

            await telegram.send_notification(
                "\n".join(report_parts),
                parse_mode="HTML",
            )

        logger.info(
            "Monthly maintenance complete: %d results, %d errors",
            len(results),
            len(errors),
        )

    async def _check_weekly_health_check(
        self,
        now: datetime,
        cron_str: str,
    ) -> None:
        """Check and run weekly health check if scheduled."""
        try:
            minute, hour, _, _, day_of_week = self._parse_simple_cron(cron_str)
        except ValueError as e:
            logger.warning("Invalid health check cron: %s", e)
            return

        # Default to Sunday (0) if not specified
        day_of_week = day_of_week if day_of_week is not None else 0

        # Check if we've already run this week
        week_key = now.strftime("%Y-W%W")
        if self._last_weekly_health_check == week_key:
            return

        # Check if it's the right day (0 = Monday in Python, but cron uses 0 = Sunday)
        # Convert: cron Sunday=0 -> Python weekday 6
        python_weekday = (day_of_week - 1) % 7 if day_of_week > 0 else 6
        if now.weekday() != python_weekday:
            return

        if now.hour != hour:
            return

        # Within the check window for this minute
        if now.minute < minute or now.minute > minute + (MAINTENANCE_CHECK_INTERVAL_SECONDS // 60):
            return

        logger.info("Weekly Android health check time reached")
        await self._run_weekly_health_check()
        self._last_weekly_health_check = week_key

    async def _run_weekly_health_check(self) -> None:
        """Execute weekly Android device health check."""
        from services.android_maintenance import get_android_maintenance_service
        from services.telegram_bot import TelegramBot

        logger.info("Running weekly Android health check...")

        maintenance = get_android_maintenance_service()
        telegram = TelegramBot()

        issues: list[str] = []

        # Check device connection
        from services.android_client import get_android_client

        client = get_android_client()
        is_connected = False

        try:
            await client.connect()
            is_connected = await client.check_connection()
        except Exception as e:
            issues.append(f"Connection error: {e}")

        if not is_connected:
            issues.append("Device not responding")

        if is_connected:
            # Check battery health
            try:
                battery_result = await maintenance.get_battery_health()
                if battery_result.success:
                    details = battery_result.details or {}
                    level = details.get("level_percent", "?")
                    health = details.get("health", "?")

                    # Alert if battery is low or health is poor
                    try:
                        level_int = int(str(level))
                        if level_int < 20:
                            issues.append(f"Battery low: {level}%")
                    except (ValueError, TypeError):
                        pass

                    # Health status 2 = "Good" in Android
                    if str(health) not in ("2", "Good", "good"):
                        issues.append(f"Battery health: {health}")
                else:
                    issues.append(f"Battery check failed: {battery_result.error}")
            except Exception as e:
                issues.append(f"Battery check error: {e}")

            # Check WiFi connectivity
            try:
                wifi_ssid = await client.get_wifi_ssid()
                if not wifi_ssid:
                    issues.append("WiFi not connected")
            except Exception as e:
                issues.append(f"WiFi check error: {e}")

            # Test app launch
            try:
                launch_result = await maintenance.test_app_launch("settings")
                if not launch_result.success:
                    issues.append(f"App launch test failed: {launch_result.error}")
            except Exception as e:
                issues.append(f"App launch test error: {e}")

        # Only send notification if there are issues
        if issues and telegram.is_configured:
            report_parts = [
                "⚠️ <b>Android Health Check - Issues Detected</b>",
                "",
            ]
            for issue in issues:
                report_parts.append(f"• {issue}")

            report_parts.append("")
            report_parts.append("<b>Suggested Actions:</b>")
            if "not responding" in str(issues).lower() or "connection" in str(issues).lower():
                report_parts.append("• Check if phone is on and connected to network")
                report_parts.append("• Verify ADB debugging is enabled")
            if "battery" in str(issues).lower():
                report_parts.append("• Charge the device")
            if "wifi" in str(issues).lower():
                report_parts.append("• Check WiFi connection on device")

            await telegram.send_notification(
                "\n".join(report_parts),
                parse_mode="HTML",
            )

            logger.warning(
                "Weekly health check found %d issue(s): %s",
                len(issues),
                issues,
            )
        else:
            logger.info("Weekly health check passed - no issues found")


# Module-level instance for app lifecycle integration
_background_service: BackgroundLoopService | None = None


async def start_background_loop() -> None:
    """
    Start the background loop service.

    Called during Starlette app startup.
    """
    global _background_service

    if _background_service is not None and _background_service.is_running:
        logger.warning("Background loop already started")
        return

    _background_service = BackgroundLoopService()
    await _background_service.start()


async def stop_background_loop() -> None:
    """
    Stop the background loop service.

    Called during Starlette app shutdown.
    """
    global _background_service

    if _background_service is None:
        return

    await _background_service.stop()
    _background_service = None


def get_background_loop_status() -> dict[str, Any]:
    """
    Get the current status of the background loop.

    Returns:
        Status dict or indication that loop is not running
    """
    global _background_service

    if _background_service is None:
        return {"running": False, "message": "Background loop not initialized"}

    return _background_service.get_status()


__all__ = [
    "BackgroundLoopService",
    "start_background_loop",
    "stop_background_loop",
    "get_background_loop_status",
]
