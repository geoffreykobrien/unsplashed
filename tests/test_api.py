"""Pure helpers in the API module."""

from custom_components.unsplashed.api import orientation_for, parse_photo, sized_url

from .conftest import make_photo


def test_orientation() -> None:
    assert orientation_for(1080, 1920) == "portrait"
    assert orientation_for(1920, 1080) == "landscape"
    assert orientation_for(1000, 1000) == "squarish"


def test_sized_url_keeps_ixid() -> None:
    url = sized_url("https://images.unsplash.com/photo-1?ixid=abc", 1080, 1920)
    assert url.startswith("https://images.unsplash.com/photo-1?ixid=abc&")
    assert "w=1080" in url and "h=1920" in url and "fit=crop" in url


def test_parse_photo() -> None:
    photo = parse_photo(make_photo("xyz"), 1080, 1920)
    assert photo is not None
    assert photo.credit == "Photo by Jane Doe on Unsplash"
    assert photo.track_url.endswith("/photos/xyz/download?ixid=abc")
    assert parse_photo({"id": "no-urls"}, 1, 1) is None
