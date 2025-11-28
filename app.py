"""
Minimal entrypoint that wires the HTTP Actions server and logging.
"""

from __future__ import annotations

import logging
import sys

import uvicorn
from dotenv import load_dotenv

from frank_bot.config import get_settings
from frank_bot.http_app import create_starlette_app
from frank_bot.logging_config import configure_logging

load_dotenv()
settings = get_settings()
configure_logging(settings.log_file, settings.log_level)

logger = logging.getLogger(__name__)
logger.info("Environment variables loaded")
logger.info("Logging to file: %s", settings.log_file)
logger.info("Log level: %s", settings.log_level)

starlette_app = create_starlette_app()


def main():
    """Main entry point used by Python or other process managers."""
    logger.info("Starting Actions server...")
    logger.info(
        "Server will listen on %s:%s",
        settings.host,
        settings.port,
    )
    logger.info(
        "✓ Health check: http://%s:%s/health",
        settings.host,
        settings.port,
    )
    logger.info("Press Ctrl-C to shutdown gracefully")

    try:
        uvicorn.run(
            starlette_app,
            host=settings.host,
            port=settings.port,
            log_config=None,
        )
    except KeyboardInterrupt:
        logger.info("Shutdown signal received - shutting down gracefully...")
    except Exception:
        logger.exception("Unexpected error while running uvicorn")
        raise
    finally:
        logger.info("Actions server stopped")
        for handler in logging.root.handlers[:]:
            handler.flush()
            handler.close()
            logging.root.removeHandler(handler)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown complete.", file=sys.stderr)
        sys.exit(0)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        logging.shutdown()
