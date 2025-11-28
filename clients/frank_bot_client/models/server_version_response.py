from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="ServerVersionResponse")


@_attrs_define
class ServerVersionResponse:
    """
    Attributes:
        message (str):
        startup_iso_time (datetime.datetime): Timestamp when the container process started.
        uptime_seconds (int): Uptime calculated at the time of the request.
    """

    message: str
    startup_iso_time: datetime.datetime
    uptime_seconds: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        startup_iso_time = self.startup_iso_time.isoformat()

        uptime_seconds = self.uptime_seconds

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "startup_iso_time": startup_iso_time,
                "uptime_seconds": uptime_seconds,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        startup_iso_time = isoparse(d.pop("startup_iso_time"))

        uptime_seconds = d.pop("uptime_seconds")

        server_version_response = cls(
            message=message,
            startup_iso_time=startup_iso_time,
            uptime_seconds=uptime_seconds,
        )

        server_version_response.additional_properties = d
        return server_version_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
