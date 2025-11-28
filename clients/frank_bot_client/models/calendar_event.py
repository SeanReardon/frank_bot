from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.calendar_event_attendees_item import CalendarEventAttendeesItem
    from ..models.calendar_event_end import CalendarEventEnd
    from ..models.calendar_event_start import CalendarEventStart


T = TypeVar("T", bound="CalendarEvent")


@_attrs_define
class CalendarEvent:
    """Subset of Google Calendar event resource.

    Attributes:
        id (str | Unset): Unique event identifier.
        summary (str | Unset): Event title.
        description (str | Unset): Optional event description/body.
        location (str | Unset): Event location if provided.
        html_link (str | Unset): Google Calendar web URL for the event.
        start (CalendarEventStart | Unset): Google Calendar start object.
        end (CalendarEventEnd | Unset): Google Calendar end object.
        attendees (list[CalendarEventAttendeesItem] | Unset): List of attendee objects when present.
    """

    id: str | Unset = UNSET
    summary: str | Unset = UNSET
    description: str | Unset = UNSET
    location: str | Unset = UNSET
    html_link: str | Unset = UNSET
    start: CalendarEventStart | Unset = UNSET
    end: CalendarEventEnd | Unset = UNSET
    attendees: list[CalendarEventAttendeesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        summary = self.summary

        description = self.description

        location = self.location

        html_link = self.html_link

        start: dict[str, Any] | Unset = UNSET
        if not isinstance(self.start, Unset):
            start = self.start.to_dict()

        end: dict[str, Any] | Unset = UNSET
        if not isinstance(self.end, Unset):
            end = self.end.to_dict()

        attendees: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.attendees, Unset):
            attendees = []
            for attendees_item_data in self.attendees:
                attendees_item = attendees_item_data.to_dict()
                attendees.append(attendees_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if summary is not UNSET:
            field_dict["summary"] = summary
        if description is not UNSET:
            field_dict["description"] = description
        if location is not UNSET:
            field_dict["location"] = location
        if html_link is not UNSET:
            field_dict["htmlLink"] = html_link
        if start is not UNSET:
            field_dict["start"] = start
        if end is not UNSET:
            field_dict["end"] = end
        if attendees is not UNSET:
            field_dict["attendees"] = attendees

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.calendar_event_attendees_item import CalendarEventAttendeesItem
        from ..models.calendar_event_end import CalendarEventEnd
        from ..models.calendar_event_start import CalendarEventStart

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        summary = d.pop("summary", UNSET)

        description = d.pop("description", UNSET)

        location = d.pop("location", UNSET)

        html_link = d.pop("htmlLink", UNSET)

        _start = d.pop("start", UNSET)
        start: CalendarEventStart | Unset
        if isinstance(_start, Unset):
            start = UNSET
        else:
            start = CalendarEventStart.from_dict(_start)

        _end = d.pop("end", UNSET)
        end: CalendarEventEnd | Unset
        if isinstance(_end, Unset):
            end = UNSET
        else:
            end = CalendarEventEnd.from_dict(_end)

        _attendees = d.pop("attendees", UNSET)
        attendees: list[CalendarEventAttendeesItem] | Unset = UNSET
        if _attendees is not UNSET:
            attendees = []
            for attendees_item_data in _attendees:
                attendees_item = CalendarEventAttendeesItem.from_dict(attendees_item_data)

                attendees.append(attendees_item)

        calendar_event = cls(
            id=id,
            summary=summary,
            description=description,
            location=location,
            html_link=html_link,
            start=start,
            end=end,
            attendees=attendees,
        )

        calendar_event.additional_properties = d
        return calendar_event

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
