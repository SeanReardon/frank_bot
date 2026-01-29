"""Unit tests for script storage and parsing utilities."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile

import pytest

from meta.scripts import (
    ScriptMetadata,
    ScriptParameter,
    parse_docstring,
    get_script_docstring,
    parse_script_filename,
    generate_script_filename,
    list_scripts,
    get_script,
    save_script,
    script_metadata_to_dict,
)


class TestParseDocstring:
    """Tests for docstring parsing."""

    def test_empty_docstring(self):
        """Empty or None docstring returns empty values."""
        result = parse_docstring(None)
        assert result["description"] == ""
        assert result["parameters"] == []
        assert result["example"] is None

        result = parse_docstring("")
        assert result["description"] == ""
        assert result["parameters"] == []
        assert result["example"] is None

    def test_simple_description(self):
        """Single paragraph description is extracted correctly."""
        docstring = "This is a simple description."
        result = parse_docstring(docstring)
        assert result["description"] == "This is a simple description."
        assert result["parameters"] == []
        assert result["example"] is None

    def test_multiline_description(self):
        """Multi-line description up to blank line."""
        docstring = """This is a multi-line
description that spans
multiple lines.

This is not part of description."""
        result = parse_docstring(docstring)
        assert (
            result["description"]
            == "This is a multi-line description that spans multiple lines."
        )

    def test_parameters_section(self):
        """Parameters section is parsed correctly."""
        docstring = """Script description.

Parameters:
    city (str): The city to search for hotels
    max_results (int): Maximum number of results to return
    include_reviews: Whether to include reviews
"""
        result = parse_docstring(docstring)
        assert result["description"] == "Script description."
        assert len(result["parameters"]) == 3

        params = result["parameters"]
        assert params[0].name == "city"
        assert params[0].type == "str"
        assert params[0].description == "The city to search for hotels"

        assert params[1].name == "max_results"
        assert params[1].type == "int"
        assert params[1].description == "Maximum number of results to return"

        assert params[2].name == "include_reviews"
        assert params[2].type is None
        assert params[2].description == "Whether to include reviews"

    def test_example_section(self):
        """Example section is extracted correctly."""
        docstring = """Script description.

Example:
    result = frank.swarm.checkins(category="hotel")
    for checkin in result["checkins"]:
        print(checkin["venue"]["name"])
"""
        result = parse_docstring(docstring)
        assert result["description"] == "Script description."
        assert result["example"] is not None
        assert 'frank.swarm.checkins(category="hotel")' in result["example"]

    def test_full_docstring(self):
        """Full docstring with all sections."""
        docstring = """Find hotels in a city using Swarm checkins.

This script searches through your Swarm history to find hotel
checkins in a specific city.

Parameters:
    city (str): The city to search for hotels
    year (int): Year to filter by

Example:
    hotels = main(frank, city="San Francisco", year=2024)

Returns:
    List of hotel checkins
"""
        result = parse_docstring(docstring)
        assert "Find hotels in a city" in result["description"]
        assert len(result["parameters"]) == 2
        assert result["example"] is not None
        assert "San Francisco" in result["example"]

    def test_args_section(self):
        """Args: section (alternative to Parameters:) is parsed."""
        docstring = """Script description.

Args:
    name (str): The name to search
"""
        result = parse_docstring(docstring)
        assert len(result["parameters"]) == 1
        assert result["parameters"][0].name == "name"


class TestGetScriptDocstring:
    """Tests for extracting module docstrings."""

    def test_extract_docstring(self):
        """Module docstring is extracted correctly."""
        code = '''"""
This is the script docstring.

Parameters:
    param1: A parameter
"""

def main(frank, param1):
    pass
'''
        docstring = get_script_docstring(code)
        assert docstring is not None
        assert "This is the script docstring" in docstring

    def test_no_docstring(self):
        """Returns None when no docstring present."""
        code = """
def main(frank):
    pass
