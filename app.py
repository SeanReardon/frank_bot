"""
MCP Server - Hello World example
Model Context Protocol server for ChatGPT integration
"""
import json
import logging
import os
import sys
import time
from typing import Any, Sequence
from dotenv import load_dotenv

from asyncio import CancelledError

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

from camel_sse_transport import CamelCaseSseServerTransport

# Load environment variables first
load_dotenv()

# Configure detailed logging with both console and file handlers
LOG_FILE = os.getenv("LOG_FILE", "app.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - '
    '[%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL))

# Clear any existing handlers
root_logger.handlers.clear()

# Console handler (stderr/stdout)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(getattr(logging, LOG_LEVEL))
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
file_handler.setLevel(getattr(logging, LOG_LEVEL))
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)

logger.info("Environment variables loaded")
logger.info(f"Logging to file: {LOG_FILE}")
logger.info(f"Log level: {LOG_LEVEL}")

# Get port from environment or default to 8000
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Initialize the MCP server
mcp_server = Server("frank-bot")
logger.info("MCP server 'frank-bot' initialized")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """
    List available tools that the MCP server provides
    """
    logger.info("=== ChatGPT Request: list_tools() ===")
    tools = [
        Tool(
            name="hello_world",
            description="A simple hello world tool that greets the user",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The name to greet "
                            "(optional, defaults to 'World')"
                        ),
                    }
                },
            },
        ),
    ]
    response_data = {
        "request_type": "list_tools",
        "tools_count": len(tools),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ],
    }
    logger.info(
        f"=== ChatGPT Request (JSON) ===\n"
        f"{json.dumps(response_data, indent=2)}"
    )
    logger.info(f"Returning {len(tools)} tool(s)")
    return tools


@mcp_server.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, Any] | None
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """
    Handle tool calls from the MCP client
    """
    # Log the incoming request from ChatGPT in JSON format
    request_data = {
        "request_type": "call_tool",
        "tool_name": name,
        "arguments": arguments or {},
    }
    logger.info("=== ChatGPT Request: call_tool() ===")
    logger.info(
        f"=== ChatGPT Request (JSON) ===\n"
        f"{json.dumps(request_data, indent=2)}"
    )

    if name == "hello_world":
        # Always return "hello world" for testing
        message = "hello world"

        response_data = {
            "request_type": "call_tool",
            "tool_name": name,
            "response": message,
        }
        logger.info(
            f"=== Response to ChatGPT (JSON) ===\n"
            f"{json.dumps(response_data, indent=2)}"
        )

        return [
            TextContent(
                type="text",
                text=message,
            )
        ]
    else:
        error_data = {
            "request_type": "call_tool",
            "tool_name": name,
            "error": f"Unknown tool: {name}",
        }
        logger.error(
            f"=== Error Response (JSON) ===\n"
            f"{json.dumps(error_data, indent=2)}"
        )
        raise ValueError(f"Unknown tool: {name}")


# Note: uvicorn handles SIGINT/SIGTERM gracefully by default
# We don't need custom signal handlers that might interfere


# Create SSE transport
# The parameter should be just the message endpoint suffix, not the full path
# Since we Mount at /mcp and want messages at /mcp/messages, we use "/messages"
# Note: OpenAI Apps SDK expects /messages (plural) by convention
transport = CamelCaseSseServerTransport("/messages")


# Create Starlette app with SSE endpoint
# Use raw ASGI handler to avoid middleware conflicts with SSE responses
async def sse_endpoint_asgi(scope, receive, send):
    """Handle SSE connections for MCP protocol (raw ASGI)"""
    logger.debug("=== SSE Endpoint Called ===")
    logger.debug(f"Method: {scope.get('method')}")
    logger.debug(f"Path: {scope.get('path')}")

    try:
        # Use the transport's connect_sse which handles the ASGI interface
        logger.debug("Calling transport.connect_sse()...")
        async with transport.connect_sse(scope, receive, send) as (
            read_stream,
            write_stream
        ):
            logger.info("SSE connection established - streams ready")
            logger.debug("Running MCP server...")

            # Run the MCP server
            init_options = mcp_server.create_initialization_options()
            logger.debug(f"Initialization options: {init_options}")

            # mcp_server.run() processes messages from read_stream and writes
            # responses to write_stream. In SSE mode, JSON-RPC payloads arrive
            # via POST /mcp/messages with session IDs that the transport uses
            # to route everything to the correct session streams.
            await mcp_server.run(
                read_stream,
                write_stream,
                init_options
            )
            logger.info("MCP server run completed")

    except Exception as error:
        logger.error(
            "=== ERROR in SSE Endpoint ===",
            exc_info=True
        )
        logger.error(f"Error type: {type(error).__name__}")
        logger.error(f"Error message: {str(error)}")

        # Send error response if not already started
        try:
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"application/json"]],
            })
            await send({
                "type": "http.response.body",
                "body": json.dumps({
                    "error": str(error),
                    "type": type(error).__name__
                }).encode(),
            })
        except Exception as send_error:
            logger.error(f"Failed to send error response: {send_error}")


