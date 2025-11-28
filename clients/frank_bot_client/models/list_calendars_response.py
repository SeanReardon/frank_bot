from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.calendar_summary import CalendarSummary


T = TypeVar("T", bound="ListCalendarsResponse")


@_attrs_define
class ListCalendarsResponse:
    """
    Attributes:
        message (str):
        count (int):
        calendars (list[CalendarSummary]):
    """

    message: str
    count: int
    calendars: list[CalendarSummary]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        count = self.count

        calendars = []
        for calendars_item_data in self.calendars:
            calendars_item = calendars_item_data.to_dict()
            calendars.append(calendars_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "count": count,
                "calendars": calendars,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.calendar_summary import CalendarSummary

        d = dict(src_dict)
        message = d.pop("message")

        count = d.pop("count")

        calendars = []
        _calendars = d.pop("calendars")
        for calendars_item_data in _calendars:
            calendars_item = CalendarSummary.from_dict(calendars_item_data)

            calendars.append(calendars_item)

        list_calendars_response = cls(
            message=message,
            count=count,
            calendars=calendars,
        )

        list_calendars_response.additional_properties = d
        return list_calendars_response

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
