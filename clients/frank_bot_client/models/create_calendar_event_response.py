from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.calendar_descriptor import CalendarDescriptor
    from ..models.calendar_event import CalendarEvent


T = TypeVar("T", bound="CreateCalendarEventResponse")


@_attrs_define
class CreateCalendarEventResponse:
    """
    Attributes:
        message (str):
        calendar (CalendarDescriptor):
        event (CalendarEvent): Subset of Google Calendar event resource.
    """

    message: str
    calendar: CalendarDescriptor
    event: CalendarEvent
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        calendar = self.calendar.to_dict()

        event = self.event.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "calendar": calendar,
                "event": event,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.calendar_descriptor import CalendarDescriptor
        from ..models.calendar_event import CalendarEvent

        d = dict(src_dict)
        message = d.pop("message")

        calendar = CalendarDescriptor.from_dict(d.pop("calendar"))

        event = CalendarEvent.from_dict(d.pop("event"))

        create_calendar_event_response = cls(
            message=message,
            calendar=calendar,
            event=event,
        )

        create_calendar_event_response.additional_properties = d
        return create_calendar_event_response

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