async def health_check(request):
    """Health check endpoint"""
    return JSONResponse({"status": "healthy", "server": "frank-bot"})


async def root_endpoint(request):
    """Root endpoint - handle discovery and MCP protocol requests"""
    # Try to get request body if it's a POST request
    body = None
    body_json = None
    if request.method == "POST":
        try:
            body = await request.body()
            if body:
                try:
                    body_json = json.loads(body.decode())
                    # Check if this is a JSON-RPC 2.0 message (MCP protocol)
                    if isinstance(body_json, dict) and "jsonrpc" in body_json:
                        logger.info(
                            "=== Detected JSON-RPC message at root ==="
                        )
                        logger.info(
                            f"JSON-RPC method: {body_json.get('method')}, "
                            f"id: {body_json.get('id')}"
                        )
                        # This is an MCP protocol message - route to handler
                        # We need to convert Starlette request to ASGI scope
                        # and handle it via the transport.
                        scope = request.scope
                        # Create a receive function that returns the body
                        # we already read
                        body_sent = False

                        async def receive():
                            nonlocal body_sent
                            if not body_sent:
                                body_sent = True
                                return {
                                    "type": "http.request",
                                    "body": body,
                                    "more_body": False,
                                }
                            return {
                                "type": "http.request",
                                "body": b"",
                                "more_body": False
                            }

                        # Create a send function to collect the response
                        response_status = None
                        response_headers = []
                        response_body = b""

                        async def send(message):
                            nonlocal response_status, response_headers
                            nonlocal response_body
                            if message["type"] == "http.response.start":
                                response_status = message["status"]
                                response_headers = message["headers"]
                            elif message["type"] == "http.response.body":
                                response_body += message.get("body", b"")

                        # Handle via transport's handle_post_message
                        logger.info(
                            "Routing JSON-RPC message to MCP handler..."
                        )
                        await transport.handle_post_message(
                            scope, receive, send
                        )

                        # Return the response
                        header_dict = dict(
                            (
                                k.decode() if isinstance(k, bytes) else k,
                                v.decode() if isinstance(v, bytes) else v
                            )
                            for k, v in response_headers
                        )
                        return Response(
                            content=response_body,
                            status_code=response_status or 200,
                            headers=header_dict,
                        )
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body = body.decode('utf-8', errors='replace')
        except Exception as e:
            logger.warning(f"Could not read request body: {e}")

    request_data = {
        "method": request.method,
        "path": str(request.url.path),
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "body": body_json or body,
    }
    logger.info("=== ChatGPT Request: Root Endpoint ===")
    logger.info(
        f"=== Request Details (JSON) ===\n"
        f"{json.dumps(request_data, indent=2, default=str)}"
    )

    # Return server information for GET requests or non-JSON-RPC POSTs
    return JSONResponse({
        "server": "frank-bot",
        "mcp_server": True,
        "endpoints": {
            "/mcp": "SSE endpoint for MCP protocol",
            "/health": "Health check endpoint",
        },
        "status": "running",
    })


async def messages_endpoint(request):
    body = await request.body()
    scope = dict(request.scope)
    raw_qs = scope.get("query_string", b"")
    if b"sessionId=" in raw_qs and b"session_id=" not in raw_qs:
        scope["query_string"] = raw_qs.replace(b"sessionId=", b"session_id=")

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    response_status = None
    response_headers = []
    response_body = b""

    async def send(message):
        nonlocal response_status, response_headers, response_body
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = message["headers"]
        elif message["type"] == "http.response.body":
            response_body += message.get("body", b"")

    await transport.handle_post_message(scope, receive, send)

    header_dict = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in response_headers
    }
    return Response(
        content=response_body,
        status_code=response_status or 200,
        headers=header_dict,
    )


# Create Starlette application
# SSE transport will send endpoint as: mount_path + transport_endpoint
# With Mount at /mcp and SseServerTransport("/messages"), endpoint becomes
# /mcp/messages
starlette_app = Starlette(
    routes=[
        Route("/mcp/messages", messages_endpoint, methods=["POST"]),
        Route("/mcp/messages/", messages_endpoint, methods=["POST"]),
        Mount("/mcp", app=sse_endpoint_asgi),
        Mount("/mcp/", app=sse_endpoint_asgi),
        Route("/health", health_check, methods=["GET"]),
        Route("/", root_endpoint, methods=["GET", "POST"]),
    ]
)
starlette_app.state.shutting_down = False

