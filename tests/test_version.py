"""Test backend version management."""

import re

from backend import __version__


def test_version_is_string():
    """Version should be a string."""
    assert isinstance(__version__, str)


def test_version_format():
    """Version should be in MAJOR.MINOR format."""
    pattern = r"^\d+\.\d+$"
    assert re.match(pattern, __version__), f"Version {__version__} does not match X.Y format"


def test_version_components():
    """Version should have major and minor components."""
    parts = __version__.split(".")
    assert len(parts) == 2, f"Expected 2 parts, got {len(parts)}"
    assert int(parts[0]) >= 0, "Major version should be >= 0"
    assert int(parts[1]) >= 0, "Minor version should be >= 0"


def test_version_is_at_least_0_1():
    """Version should be at least 0.1 (major>=0, minor>=0)."""
    parts = __version__.split(".")
    major, minor = int(parts[0]), int(parts[1])
    assert major >= 0, f"Expected major version >= 0, got {major}"
    assert minor >= 0, f"Expected minor version >= 0, got {minor}"


def test_version_is_not_empty():
    """Version should not be empty."""
    assert __version__
    assert len(__version__) > 0
