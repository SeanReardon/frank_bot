from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.list_calendars_response import ListCalendarsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    include_access_role: bool | Unset = UNSET,
    primary_only: bool | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["include_access_role"] = include_access_role

    params["primary_only"] = primary_only

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/actions/calendar/calendars",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | ListCalendarsResponse | None:
    if response.status_code == 200:
        response_200 = ListCalendarsResponse.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | ListCalendarsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    include_access_role: bool | Unset = UNSET,
    primary_only: bool | Unset = UNSET,
) -> Response[ErrorResponse | ListCalendarsResponse]:
    """List calendars available to the authenticated user.

    Args:
        include_access_role (bool | Unset):
        primary_only (bool | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListCalendarsResponse]
    """

    kwargs = _get_kwargs(
        include_access_role=include_access_role,
        primary_only=primary_only,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    include_access_role: bool | Unset = UNSET,
    primary_only: bool | Unset = UNSET,
) -> ErrorResponse | ListCalendarsResponse | None:
    """List calendars available to the authenticated user.

    Args:
        include_access_role (bool | Unset):
        primary_only (bool | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListCalendarsResponse
    """

    return sync_detailed(
        client=client,
        include_access_role=include_access_role,
        primary_only=primary_only,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    include_access_role: bool | Unset = UNSET,
    primary_only: bool | Unset = UNSET,
) -> Response[ErrorResponse | ListCalendarsResponse]:
    """List calendars available to the authenticated user.

    Args:
        include_access_role (bool | Unset):
        primary_only (bool | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListCalendarsResponse]
    """

    kwargs = _get_kwargs(
        include_access_role=include_access_role,
        primary_only=primary_only,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    include_access_role: bool | Unset = UNSET,
    primary_only: bool | Unset = UNSET,
) -> ErrorResponse | ListCalendarsResponse | None:
    """List calendars available to the authenticated user.

    Args:
        include_access_role (bool | Unset):
        primary_only (bool | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListCalendarsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            include_access_role=include_access_role,
            primary_only=primary_only,
        )
    ).parsed
