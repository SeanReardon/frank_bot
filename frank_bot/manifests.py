"""
Manifest builders for OpenAI Actions compatibility.
"""

from __future__ import annotations

from typing import Any

from frank_bot.config import Settings


def _remove_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def build_ai_plugin_manifest(settings: Settings) -> dict[str, Any]:
    """
    Build a ChatGPT plugin style manifest compatible with OpenAI Actions.
    """
    base_url = settings.public_base_url.rstrip("/")
    manifest = {
        "schema_version": "v1",
        "name_for_human": settings.actions_name_for_human,
        "name_for_model": settings.actions_name_for_model,
        "description_for_human": settings.actions_description_for_human,
        "description_for_model": settings.actions_description_for_model,
        "auth": {
            "type": "service_http",
            "authorization_type": "custom",
            "instructions": (
                "Include the X-API-Key header set to the ACTIONS_API_KEY value "
                "configured on the server. This key is never shared with end users."
            ),
        },
        "api": {
            "type": "openapi",
            "url": f"{base_url}/actions/openapi.json",
            "is_user_authenticated": False,
        },
        "logo_url": settings.actions_logo_url,
        "contact_email": settings.actions_contact_email,
        "legal_info_url": settings.actions_legal_url,
    }
    return _remove_none(manifest)


def build_actions_manifest(settings: Settings) -> dict[str, Any]:
    """
    Lightweight manifest for the /.well-known/actions.json endpoint.
    """
    base_url = settings.public_base_url.rstrip("/")
    manifest = {
        "schema_version": "1.0",
        "name_for_human": settings.actions_name_for_human,
        "name_for_model": settings.actions_name_for_model,
        "description_for_model": settings.actions_description_for_model,
        "server_url": base_url,
        "openapi_url": f"{base_url}/actions/openapi.json",
        "auth": {
            "type": "api_key",
            "header": "X-API-Key",
            "env": "ACTIONS_API_KEY",
        },
    }
    if not settings.actions_api_key:
        manifest["auth"]["note"] = (
            "Set ACTIONS_API_KEY to enforce authentication."
        )
    return manifest


__all__ = ["build_ai_plugin_manifest", "build_actions_manifest"]