# Add CORS middleware - ChatGPT needs this to connect
starlette_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add startup logging to verify routes
@starlette_app.on_event("startup")
async def startup_event():
    starlette_app.state.shutting_down = False
    logger.info("Starlette app started - routes configured")
    logger.info(
        "Route order: /mcp/messages (messages), /mcp (SSE), /health, /"
    )
    logger.info(
        "Waiting for ChatGPT to POST to /mcp/messages after receiving "
        "endpoint event..."
    )


@starlette_app.on_event("shutdown")
async def shutdown_event():
    starlette_app.state.shutting_down = True
    logger.info("Shutdown signal received - cancelling SSE sessions")
    transport.cancel_all_sessions()


@starlette_app.exception_handler(404)
async def not_found_handler(request, exc):
    logger.warning(
        "404 Not Found - method=%s path=%s query=%s headers=%s",
        request.method,
        request.url.path,
        dict(request.query_params),
        dict(request.headers),
    )
    return Response("Not Found", status_code=404)


# Add middleware to log ALL requests for debugging
@starlette_app.middleware("http")
async def log_all_requests(request, call_next):
    """Log all incoming requests thoroughly for debugging"""
    start_time = time.time()

    # Log request details
    request_id = id(request)
    logger.info("=" * 80)
    logger.info(f"=== HTTP REQUEST #{request_id} ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"Path: {request.url.path}")
    logger.info(f"Full URL: {request.url}")
    logger.info(f"Query Params: {dict(request.query_params)}")
    logger.info(f"Headers: {dict(request.headers)}")
    client_info = (
        f"{request.client.host if request.client else 'unknown'}:"
        f"{request.client.port if request.client else 'unknown'}"
    )
    logger.info(f"Client: {client_info}")

    # Try to log request body (for POST/PUT/PATCH)
    body_logging_allowed = not request.url.path.startswith("/mcp")
    if request.method in ("POST", "PUT", "PATCH"):
        if body_logging_allowed:
            try:
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body.decode())
                        logger.info(
                            "Request Body (JSON):\n"
                            f"{json.dumps(body_json, indent=2, default=str)}"
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        body_str = body.decode('utf-8', errors='replace')
                        if len(body_str) > 1000:
                            logger.info(
                                "Request Body (text, truncated):\n"
                                f"{body_str[:1000]}... ({len(body_str)} chars)"
                            )
                        else:
                            logger.info(f"Request Body (text):\n{body_str}")
            except Exception as e:
                logger.warning(f"Could not read request body: {e}")
        else:
            logger.info(
                "Request body logging skipped to avoid draining MCP streams"
            )

    # Process request
    try:
        response = await call_next(request)
    except CancelledError:
        elapsed_time = time.time() - start_time
        logger.info(f"=== HTTP REQUEST #{request_id} CANCELLED ===")
        logger.info("Request cancelled during shutdown")
        logger.info(f"Elapsed Time: {elapsed_time:.4f}s")
        logger.info("=" * 80)
        return Response("Server shutting down", status_code=503)
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            f"=== HTTP REQUEST #{request_id} ERROR ===",
            exc_info=True
        )
        logger.error(f"Error: {type(e).__name__}: {str(e)}")
        logger.error(f"Elapsed Time: {elapsed_time:.4f}s")
        logger.error("=" * 80)
        raise
    else:
        elapsed_time = time.time() - start_time

        # Log response details
        logger.info(f"=== HTTP RESPONSE #{request_id} ===")
        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"Response Headers: {dict(response.headers)}")
        logger.info(f"Elapsed Time: {elapsed_time:.4f}s")
        logger.info("=" * 80)

        return response


def main():
    """
    Main entry point for the MCP server
    """
    logger.info("Starting MCP server...")
    logger.info(f"Server will listen on {HOST}:{PORT}")
    logger.info("Using SSE (Server-Sent Events) transport for HTTP access")
    logger.info(f"✓ MCP server will be available at http://{HOST}:{PORT}")
    logger.info(f"✓ SSE endpoint: http://{HOST}:{PORT}/mcp")
    logger.info(f"✓ Health check: http://{HOST}:{PORT}/health")
    logger.info("Press Ctrl-C to shutdown gracefully")

    try:
        # Run the server with uvicorn
        # uvicorn handles SIGINT/SIGTERM gracefully by default
        uvicorn.run(
            starlette_app,
            host=HOST,
            port=PORT,
            log_config=None,  # Use our own logging
        )
    except KeyboardInterrupt:
        # uvicorn raises KeyboardInterrupt on SIGINT
        # Log and let it propagate for clean shutdown
        logger.info("Shutdown signal received - shutting down gracefully...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
    finally:
        logger.info("MCP server stopped")
        # Ensure log handlers are flushed
        for handler in logging.root.handlers[:]:
            handler.flush()
            handler.close()
            logging.root.removeHandler(handler)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Clean exit on Ctrl-C
        print("\nShutdown complete.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Ensure all logs are flushed
        logging.shutdown()
