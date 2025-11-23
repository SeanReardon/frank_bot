"""
Patch of the MCP SSE transport that emits the session query parameter in
camelCase so it matches ChatGPT's connector expectations while still
accepting both camelCase and snake_case on the POST endpoint.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import anyio
from anyio.streams.memory import (
    MemoryObjectReceiveStream,
    MemoryObjectSendStream,
)
from pydantic import ValidationError
from sse_starlette import EventSourceResponse
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

import mcp.types as types
from mcp.server.sse import SseServerTransport as BaseSseServerTransport
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.message import ServerMessageMetadata, SessionMessage

logger = logging.getLogger(__name__)


class CamelCaseSseServerTransport(BaseSseServerTransport):
    def __init__(
        self,
        endpoint: str,
        security_settings: TransportSecuritySettings | None = None,
    ) -> None:
        super().__init__(endpoint, security_settings=security_settings)
        self._session_scopes: dict[UUID, anyio.CancelScope] = {}

    """
    Starlette-friendly SSE transport that mirrors the upstream transport but
    sends session identifiers using `sessionId` to align with the OpenAI Apps
    connector. The POST endpoint still accepts both `sessionId` and
    `session_id` so existing tooling continues to function.
    """

    @asynccontextmanager
    async def connect_sse(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ):
        if scope["type"] != "http":
            logger.error("connect_sse received non-HTTP request")
            raise ValueError("connect_sse can only handle HTTP requests")

        request = Request(scope, receive)
        error_response = await self._security.validate_request(
            request,
            is_post=False,
        )
        if error_response:
            await error_response(scope, receive, send)
            raise ValueError("Request validation failed")

        initial_payload = await request.body()
        initial_session_message: SessionMessage | Exception | None = None
        if initial_payload:
            try:
                parsed = types.JSONRPCMessage.model_validate_json(
                    initial_payload
                )
                metadata = ServerMessageMetadata(request_context=request)
                initial_session_message = SessionMessage(parsed, metadata)
                logger.debug(
                    "Captured initial JSON-RPC message on SSE request: %s",
                    parsed,
                )
            except ValidationError as err:
                logger.warning(
                    "Failed to parse initial SSE body; forwarding error. %s",
                    err,
                )
                initial_session_message = err

        read_stream_writer: MemoryObjectSendStream[
            SessionMessage | Exception
        ]
        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
        write_stream: MemoryObjectSendStream[SessionMessage]
        write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        (
            write_stream,
            write_stream_reader,
        ) = anyio.create_memory_object_stream(0)

        session_id = uuid4()
        self._read_stream_writers[session_id] = read_stream_writer
        logger.debug("Created new session with ID: %s", session_id)
        session_scope = anyio.CancelScope()
        self._session_scopes[session_id] = session_scope

        root_path = scope.get("root_path", "")
        full_message_path_for_client = root_path.rstrip("/") + self._endpoint

        # ChatGPT expects camelCase session identifiers.
        client_post_uri_data = (
            f"{quote(full_message_path_for_client)}?sessionId={session_id.hex}"
        )

        (
            sse_stream_writer,
            sse_stream_reader,
        ) = anyio.create_memory_object_stream[dict[str, Any]](0)

        async def sse_writer():
            logger.debug("Starting SSE writer")
            async with sse_stream_writer, write_stream_reader:
                await sse_stream_writer.send(
                    {"event": "endpoint", "data": client_post_uri_data}
                )
                logger.debug("Sent endpoint event: %s", client_post_uri_data)

                async for session_message in write_stream_reader:
                    logger.debug(
                        "Sending message via SSE: %s",
                        session_message,
                    )
                    await sse_stream_writer.send(
                        {
                            "event": "message",
                            "data": session_message.message.model_dump_json(
                                by_alias=True,
                                exclude_none=True,
                            ),
                        }
                    )

        if initial_session_message is not None:
            await read_stream_writer.send(initial_session_message)

        async with anyio.create_task_group() as tg:

            async def response_wrapper(
                scope: Scope,
                receive: Receive,
                send: Send,
            ):
                with session_scope:
                    await EventSourceResponse(
                        content=sse_stream_reader,
                        data_sender_callable=sse_writer,
                    )(scope, receive, send)
                await read_stream_writer.aclose()
                await write_stream_reader.aclose()
                logger.debug("Client session disconnected %s", session_id)

            logger.debug("Starting SSE response task")
            tg.start_soon(response_wrapper, scope, receive, send)

            logger.debug("Yielding read and write streams")
            yield (read_stream, write_stream)
        self._session_scopes.pop(session_id, None)

    async def handle_post_message(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        logger.debug("Handling POST message")
        request = Request(scope, receive)

        error_response = await self._security.validate_request(
            request,
            is_post=True,
        )
        if error_response:
            return await error_response(scope, receive, send)

        session_id_param = (
            request.query_params.get("sessionId")
            or request.query_params.get("session_id")
        )
        if session_id_param is None:
            logger.warning("Received request without sessionId")
            response = Response("sessionId is required", status_code=400)
            return await response(scope, receive, send)

        try:
            session_id = UUID(hex=session_id_param)
            logger.debug("Parsed session ID: %s", session_id)
        except ValueError:
            logger.warning("Received invalid session ID: %s", session_id_param)
            response = Response("Invalid session ID", status_code=400)
            return await response(scope, receive, send)

        writer = self._read_stream_writers.get(session_id)
        if not writer:
            logger.warning("Could not find session for ID: %s", session_id)
            response = Response("Could not find session", status_code=404)
            return await response(scope, receive, send)

        body = await request.body()
        logger.debug("Received JSON: %s", body)

        try:
            message = types.JSONRPCMessage.model_validate_json(body)
            logger.debug("Validated client message: %s", message)
        except ValidationError as err:
            logger.exception("Failed to parse message")
            response = Response("Could not parse message", status_code=400)
            await response(scope, receive, send)
            await writer.send(err)
            return

        metadata = ServerMessageMetadata(request_context=request)
        session_message = SessionMessage(message, metadata=metadata)
        logger.debug("Sending session message to writer: %s", session_message)
        response = Response("Accepted", status_code=202)
        await response(scope, receive, send)
        await writer.send(session_message)

    def cancel_all_sessions(self) -> None:
        """Cancel every active SSE session to unblock shutdown."""
        for scope in list(self._session_scopes.values()):
            scope.cancel()
