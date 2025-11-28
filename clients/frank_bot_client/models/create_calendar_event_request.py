from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CreateCalendarEventRequest")


@_attrs_define
class CreateCalendarEventRequest:
    """
    Attributes:
        summary (str):
        start (str): Start time in ISO8601 format.
        end (str): End time in ISO8601 format.
        attendees (list[str] | Unset): Email addresses for attendees.
        description (str | Unset):
        time_zone (str | Unset): IANA timezone for the event block.
        calendar_id (str | Unset):
        calendar_name (str | Unset):
    """

    summary: str
    start: str
    end: str
    attendees: list[str] | Unset = UNSET
    description: str | Unset = UNSET
    time_zone: str | Unset = UNSET
    calendar_id: str | Unset = UNSET
    calendar_name: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary

        start = self.start

        end = self.end

        attendees: list[str] | Unset = UNSET
        if not isinstance(self.attendees, Unset):
            attendees = self.attendees

        description = self.description

        time_zone = self.time_zone

        calendar_id = self.calendar_id

        calendar_name = self.calendar_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "summary": summary,
                "start": start,
                "end": end,
            }
        )
        if attendees is not UNSET:
            field_dict["attendees"] = attendees
        if description is not UNSET:
            field_dict["description"] = description
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
        summary = d.pop("summary")

        start = d.pop("start")

        end = d.pop("end")

        attendees = cast(list[str], d.pop("attendees", UNSET))

        description = d.pop("description", UNSET)

        time_zone = d.pop("time_zone", UNSET)

        calendar_id = d.pop("calendar_id", UNSET)

        calendar_name = d.pop("calendar_name", UNSET)

        create_calendar_event_request = cls(
            summary=summary,
            start=start,
            end=end,
            attendees=attendees,
            description=description,
            time_zone=time_zone,
            calendar_id=calendar_id,
            calendar_name=calendar_name,
        )

        create_calendar_event_request.additional_properties = d
        return create_calendar_event_request

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
