from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.list_calendar_events_response import ListCalendarEventsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    day: str | Unset = UNSET,
    time_min: str | Unset = UNSET,
    time_max: str | Unset = UNSET,
    max_results: int | Unset = UNSET,
    time_zone: str | Unset = UNSET,
    calendar_id: str | Unset = UNSET,
    calendar_name: str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["day"] = day

    params["time_min"] = time_min

    params["time_max"] = time_max

    params["max_results"] = max_results

    params["time_zone"] = time_zone

    params["calendar_id"] = calendar_id

    params["calendar_name"] = calendar_name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/actions/calendar/events",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | ListCalendarEventsResponse | None:
    if response.status_code == 200:
        response_200 = ListCalendarEventsResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | ListCalendarEventsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    day: str | Unset = UNSET,
    time_min: str | Unset = UNSET,
    time_max: str | Unset = UNSET,
    max_results: int | Unset = UNSET,
    time_zone: str | Unset = UNSET,
    calendar_id: str | Unset = UNSET,
    calendar_name: str | Unset = UNSET,
) -> Response[ErrorResponse | ListCalendarEventsResponse]:
    """List calendar events via query parameters.

    Args:
        day (str | Unset):
        time_min (str | Unset):
        time_max (str | Unset):
        max_results (int | Unset):
        time_zone (str | Unset):
        calendar_id (str | Unset):
        calendar_name (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListCalendarEventsResponse]
    """

    kwargs = _get_kwargs(
        day=day,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        time_zone=time_zone,
        calendar_id=calendar_id,
        calendar_name=calendar_name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    day: str | Unset = UNSET,
    time_min: str | Unset = UNSET,
    time_max: str | Unset = UNSET,
    max_results: int | Unset = UNSET,
    time_zone: str | Unset = UNSET,
    calendar_id: str | Unset = UNSET,
    calendar_name: str | Unset = UNSET,
) -> ErrorResponse | ListCalendarEventsResponse | None:
    """List calendar events via query parameters.

    Args:
        day (str | Unset):
        time_min (str | Unset):
        time_max (str | Unset):
        max_results (int | Unset):
        time_zone (str | Unset):
        calendar_id (str | Unset):
        calendar_name (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListCalendarEventsResponse
    """

    return sync_detailed(
        client=client,
        day=day,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        time_zone=time_zone,
        calendar_id=calendar_id,
        calendar_name=calendar_name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    day: str | Unset = UNSET,
    time_min: str | Unset = UNSET,
    time_max: str | Unset = UNSET,
    max_results: int | Unset = UNSET,
    time_zone: str | Unset = UNSET,
    calendar_id: str | Unset = UNSET,
    calendar_name: str | Unset = UNSET,
) -> Response[ErrorResponse | ListCalendarEventsResponse]:
    """List calendar events via query parameters.

    Args:
        day (str | Unset):
        time_min (str | Unset):
        time_max (str | Unset):
        max_results (int | Unset):
        time_zone (str | Unset):
        calendar_id (str | Unset):
        calendar_name (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListCalendarEventsResponse]
    """

    kwargs = _get_kwargs(
        day=day,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        time_zone=time_zone,
        calendar_id=calendar_id,
        calendar_name=calendar_name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    day: str | Unset = UNSET,
    time_min: str | Unset = UNSET,
    time_max: str | Unset = UNSET,
    max_results: int | Unset = UNSET,
    time_zone: str | Unset = UNSET,
    calendar_id: str | Unset = UNSET,
    calendar_name: str | Unset = UNSET,
) -> ErrorResponse | ListCalendarEventsResponse | None:
    """List calendar events via query parameters.

    Args:
        day (str | Unset):
        time_min (str | Unset):
        time_max (str | Unset):
        max_results (int | Unset):
        time_zone (str | Unset):
        calendar_id (str | Unset):
        calendar_name (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListCalendarEventsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            day=day,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            time_zone=time_zone,
            calendar_id=calendar_id,
            calendar_name=calendar_name,
        )
    ).parsed
