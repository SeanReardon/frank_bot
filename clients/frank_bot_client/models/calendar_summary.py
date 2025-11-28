from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CalendarSummary")


@_attrs_define
class CalendarSummary:
    """
    Attributes:
        id (str | Unset):
        summary (str | Unset):
        time_zone (str | Unset):
        primary (bool | Unset):
        access_role (str | Unset):
    """

    id: str | Unset = UNSET
    summary: str | Unset = UNSET
    time_zone: str | Unset = UNSET
    primary: bool | Unset = UNSET
    access_role: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        summary = self.summary

        time_zone = self.time_zone

        primary = self.primary

        access_role = self.access_role

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if summary is not UNSET:
            field_dict["summary"] = summary
        if time_zone is not UNSET:
            field_dict["timeZone"] = time_zone
        if primary is not UNSET:
            field_dict["primary"] = primary
        if access_role is not UNSET:
            field_dict["accessRole"] = access_role

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id", UNSET)

        summary = d.pop("summary", UNSET)

        time_zone = d.pop("timeZone", UNSET)

        primary = d.pop("primary", UNSET)

        access_role = d.pop("accessRole", UNSET)

        calendar_summary = cls(
            id=id,
            summary=summary,
            time_zone=time_zone,
            primary=primary,
            access_role=access_role,
        )

        calendar_summary.additional_properties = d
        return calendar_summary

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
