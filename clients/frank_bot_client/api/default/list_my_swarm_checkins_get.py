from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.swarm_my_checkins_response import SwarmMyCheckinsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    max_results: int | Unset = UNSET,
    stale_minutes: int | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["max_results"] = max_results

    params["stale_minutes"] = stale_minutes

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/actions/swarm/self",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SwarmMyCheckinsResponse | None:
    if response.status_code == 200:
        response_200 = SwarmMyCheckinsResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | SwarmMyCheckinsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    max_results: int | Unset = UNSET,
    stale_minutes: int | Unset = UNSET,
) -> Response[ErrorResponse | SwarmMyCheckinsResponse]:
    """List recent Swarm check-ins for your account via query parameters.

    Args:
        max_results (int | Unset):
        stale_minutes (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SwarmMyCheckinsResponse]
    """

    kwargs = _get_kwargs(
        max_results=max_results,
        stale_minutes=stale_minutes,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    max_results: int | Unset = UNSET,
    stale_minutes: int | Unset = UNSET,
) -> ErrorResponse | SwarmMyCheckinsResponse | None:
    """List recent Swarm check-ins for your account via query parameters.

    Args:
        max_results (int | Unset):
        stale_minutes (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SwarmMyCheckinsResponse
    """

    return sync_detailed(
        client=client,
        max_results=max_results,
        stale_minutes=stale_minutes,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    max_results: int | Unset = UNSET,
    stale_minutes: int | Unset = UNSET,
) -> Response[ErrorResponse | SwarmMyCheckinsResponse]:
    """List recent Swarm check-ins for your account via query parameters.

    Args:
        max_results (int | Unset):
        stale_minutes (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SwarmMyCheckinsResponse]
    """

    kwargs = _get_kwargs(
        max_results=max_results,
        stale_minutes=stale_minutes,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    max_results: int | Unset = UNSET,
    stale_minutes: int | Unset = UNSET,
) -> ErrorResponse | SwarmMyCheckinsResponse | None:
    """List recent Swarm check-ins for your account via query parameters.

    Args:
        max_results (int | Unset):
        stale_minutes (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SwarmMyCheckinsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            max_results=max_results,
            stale_minutes=stale_minutes,
        )
    ).parsed
