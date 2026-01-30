"""
Background Event Loop for Jorb System.

Orchestrates jorb event processing including:
- Telegram message listening via Telethon callback
- Processing debounced messages when timers fire
- Hourly heartbeat for stale jorb detection and scheduled actions
- Daily digest email at configured time
- Graceful shutdown handling
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone, time as dt_time
from typing import Any, Callable, Coroutine

from services.agent_runner import AgentRunner
from services.context_reset import ContextResetService
from services.email_service import EmailService
from services.jorb_storage import JorbStorage
from services.telegram_jorb_router import (
    get_router_status,
    initialize_telegram_jorb_router,
    shutdown_telegram_jorb_router,
)

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds (1 hour)
HEARTBEAT_INTERVAL_SECONDS = 3600

# How often to check if it's digest time (in seconds)
DIGEST_CHECK_INTERVAL_SECONDS = 60


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
        self._shutdown_event: asyncio.Event | None = None
        self._last_digest_date: str | None = None

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
            "running": self._running,
            "telegram_router": get_router_status(),
            "heartbeat_task_running": (
                self._heartbeat_task is not None and not self._heartbeat_task.done()
            ),
            "digest_task_running": (
                self._digest_task is not None and not self._digest_task.done()
            ),
            "last_digest_date": self._last_digest_date,
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
        self._shutdown_event = asyncio.Event()

        # Initialize Telegram router for message listening
        telegram_initialized = await initialize_telegram_jorb_router()
        if telegram_initialized:
            logger.info("Telegram message router initialized")
        else:
            logger.warning(
                "Telegram router not initialized (may not be configured)"
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

        # Shutdown Telegram router
        await shutdown_telegram_jorb_router()

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
                        pass  # Timeout expired, run heartbeat

                if not self._running:
                    break

                await self._run_heartbeat()

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
                        pass  # Timeout expired, check digest time

                if not self._running:
                    break

                await self._check_digest_time()

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
