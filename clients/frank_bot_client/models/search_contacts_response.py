from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.contact_result import ContactResult


T = TypeVar("T", bound="SearchContactsResponse")


@_attrs_define
class SearchContactsResponse:
    """
    Attributes:
        message (str):
        query (str):
        count (int):
        contacts (list[ContactResult]):
    """

    message: str
    query: str
    count: int
    contacts: list[ContactResult]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        query = self.query

        count = self.count

        contacts = []
        for contacts_item_data in self.contacts:
            contacts_item = contacts_item_data.to_dict()
            contacts.append(contacts_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
                "query": query,
                "count": count,
                "contacts": contacts,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.contact_result import ContactResult

        d = dict(src_dict)
        message = d.pop("message")

        query = d.pop("query")

        count = d.pop("count")

        contacts = []
        _contacts = d.pop("contacts")
        for contacts_item_data in _contacts:
            contacts_item = ContactResult.from_dict(contacts_item_data)

            contacts.append(contacts_item)

        search_contacts_response = cls(
            message=message,
            query=query,
            count=count,
            contacts=contacts,
        )

        search_contacts_response.additional_properties = d
        return search_contacts_response

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
