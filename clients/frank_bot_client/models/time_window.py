from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TimeWindow")


@_attrs_define
class TimeWindow:
    """
    Attributes:
        time_min (str | Unset):
        time_max (str | Unset):
        time_zone (str | Unset):
    """

    time_min: str | Unset = UNSET
    time_max: str | Unset = UNSET
    time_zone: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        time_min = self.time_min

        time_max = self.time_max

        time_zone = self.time_zone

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if time_min is not UNSET:
            field_dict["time_min"] = time_min
        if time_max is not UNSET:
            field_dict["time_max"] = time_max
        if time_zone is not UNSET:
            field_dict["time_zone"] = time_zone

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        time_min = d.pop("time_min", UNSET)

        time_max = d.pop("time_max", UNSET)

        time_zone = d.pop("time_zone", UNSET)

        time_window = cls(
            time_min=time_min,
            time_max=time_max,
            time_zone=time_zone,
        )

        time_window.additional_properties = d
        return time_window

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
