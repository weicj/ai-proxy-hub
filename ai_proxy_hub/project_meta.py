from __future__ import annotations

from typing import Any, Dict

from .constants import (
    APP_AUTHOR,
    APP_LICENSE_NAME,
    APP_LICENSE_URL,
    APP_NAME,
    APP_RELEASES_URL,
    APP_REPOSITORY_URL,
    APP_SLUG,
    APP_SOURCE_HOST,
    APP_UPDATE_CHANNEL,
    APP_VERSION,
    CONFIG_VERSION,
)


def project_metadata_payload() -> Dict[str, Any]:
    repository_url = str(APP_REPOSITORY_URL or "").strip()
    releases_url = str(APP_RELEASES_URL or "").strip()
    source_configured = bool(repository_url)
    updates_url = releases_url or repository_url
    return {
        "name": APP_NAME,
        "slug": APP_SLUG,
        "version": APP_VERSION,
        "config_version": CONFIG_VERSION,
        "author": APP_AUTHOR,
        "license": {
            "name": APP_LICENSE_NAME,
            "url": APP_LICENSE_URL,
        },
        "source": {
            "host": APP_SOURCE_HOST,
            "url": repository_url,
            "configured": source_configured,
        },
        "updates": {
            "channel": APP_UPDATE_CHANNEL,
            "url": updates_url,
            "configured": bool(updates_url),
        },
    }


__all__ = ["project_metadata_payload"]
