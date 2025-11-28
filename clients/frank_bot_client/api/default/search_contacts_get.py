from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.search_contacts_response import SearchContactsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    query: str,
    max_results: int | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["query"] = query

    params["max_results"] = max_results

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/actions/contacts/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SearchContactsResponse | None:
    if response.status_code == 200:
        response_200 = SearchContactsResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | SearchContactsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    query: str,
    max_results: int | Unset = UNSET,
) -> Response[ErrorResponse | SearchContactsResponse]:
    """Search Google Contacts via query parameters.

    Args:
        query (str):
        max_results (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SearchContactsResponse]
    """

    kwargs = _get_kwargs(
        query=query,
        max_results=max_results,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    query: str,
    max_results: int | Unset = UNSET,
) -> ErrorResponse | SearchContactsResponse | None:
    """Search Google Contacts via query parameters.

    Args:
        query (str):
        max_results (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SearchContactsResponse
    """

    return sync_detailed(
        client=client,
        query=query,
        max_results=max_results,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    query: str,
    max_results: int | Unset = UNSET,
) -> Response[ErrorResponse | SearchContactsResponse]:
    """Search Google Contacts via query parameters.

    Args:
        query (str):
        max_results (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SearchContactsResponse]
    """

    kwargs = _get_kwargs(
        query=query,
        max_results=max_results,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    query: str,
    max_results: int | Unset = UNSET,
) -> ErrorResponse | SearchContactsResponse | None:
    """Search Google Contacts via query parameters.

    Args:
        query (str):
        max_results (int | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SearchContactsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            query=query,
            max_results=max_results,
        )
    ).parsed
