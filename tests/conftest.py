"""Shared fixtures."""

from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load integrations from custom_components in every test."""
    yield


def make_photo(photo_id: str, name: str = "Jane Doe") -> dict:
    return {
        "id": photo_id,
        "description": f"Photo {photo_id}",
        "color": "#123456",
        "urls": {"raw": f"https://images.unsplash.com/photo-{photo_id}?ixid=abc"},
        "links": {
            "html": f"https://unsplash.com/photos/{photo_id}",
            "download_location": f"https://api.unsplash.com/photos/{photo_id}/download?ixid=abc",
        },
        "user": {"name": name, "links": {"html": "https://unsplash.com/@jane"}},
        "location": {"name": "Portland, Maine"},
    }
