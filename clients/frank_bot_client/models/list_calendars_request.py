from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ListCalendarsRequest")


@_attrs_define
class ListCalendarsRequest:
    """
    Attributes:
        include_access_role (bool | Unset): Include Google accessRole information when true.
        primary_only (bool | Unset): Restrict to the primary calendar when true.
    """

    include_access_role: bool | Unset = UNSET
    primary_only: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        include_access_role = self.include_access_role

        primary_only = self.primary_only

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if include_access_role is not UNSET:
            field_dict["include_access_role"] = include_access_role
        if primary_only is not UNSET:
            field_dict["primary_only"] = primary_only

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        include_access_role = d.pop("include_access_role", UNSET)

        primary_only = d.pop("primary_only", UNSET)

        list_calendars_request = cls(
            include_access_role=include_access_role,
            primary_only=primary_only,
        )

        list_calendars_request.additional_properties = d
        return list_calendars_request

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