"""
        assert get_script_docstring(code) is None

    def test_invalid_syntax(self):
        """Returns None for invalid Python syntax."""
        code = "def main( invalid syntax"
        assert get_script_docstring(code) is None


class TestParseScriptFilename:
    """Tests for parsing script filenames."""

    def test_valid_filename(self):
        """Valid filename is parsed correctly."""
        result = parse_script_filename("2024-01-15T10-30-00Z-my-script.py")
        assert result is not None
        timestamp, slug = result
        assert timestamp == "2024-01-15T10-30-00Z"
        assert slug == "my-script"

    def test_complex_slug(self):
        """Slug with multiple dashes is preserved."""
        result = parse_script_filename("2024-01-15T10-30-00Z-my-complex-script-name.py")
        assert result is not None
        _, slug = result
        assert slug == "my-complex-script-name"

    def test_invalid_extension(self):
        """Non-.py files return None."""
        assert parse_script_filename("2024-01-15T10-30-00Z-script.txt") is None

    def test_invalid_format(self):
        """Invalid formats return None."""
        assert parse_script_filename("my-script.py") is None
        assert parse_script_filename("2024-script.py") is None


class TestGenerateScriptFilename:
    """Tests for generating script filenames."""

    def test_with_timestamp(self):
        """Filename is generated with provided timestamp."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        filename = generate_script_filename("my-script", ts)
        assert filename == "2024-01-15T10-30-00Z-my-script.py"

    def test_without_timestamp(self):
        """Filename uses current time when no timestamp provided."""
        filename = generate_script_filename("test-script")
        assert filename.endswith("-test-script.py")
        # Should have timestamp prefix
        assert "T" in filename
        assert "Z" in filename


class TestScriptStorage:
    """Tests for script storage operations."""

    def test_save_and_get_script(self):
        """Script can be saved and retrieved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir)

            code = '''"""Test script."""

def main(frank):
    return {"status": "ok"}
'''
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            script_id = save_script("test-script", code, scripts_dir, ts)

            assert script_id == "2024-01-15T10-30-00Z-test-script"

            # Retrieve the script
            retrieved = get_script(script_id, scripts_dir)
            assert retrieved == code

    def test_get_nonexistent_script(self):
        """Getting nonexistent script returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_script("nonexistent-script", tmpdir)
            assert result is None

    def test_list_scripts_empty(self):
        """Empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts = list_scripts(tmpdir)
            assert scripts == []

    def test_list_scripts_nonexistent_dir(self):
        """Nonexistent directory returns empty list."""
        scripts = list_scripts("/nonexistent/path")
        assert scripts == []

    def test_list_scripts_with_metadata(self):
        """Scripts are listed with parsed metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir)

            code1 = '''"""
Find hotels in a city.

Parameters:
    city (str): The city name
"""

def main(frank, city):
    pass
'''
            code2 = '''"""Another script."""

def main(frank):
    pass
'''
            ts1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            ts2 = datetime(2024, 1, 16, 11, 0, 0, tzinfo=timezone.utc)

            save_script("find-hotels", code1, scripts_dir, ts1)
            save_script("other-script", code2, scripts_dir, ts2)

            scripts = list_scripts(scripts_dir)

            # Should be sorted by created_at descending
            assert len(scripts) == 2
            assert scripts[0].slug == "other-script"  # Newer
            assert scripts[1].slug == "find-hotels"  # Older

            # Check metadata for find-hotels
            hotels_script = scripts[1]
            assert "Find hotels" in hotels_script.description
            assert len(hotels_script.parameters) == 1
            assert hotels_script.parameters[0].name == "city"

    def test_list_scripts_ignores_invalid_filenames(self):
        """Files with invalid names are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir)

            # Create valid script
            ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            save_script("valid-script", '"""Valid."""', scripts_dir, ts)

            # Create invalid files
            (scripts_dir / "invalid.py").write_text("# no timestamp")
            (scripts_dir / "readme.txt").write_text("not a script")

            scripts = list_scripts(scripts_dir)
            assert len(scripts) == 1
            assert scripts[0].slug == "valid-script"


class TestScriptMetadataToDict:
    """Tests for converting metadata to dict."""

    def test_conversion(self):
        """ScriptMetadata converts to dict correctly."""
        metadata = ScriptMetadata(
            id="2024-01-15T10-30-00Z-test",
            slug="test",
            description="Test script",
            parameters=[
                ScriptParameter(name="city", type="str", description="City name"),
            ],
            example="print('hello')",
            created_at="2024-01-15T10:30:00Z",
        )

        result = script_metadata_to_dict(metadata)

        assert result["id"] == "2024-01-15T10-30-00Z-test"
        assert result["slug"] == "test"
        assert result["description"] == "Test script"
        assert len(result["parameters"]) == 1
        assert result["parameters"][0]["name"] == "city"
        assert result["parameters"][0]["type"] == "str"
        assert result["example"] == "print('hello')"
        assert result["created_at"] == "2024-01-15T10:30:00Z"

    def test_empty_parameters(self):
        """Metadata with no parameters converts correctly."""
        metadata = ScriptMetadata(
            id="test-id",
            slug="test",
            description="No params",
            parameters=[],
            example=None,
            created_at="2024-01-15T10:30:00Z",
        )

        result = script_metadata_to_dict(metadata)
        assert result["parameters"] == []
        assert result["example"] is None
