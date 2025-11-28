from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListCalendarEventsRequest")


@_attrs_define
class ListCalendarEventsRequest:
    """
    Attributes:
        day (str | Unset): ISO date (YYYY-MM-DD). When provided all events for that day are returned.
        time_min (str | Unset): Lower bound (inclusive) in RFC3339/ISO8601 format.
        time_max (str | Unset): Upper bound (exclusive) in RFC3339/ISO8601 format.
        max_results (int | Unset): Maximum events to return (1-50).
        time_zone (str | Unset): IANA timezone name to use for day ranges.
        calendar_id (str | Unset): Specific calendar ID to query.
        calendar_name (str | Unset): Display name used to resolve a calendar.
    """

    day: str | Unset = UNSET
    time_min: str | Unset = UNSET
    time_max: str | Unset = UNSET
    max_results: int | Unset = UNSET
    time_zone: str | Unset = UNSET
    calendar_id: str | Unset = UNSET
    calendar_name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        day = self.day

        time_min = self.time_min

        time_max = self.time_max

        max_results = self.max_results

        time_zone = self.time_zone

        calendar_id = self.calendar_id

        calendar_name = self.calendar_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if day is not UNSET:
            field_dict["day"] = day
        if time_min is not UNSET:
            field_dict["time_min"] = time_min
        if time_max is not UNSET:
            field_dict["time_max"] = time_max
        if max_results is not UNSET:
            field_dict["max_results"] = max_results
        if time_zone is not UNSET:
            field_dict["time_zone"] = time_zone
        if calendar_id is not UNSET:
            field_dict["calendar_id"] = calendar_id
        if calendar_name is not UNSET:
            field_dict["calendar_name"] = calendar_name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        day = d.pop("day", UNSET)

        time_min = d.pop("time_min", UNSET)

        time_max = d.pop("time_max", UNSET)

        max_results = d.pop("max_results", UNSET)

        time_zone = d.pop("time_zone", UNSET)

        calendar_id = d.pop("calendar_id", UNSET)

        calendar_name = d.pop("calendar_name", UNSET)

        list_calendar_events_request = cls(
            day=day,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            time_zone=time_zone,
            calendar_id=calendar_id,
            calendar_name=calendar_name,
        )

        list_calendar_events_request.additional_properties = d
        return list_calendar_events_request

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
