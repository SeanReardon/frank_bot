from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SwarmMyCheckinsRequest")


@_attrs_define
class SwarmMyCheckinsRequest:
    """
    Attributes:
        max_results (int | Unset): Number of check-ins to return (default 5, max 20).
        stale_minutes (int | Unset): Minutes before a check-in is considered stale (default 180).
    """

    max_results: int | Unset = UNSET
    stale_minutes: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        max_results = self.max_results

        stale_minutes = self.stale_minutes

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if max_results is not UNSET:
            field_dict["max_results"] = max_results
        if stale_minutes is not UNSET:
            field_dict["stale_minutes"] = stale_minutes

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        max_results = d.pop("max_results", UNSET)

        stale_minutes = d.pop("stale_minutes", UNSET)

        swarm_my_checkins_request = cls(
            max_results=max_results,
            stale_minutes=stale_minutes,
        )

        swarm_my_checkins_request.additional_properties = d
        return swarm_my_checkins_request

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
