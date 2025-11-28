from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="CurrentTimeResponse")


@_attrs_define
class CurrentTimeResponse:
    """
    Attributes:
        message (str):
        iso_time (datetime.datetime): Current time in ISO 8601 format.
        timezone (str): IANA timezone identifier.
        offset_minutes (int): UTC offset in minutes.
    """

    message: str
    iso_time: datetime.datetime
    timezone: str
    offset_minutes: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        iso_time = self.iso_time.isoformat()

        timezone = self.timezone

        offset_minutes = self.offset_minutes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "iso_time": iso_time,
                "timezone": timezone,
                "offset_minutes": offset_minutes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        iso_time = isoparse(d.pop("iso_time"))

        timezone = d.pop("timezone")

        offset_minutes = d.pop("offset_minutes")

        current_time_response = cls(
            message=message,
            iso_time=iso_time,
            timezone=timezone,
            offset_minutes=offset_minutes,
        )

        current_time_response.additional_properties = d
        return current_time_response

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
