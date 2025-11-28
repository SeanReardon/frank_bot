from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="SwarmCheckinEntry")


@_attrs_define
class SwarmCheckinEntry:
    """
    Attributes:
        iso_time (datetime.datetime | Unset):
        minutes_since (int | Unset):
        venue_name (str | Unset):
        city (str | Unset):
        state (str | Unset):
        country (str | Unset):
        categories (list[str] | Unset):
        canonical_url (str | Unset):
        shout (str | Unset):
    """

    iso_time: datetime.datetime | Unset = UNSET
    minutes_since: int | Unset = UNSET
    venue_name: str | Unset = UNSET
    city: str | Unset = UNSET
    state: str | Unset = UNSET
    country: str | Unset = UNSET
    categories: list[str] | Unset = UNSET
    canonical_url: str | Unset = UNSET
    shout: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        iso_time: str | Unset = UNSET
        if not isinstance(self.iso_time, Unset):
            iso_time = self.iso_time.isoformat()

        minutes_since = self.minutes_since

        venue_name = self.venue_name

        city = self.city

        state = self.state

        country = self.country

        categories: list[str] | Unset = UNSET
        if not isinstance(self.categories, Unset):
            categories = self.categories

        canonical_url = self.canonical_url

        shout = self.shout

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if iso_time is not UNSET:
            field_dict["iso_time"] = iso_time
        if minutes_since is not UNSET:
            field_dict["minutes_since"] = minutes_since
        if venue_name is not UNSET:
            field_dict["venue_name"] = venue_name
        if city is not UNSET:
            field_dict["city"] = city
        if state is not UNSET:
            field_dict["state"] = state
        if country is not UNSET:
            field_dict["country"] = country
        if categories is not UNSET:
            field_dict["categories"] = categories
        if canonical_url is not UNSET:
            field_dict["canonical_url"] = canonical_url
        if shout is not UNSET:
            field_dict["shout"] = shout

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _iso_time = d.pop("iso_time", UNSET)
        iso_time: datetime.datetime | Unset
        if isinstance(_iso_time, Unset):
            iso_time = UNSET
        else:
            iso_time = isoparse(_iso_time)

        minutes_since = d.pop("minutes_since", UNSET)

        venue_name = d.pop("venue_name", UNSET)

        city = d.pop("city", UNSET)

        state = d.pop("state", UNSET)

        country = d.pop("country", UNSET)

        categories = cast(list[str], d.pop("categories", UNSET))

        canonical_url = d.pop("canonical_url", UNSET)

        shout = d.pop("shout", UNSET)

        swarm_checkin_entry = cls(
            iso_time=iso_time,
            minutes_since=minutes_since,
            venue_name=venue_name,
            city=city,
            state=state,
            country=country,
            categories=categories,
            canonical_url=canonical_url,
            shout=shout,
        )

        swarm_checkin_entry.additional_properties = d
        return swarm_checkin_entry

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
