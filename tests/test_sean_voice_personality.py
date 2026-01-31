"""
Unit tests for sean-voice personality.

Verifies the sean-voice personality file loads correctly and contains expected values.
"""

from __future__ import annotations

import pytest

from services.personality_loader import PersonalityLoader, get_personality_loader


class TestSeanVoicePersonality:
    """Tests for sean-voice personality loading."""

    @pytest.fixture
    def loader(self) -> PersonalityLoader:
        """Create a PersonalityLoader instance."""
        loader = PersonalityLoader()
        return loader

    def test_sean_voice_loads(self, loader: PersonalityLoader) -> None:
        """sean-voice personality loads successfully."""
        personality = loader.get("sean-voice")

        assert personality is not None
        assert personality.id == "sean-voice"
        assert personality.name == "Sean's Voice"

    def test_sean_voice_communication_style(self, loader: PersonalityLoader) -> None:
        """sean-voice has correct communication style traits."""
        personality = loader.get("sean-voice")

        assert personality is not None
        cs = personality.traits.communication_style
        assert cs.tone == "casual"
        assert cs.verbosity == "very_concise"
        assert cs.emoji_usage == "never"
        assert cs.formality < 0.5  # Informal

    def test_sean_voice_no_emojis(self, loader: PersonalityLoader) -> None:
        """sean-voice has emoji_usage set to never."""
        personality = loader.get("sean-voice")

        assert personality is not None
        assert personality.traits.communication_style.emoji_usage == "never"

    def test_sean_voice_guidelines_present(self, loader: PersonalityLoader) -> None:
        """sean-voice has guidelines for brevity and style."""
        personality = loader.get("sean-voice")

        assert personality is not None
        guidelines = personality.system_prompt_additions.guidelines
        assert len(guidelines) > 0

        # Check for key guidelines
        guidelines_text = " ".join(guidelines).lower()
        assert "emoji" in guidelines_text
        assert "markdown" in guidelines_text
        assert "short" in guidelines_text or "brief" in guidelines_text

    def test_sean_voice_examples_present(self, loader: PersonalityLoader) -> None:
        """sean-voice has example responses."""
        personality = loader.get("sean-voice")

        assert personality is not None
        examples = personality.system_prompt_additions.examples
        assert len(examples) > 0

        # Check examples show brief responses
        responses = [ex.get("response", "") for ex in examples]
        assert "Mk" in responses
        assert any("Yep" in r for r in responses)

    def test_sean_voice_temperature(self, loader: PersonalityLoader) -> None:
        """sean-voice has elevated temperature for natural variation."""
        personality = loader.get("sean-voice")

        assert personality is not None
        assert personality.model_preferences.temperature == 0.8

    def test_sean_voice_preamble_references_sean_md(
        self, loader: PersonalityLoader
    ) -> None:
        """sean-voice preamble references SEAN.md."""
        personality = loader.get("sean-voice")

        assert personality is not None
        preamble = personality.system_prompt_additions.preamble
        assert "SEAN.md" in preamble or "Sean" in preamble

    def test_sean_voice_format_for_prompt(self, loader: PersonalityLoader) -> None:
        """sean-voice formats correctly for prompts."""
        personality = loader.get("sean-voice")

        assert personality is not None
        prompt = personality.format_for_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "Sean's Voice" in prompt
        assert "casual" in prompt
        assert "very_concise" in prompt

    def test_sean_voice_in_global_loader(self) -> None:
        """sean-voice is available via global loader."""
        loader = get_personality_loader()
        loader.reload()  # Force reload to pick up any new files

        ids = loader.list_ids()
        assert "sean-voice" in ids
