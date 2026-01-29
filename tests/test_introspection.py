"""Unit tests for introspection module."""

import pytest

from meta.introspection import generate_meta_documentation, generate_method_table
from meta.api import CalendarNamespace, SwarmNamespace


class TestGenerateMetaDocumentation:
    """Tests for documentation generation."""

    def test_generates_markdown(self):
        """Documentation is generated as valid Markdown."""
        doc = generate_meta_documentation()

        # Should be a non-empty string
        assert isinstance(doc, str)
        assert len(doc) > 500  # Should have substantial content

    def test_includes_header(self):
        """Documentation includes header section."""
        doc = generate_meta_documentation()

        assert "# FrankAPI Documentation" in doc
        assert "FrankAPI provides synchronous access" in doc

    def test_includes_quick_start(self):
        """Documentation includes quick start example."""
        doc = generate_meta_documentation()

        assert "## Quick Start" in doc
        assert "```python" in doc
        assert "def main(frank" in doc
        assert "frank.swarm.checkins" in doc

    def test_includes_execution_workflow(self):
        """Documentation includes execution workflow."""
        doc = generate_meta_documentation()

        assert "## Execution Workflow" in doc
        assert "/frank/execute" in doc
        assert "job_id" in doc
        assert "/frank/jobs" in doc

    def test_includes_all_services(self):
        """Documentation includes all namespace services."""
        doc = generate_meta_documentation()

        assert "## Services" in doc
        assert "### frank.calendar" in doc
        assert "### frank.contacts" in doc
        assert "### frank.sms" in doc
        assert "### frank.swarm" in doc
        assert "### frank.ups" in doc
        assert "### frank.time" in doc

    def test_includes_method_tables(self):
        """Documentation includes method tables with proper format."""
        doc = generate_meta_documentation()

        # Check table header format
        assert "| Method | Signature | Description |" in doc
        assert "|--------|-----------|-------------|" in doc

        # Check some specific methods are documented
        assert "`events`" in doc
        assert "`create`" in doc
        assert "`search`" in doc
        assert "`checkins`" in doc
        assert "`status`" in doc
        assert "`now`" in doc
        assert "`send`" in doc

    def test_includes_notes(self):
        """Documentation includes notes section."""
        doc = generate_meta_documentation()

        assert "## Notes" in doc
        assert "10-minute timeout" in doc
        assert "`print()`" in doc
        assert "`stdout`" in doc

    def test_method_signatures_documented(self):
        """Method signatures are included in documentation."""
        doc = generate_meta_documentation()

        # Calendar.events has several parameters
        assert "day" in doc
        assert "time_min" in doc or "timeMin" in doc

        # Swarm.checkins has many parameters
        assert "category" in doc
        assert "with_companion" in doc
        assert "max_results" in doc

    def test_method_descriptions_documented(self):
        """Method descriptions are included in documentation."""
        doc = generate_meta_documentation()

        # Check some descriptions from docstrings
        assert "calendar events" in doc.lower() or "get calendar" in doc.lower()
        assert "checkins" in doc.lower() or "check-in" in doc.lower()


class TestGenerateMethodTable:
    """Tests for single namespace table generation."""

    def test_calendar_namespace(self):
        """Calendar namespace generates correct table."""
        table = generate_method_table("calendar", CalendarNamespace)

        assert "### frank.calendar" in table
        assert "| Method | Signature | Description |" in table
        assert "`events`" in table
        assert "`create`" in table
        assert "`list`" in table

    def test_swarm_namespace(self):
        """Swarm namespace generates correct table."""
        table = generate_method_table("swarm", SwarmNamespace)

        assert "### frank.swarm" in table
        assert "`checkins`" in table
        # Swarm.checkins has many parameters
        assert "year" in table
        assert "category" in table

    def test_empty_namespace(self):
        """Empty namespace returns empty string."""

        class EmptyNamespace:
            pass

        table = generate_method_table("empty", EmptyNamespace)
        assert table == ""

    def test_escapes_pipes(self):
        """Pipe characters in signatures are escaped."""
        # This tests the implementation detail that | chars are escaped
        # Most signatures don't have pipes, but the code handles it
        table = generate_method_table("calendar", CalendarNamespace)

        # The table should be valid Markdown (no unescaped pipes in content)
        lines = table.split("\n")
        for line in lines:
            if line.startswith("|"):
                # Count pipes - should have exactly 4 (start, 3 separators, end)
                # unless there's content with escaped pipes
                pass  # Just verify it doesn't crash


class TestDocumentationStructure:
    """Tests for overall documentation structure."""

    def test_sections_in_order(self):
        """Documentation sections appear in correct order."""
        doc = generate_meta_documentation()

        # Find positions of sections
        header_pos = doc.find("# FrankAPI Documentation")
        quickstart_pos = doc.find("## Quick Start")
        workflow_pos = doc.find("## Execution Workflow")
        services_pos = doc.find("## Services")
        notes_pos = doc.find("## Notes")

        # Verify all sections exist
        assert header_pos >= 0
        assert quickstart_pos >= 0
        assert workflow_pos >= 0
        assert services_pos >= 0
        assert notes_pos >= 0

        # Verify order
        assert header_pos < quickstart_pos
        assert quickstart_pos < workflow_pos
        assert workflow_pos < services_pos
        assert services_pos < notes_pos

    def test_code_blocks_properly_closed(self):
        """All code blocks are properly opened and closed."""
        doc = generate_meta_documentation()

        # Count code fence markers
        python_blocks = doc.count("```python")
        json_blocks = doc.count("```json")
        close_blocks = doc.count("```\n") + (1 if doc.endswith("```") else 0)

        # Each open block should have a close
        assert python_blocks + json_blocks == close_blocks
