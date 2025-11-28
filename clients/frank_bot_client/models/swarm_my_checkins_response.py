from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.swarm_checkin_entry import SwarmCheckinEntry


T = TypeVar("T", bound="SwarmMyCheckinsResponse")


@_attrs_define
class SwarmMyCheckinsResponse:
    """
    Attributes:
        message (str):
        count (int):
        checkins (list[SwarmCheckinEntry]):
    """

    message: str
    count: int
    checkins: list[SwarmCheckinEntry]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        count = self.count

        checkins = []
        for checkins_item_data in self.checkins:
            checkins_item = checkins_item_data.to_dict()
            checkins.append(checkins_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "count": count,
                "checkins": checkins,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.swarm_checkin_entry import SwarmCheckinEntry

        d = dict(src_dict)
        message = d.pop("message")

        count = d.pop("count")

        checkins = []
        _checkins = d.pop("checkins")
        for checkins_item_data in _checkins:
            checkins_item = SwarmCheckinEntry.from_dict(checkins_item_data)

            checkins.append(checkins_item)

        swarm_my_checkins_response = cls(
            message=message,
            count=count,
            checkins=checkins,
        )

        swarm_my_checkins_response.additional_properties = d
        return swarm_my_checkins_response

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
