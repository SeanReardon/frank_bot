"""Unit tests for jorb_capabilities module."""

from services.jorb_capabilities import generate_capabilities_reference


class TestGenerateCapabilitiesReference:
    """Tests for capabilities reference generation."""

    def test_returns_markdown_string(self):
        """Function returns a valid markdown string."""
        ref = generate_capabilities_reference()

        assert isinstance(ref, str)
        assert len(ref) > 500

    def test_includes_all_namespaces(self):
        """Reference includes all current namespace names."""
        ref = generate_capabilities_reference()

        # All namespaces should be documented
        assert "frank.calendar" in ref
        assert "frank.contacts" in ref
        assert "frank.sms" in ref
        assert "frank.telegram" in ref
        assert "frank.telegram_bot" in ref
        assert "frank.swarm" in ref
        assert "frank.time" in ref
        assert "frank.ups" in ref
        assert "frank.diagnostics" in ref
        assert "frank.system" in ref
        assert "frank.jorbs" in ref
        assert "frank.claudia" in ref
        assert "frank.style" in ref
        assert "frank.android" in ref

    def test_includes_header(self):
        """Reference includes proper header."""
        ref = generate_capabilities_reference()

        assert "# Frank Bot Capabilities" in ref

    def test_includes_method_tables(self):
        """Each namespace has method tables."""
        ref = generate_capabilities_reference()

        # Check for markdown tables
        assert "| Method | Signature | Description |" in ref
        assert "|--------|-----------|-------------|" in ref

    def test_includes_calendar_methods(self):
        """Calendar namespace methods are documented."""
        ref = generate_capabilities_reference()

        # Check for calendar methods
        assert "`events`" in ref
        assert "`create`" in ref
        assert "`list`" in ref

    def test_includes_contacts_methods(self):
        """Contacts namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`search`" in ref

    def test_includes_sms_methods(self):
        """SMS namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`send`" in ref

    def test_includes_telegram_methods(self):
        """Telegram namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`send`" in ref
        assert "`messages`" in ref
        assert "`chats`" in ref

    def test_includes_swarm_methods(self):
        """Swarm namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`checkins`" in ref

    def test_includes_time_methods(self):
        """Time namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`now`" in ref

    def test_includes_ups_methods(self):
        """UPS namespace methods are documented."""
        ref = generate_capabilities_reference()

        assert "`status`" in ref

    def test_includes_usage_examples(self):
        """Each namespace has usage examples."""
        ref = generate_capabilities_reference()

        # Should have code blocks for examples
        assert "```python" in ref

        # Examples should reference frank object
        assert "frank.calendar" in ref
        assert "frank.contacts" in ref
        assert "frank.telegram" in ref
        assert "frank.swarm" in ref

    def test_includes_usage_guidelines(self):
        """Reference includes usage guidelines."""
        ref = generate_capabilities_reference()

        assert "## Usage Guidelines" in ref
        assert "All methods are synchronous" in ref
        assert "Return dicts" in ref

    def test_includes_return_format(self):
        """Reference includes return format documentation."""
        ref = generate_capabilities_reference()

        assert "## Return Format" in ref
        assert "message" in ref


class TestCapabilitiesContent:
    """Tests for specific content in capabilities reference."""

    def test_calendar_example_is_complete(self):
        """Calendar example shows practical usage."""
        ref = generate_capabilities_reference()

        # Example should show getting events
        assert 'frank.calendar.events(day=' in ref or 'frank.calendar.events(' in ref
        # Example should show creating events
        assert 'frank.calendar.create(' in ref

    def test_telegram_example_shows_send_and_receive(self):
        """Telegram example shows both send and receive."""
        ref = generate_capabilities_reference()

        assert 'frank.telegram.send(' in ref
        assert 'frank.telegram.messages(' in ref

    def test_swarm_example_shows_filters(self):
        """Swarm example shows filtering by companion and category."""
        ref = generate_capabilities_reference()

        assert 'with_companion=' in ref
        assert 'category=' in ref


class TestCapabilitiesMarkdownValid:
    """Tests that generated markdown is valid."""

    def test_headers_are_balanced(self):
        """Markdown headers are properly formatted."""
        ref = generate_capabilities_reference()

        # Should have H1, H2, H3 headers
        assert ref.startswith("# ")
        assert "## " in ref
        assert "### " in ref

    def test_code_blocks_are_closed(self):
        """All code blocks are properly closed."""
        ref = generate_capabilities_reference()

        open_count = ref.count("```python")
        close_count = ref.count("```\n") + (1 if ref.endswith("```") else 0)

        # Allow for more closes than opens (some sections may close non-python blocks)
        assert close_count >= open_count

    def test_tables_have_proper_structure(self):
        """Markdown tables have proper structure."""
        ref = generate_capabilities_reference()

        lines = ref.split("\n")
        in_table = False
        table_separator_found = False

        for line in lines:
            if line.startswith("| Method |"):
                in_table = True
                continue
            if in_table and line.startswith("|--------"):
                table_separator_found = True
                continue
            if in_table and not line.startswith("|"):
                in_table = False
                table_separator_found = False

        # At least one table separator should exist
        assert table_separator_found or "|--------|" in ref
