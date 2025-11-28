from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="ContactResult")


@_attrs_define
class ContactResult:
    """
    Attributes:
        resource_name (str | Unset):
        display_name (str | Unset):
        emails (list[str] | Unset):
        phones (list[str] | Unset):
    """

    resource_name: str | Unset = UNSET
    display_name: str | Unset = UNSET
    emails: list[str] | Unset = UNSET
    phones: list[str] | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        resource_name = self.resource_name

        display_name = self.display_name

        emails: list[str] | Unset = UNSET
        if not isinstance(self.emails, Unset):
            emails = self.emails

        phones: list[str] | Unset = UNSET
        if not isinstance(self.phones, Unset):
            phones = self.phones

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if resource_name is not UNSET:
            field_dict["resource_name"] = resource_name
        if display_name is not UNSET:
            field_dict["display_name"] = display_name
        if emails is not UNSET:
            field_dict["emails"] = emails
        if phones is not UNSET:
            field_dict["phones"] = phones

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        resource_name = d.pop("resource_name", UNSET)

        display_name = d.pop("display_name", UNSET)

        emails = cast(list[str], d.pop("emails", UNSET))

        phones = cast(list[str], d.pop("phones", UNSET))

        contact_result = cls(
            resource_name=resource_name,
            display_name=display_name,
            emails=emails,
            phones=phones,
        )

        return contact_result
