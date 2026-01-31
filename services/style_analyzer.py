"""
Style analyzer for extracting Sean's voice patterns from message history.

This module analyzes Telegram message history to extract communication patterns,
producing a StyleAnalysisResult that can be used to generate SEAN.md documentation.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.telegram_client import TelegramMessage

logger = logging.getLogger(__name__)


@dataclass
class PatternExample:
    """A single example of a communication pattern."""

    pattern: str
    quote: str
    context: str | None = None


@dataclass
class PatternCategory:
    """A category of communication patterns with examples."""

    name: str
    description: str
    patterns: list[PatternExample] = field(default_factory=list)

    def add_example(self, pattern: str, quote: str, context: str | None = None) -> None:
        """Add an example to this category."""
        self.patterns.append(PatternExample(pattern=pattern, quote=quote, context=context))


@dataclass
class StyleAnalysisResult:
    """Complete analysis of Sean's communication style."""

    total_messages_analyzed: int
    date_range_start: str | None
    date_range_end: str | None

    hedging: PatternCategory
    disagreement: PatternCategory
    pausing: PatternCategory
    resuming: PatternCategory
    revision: PatternCategory
    acknowledgment: PatternCategory
    action_requests: PatternCategory
    follow_ups: PatternCategory
    tone_markers: PatternCategory

    def all_categories(self) -> list[PatternCategory]:
        """Return all pattern categories."""
        return [
            self.hedging,
            self.disagreement,
            self.pausing,
            self.resuming,
            self.revision,
            self.acknowledgment,
            self.action_requests,
            self.follow_ups,
            self.tone_markers,
        ]


class StyleAnalyzer:
    """Analyzes message history to extract communication patterns."""

    # Pattern definitions for each category
    HEDGING_PATTERNS = [
        (r"\bI suppose\b", "I suppose"),
        (r"\bmaybe\b", "maybe"),
        (r"\bprobably\b", "probably"),
        (r"\bLike a?\s*\w+", "Like a..."),
        (r"\bI think\b", "I think"),
        (r"\bI guess\b", "I guess"),
        (r"\bpossibly\b", "possibly"),
        (r"\bmight\b", "might"),
        (r"\bcould be\b", "could be"),
        (r"\bish\b", "-ish suffix"),
        (r"\bkind of\b", "kind of"),
        (r"\bsort of\b", "sort of"),
        (r"\bnot sure\b", "not sure"),
    ]

    DISAGREEMENT_PATTERNS = [
        (r"\bhmm\b", "hmm"),
        (r"\bactually\b", "actually"),
        (r"\bwell\b", "well"),
        (r"\bnot really\b", "not really"),
        (r"\bnot quite\b", "not quite"),
        (r"\bI mean\b", "I mean"),
        (r"\beh\b", "eh"),
    ]

    PAUSING_PATTERNS = [
        (r"\bone sec\b", "one sec"),
        (r"\bgimme a\b", "gimme a"),
        (r"\bhang on\b", "hang on"),
        (r"\bbrb\b", "brb"),
        (r"\bback in\b", "back in"),
        (r"\blet me\b", "let me"),
    ]

    RESUMING_PATTERNS = [
        (r"\bok so\b", "ok so"),
        (r"\balright\b", "alright"),
        (r"\bso anyway\b", "so anyway"),
        (r"\bback\b", "back"),
        (r"\bk\b", "k"),
        (r"\bokay\b", "okay"),
    ]

    REVISION_PATTERNS = [
        (r"\bwait\b", "wait"),
        (r"\boh\b", "oh"),
        (r"\bnvm\b", "nvm"),
        (r"\bnevermind\b", "nevermind"),
        (r"\bsorry\b", "sorry"),
        (r"\bactually\b", "actually"),
        (r"\bI meant\b", "I meant"),
        (r"\*\w+", "*correction"),
    ]

    ACKNOWLEDGMENT_PATTERNS = [
        (r"\bYep\b", "Yep"),
        (r"\byep\b", "yep"),
        (r"\bMk\b", "Mk"),
        (r"\bmk\b", "mk"),
        (r"\bkk\b", "kk"),
        (r"\bgotcha\b", "gotcha"),
        (r"\bcool\b", "cool"),
        (r"\bnice\b", "nice"),
        (r"\bgreat\b", "great"),
        (r"\bperfect\b", "perfect"),
        (r"\bthank(?:s| you)\b", "thanks/thank you"),
        (r"\bty\b", "ty"),
        (r"\bsounds good\b", "sounds good"),
        (r"\bworks for me\b", "works for me"),
    ]

    ACTION_REQUEST_PATTERNS = [
        (r"\bcan you\b", "can you"),
        (r"\bcould you\b", "could you"),
        (r"\bplease\b", "please"),
        (r"\bwhen you get a chance\b", "when you get a chance"),
        (r"\bif you could\b", "if you could"),
        (r"\bwould you\b", "would you"),
        (r"\blet me know\b", "let me know"),
    ]

    FOLLOW_UP_PATTERNS = [
        (r"\bjust checking\b", "just checking"),
        (r"\bany update\b", "any update"),
        (r"\bhow's\b", "how's"),
        (r"\bwhere are we\b", "where are we"),
        (r"\bstatus\b", "status"),
        (r"\bhave you\b", "have you"),
        (r"\bdid you\b", "did you"),
    ]

    def __init__(self, telegram_service=None):
        """
        Initialize the style analyzer.

        Args:
            telegram_service: Optional TelegramClientService instance.
                              If not provided, will be created when needed.
        """
        self._telegram_service = telegram_service

    async def _get_telegram_service(self):
        """Get or create TelegramClientService."""
        if self._telegram_service is None:
            from services.telegram_client import TelegramClientService
            self._telegram_service = TelegramClientService()
        return self._telegram_service

    async def fetch_authentic_messages(
        self,
        chat_id: str | int,
        before_date: datetime | None = None,
    ) -> list["TelegramMessage"]:
        """
        Fetch outgoing messages before a specific date for analysis.

        Args:
            chat_id: Username or chat ID to fetch messages from.
            before_date: Only include messages before this date.
                         Defaults to 2026-01-01 00:00:00 UTC.

        Returns:
            List of TelegramMessage objects (outgoing messages only).
        """
        if before_date is None:
            before_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        telegram = await self._get_telegram_service()
        messages = await telegram.get_all_messages(
            chat_id=chat_id,
            before_date=before_date,
            direction_filter="outgoing",
        )

        logger.info(
            "Fetched %d outgoing messages from %s before %s",
            len(messages),
            chat_id,
            before_date.isoformat(),
        )
        return messages

    def analyze_patterns(
        self,
        messages: list["TelegramMessage"],
    ) -> StyleAnalysisResult:
        """
        Analyze messages to extract communication patterns.

        Args:
            messages: List of TelegramMessage objects to analyze.

        Returns:
            StyleAnalysisResult with patterns extracted across all categories.
        """
        # Initialize categories
        hedging = PatternCategory(
            name="Hedging",
            description="Expressions of uncertainty or softened assertions",
        )
        disagreement = PatternCategory(
            name="Disagreement",
            description="Ways of expressing disagreement or correction",
        )
        pausing = PatternCategory(
            name="Pausing",
            description="Signals for taking a break or needing time",
        )
        resuming = PatternCategory(
            name="Resuming",
            description="Ways of coming back to a conversation",
        )
        revision = PatternCategory(
            name="Revision",
            description="Self-corrections and updates to previous statements",
        )
        acknowledgment = PatternCategory(
            name="Acknowledgment",
            description="Ways of confirming receipt or agreement",
        )
        action_requests = PatternCategory(
            name="Action Requests",
            description="Patterns for asking others to do things",
        )
        follow_ups = PatternCategory(
            name="Follow-ups",
            description="Checking in on pending matters",
        )
        tone_markers = PatternCategory(
            name="Tone Markers",
            description="Punctuation, capitalization, and informal style markers",
        )

        # Track seen patterns to avoid duplicates
        seen_examples: dict[str, set[str]] = {
            "hedging": set(),
            "disagreement": set(),
            "pausing": set(),
            "resuming": set(),
            "revision": set(),
            "acknowledgment": set(),
            "action_requests": set(),
            "follow_ups": set(),
        }

        # Tone marker tracking
        typo_examples: list[str] = []
        punctuation_examples: list[str] = []
        capitalization_examples: list[str] = []

        # Date range tracking
        dates = [m.date for m in messages if m.date]
        date_range_start = min(dates) if dates else None
        date_range_end = max(dates) if dates else None

        # Analyze each message
        for msg in messages:
            if not msg.text:
                continue

            text = msg.text

            # Analyze each pattern category
            self._extract_patterns(
                text, self.HEDGING_PATTERNS, hedging, seen_examples["hedging"]
            )
            self._extract_patterns(
                text, self.DISAGREEMENT_PATTERNS, disagreement, seen_examples["disagreement"]
            )
            self._extract_patterns(
                text, self.PAUSING_PATTERNS, pausing, seen_examples["pausing"]
            )
            self._extract_patterns(
                text, self.RESUMING_PATTERNS, resuming, seen_examples["resuming"]
            )
            self._extract_patterns(
                text, self.REVISION_PATTERNS, revision, seen_examples["revision"]
            )
            self._extract_patterns(
                text, self.ACKNOWLEDGMENT_PATTERNS, acknowledgment, seen_examples["acknowledgment"]
            )
            self._extract_patterns(
                text, self.ACTION_REQUEST_PATTERNS, action_requests, seen_examples["action_requests"]
            )
            self._extract_patterns(
                text, self.FOLLOW_UP_PATTERNS, follow_ups, seen_examples["follow_ups"]
            )

            # Analyze tone markers
            self._analyze_tone_markers(
                text, typo_examples, punctuation_examples, capitalization_examples
            )

        # Add tone marker examples
        for example in typo_examples[:5]:
            tone_markers.add_example("Typo tolerance", example, "Natural typos are kept")
        for example in punctuation_examples[:5]:
            tone_markers.add_example("Casual punctuation", example, "Informal punctuation style")
        for example in capitalization_examples[:5]:
            tone_markers.add_example("Lowercase preference", example, "Lowercase for casual tone")

        return StyleAnalysisResult(
            total_messages_analyzed=len(messages),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            hedging=hedging,
            disagreement=disagreement,
            pausing=pausing,
            resuming=resuming,
            revision=revision,
            acknowledgment=acknowledgment,
            action_requests=action_requests,
            follow_ups=follow_ups,
            tone_markers=tone_markers,
        )

    def _extract_patterns(
        self,
        text: str,
        patterns: list[tuple[str, str]],
        category: PatternCategory,
        seen: set[str],
    ) -> None:
        """Extract patterns from text and add to category."""
        for regex, pattern_name in patterns:
            matches = re.finditer(regex, text, re.IGNORECASE)
            for match in matches:
                # Use the actual matched text as the quote
                quote = match.group(0)
                # Limit to first 5 unique examples per pattern
                if quote.lower() not in seen and len([
                    p for p in category.patterns if p.pattern == pattern_name
                ]) < 5:
                    seen.add(quote.lower())
                    # Extract context (surrounding text)
                    start = max(0, match.start() - 20)
                    end = min(len(text), match.end() + 20)
                    context = text[start:end].strip()
                    if start > 0:
                        context = "..." + context
                    if end < len(text):
                        context = context + "..."
                    category.add_example(pattern_name, quote, context)

    def _analyze_tone_markers(
        self,
        text: str,
        typo_examples: list[str],
        punctuation_examples: list[str],
        capitalization_examples: list[str],
    ) -> None:
        """Analyze tone markers in text."""
        # Check for potential typos (repeated characters, missing spaces)
        if re.search(r"[a-z]{2,}[A-Z]", text):  # Missing space before capital
            if len(typo_examples) < 10:
                typo_examples.append(text[:50] if len(text) > 50 else text)
        if re.search(r"(\w)\1{2,}", text):  # Triple letters
            if len(typo_examples) < 10:
                typo_examples.append(text[:50] if len(text) > 50 else text)

        # Check for casual punctuation
        if text.endswith(".."):  # Double period
            if len(punctuation_examples) < 10:
                punctuation_examples.append(text[:50] if len(text) > 50 else text)
        if "!!" in text or "??" in text:  # Multiple punctuation
            if len(punctuation_examples) < 10:
                punctuation_examples.append(text[:50] if len(text) > 50 else text)

        # Check for lowercase preference (sentences starting with lowercase)
        if len(text) > 0 and text[0].islower():
            if len(capitalization_examples) < 10:
                capitalization_examples.append(text[:50] if len(text) > 50 else text)

    def generate_sean_md(self, analysis_result: StyleAnalysisResult) -> str:
        """
        Generate SEAN.md content from style analysis results.

        Args:
            analysis_result: The StyleAnalysisResult from analyze_patterns().

        Returns:
            Complete Markdown string documenting Sean's communication style.
        """
        sections = []

        # Title and Metadata
        sections.append("# SEAN.md - Communication Style Guide")
        sections.append("")
        sections.append("*Auto-generated from message analysis*")
        sections.append("")
        sections.append(f"- **Messages analyzed**: {analysis_result.total_messages_analyzed}")
        if analysis_result.date_range_start and analysis_result.date_range_end:
            sections.append(
                f"- **Date range**: {analysis_result.date_range_start[:10]} to "
                f"{analysis_result.date_range_end[:10]}"
            )
        sections.append("")

        # Executive Summary
        sections.append("## Executive Summary")
        sections.append("")
        sections.append(
            "Sean's communication style is characterized by brevity, informality, and "
            "authenticity. Messages tend to be short and direct, with natural typos and "
            "casual punctuation preserved. The tone is conversational rather than formal, "
            "with frequent use of acknowledgment markers like 'Yep', 'Mk', and 'cool'."
        )
        sections.append("")
        sections.append("**Key characteristics:**")
        sections.append("")
        sections.append("- **Brevity**: Prefer short responses over verbose explanations")
        sections.append("- **Casualness**: Use informal language and allow natural typos")
        sections.append("- **Directness**: Get to the point without excessive preamble")
        sections.append("- **Authenticity**: Sound human, not robotic or over-polished")
        sections.append("")

        # Core Communication Patterns
        sections.append("---")
        sections.append("")
        sections.append("## Core Communication Patterns")
        sections.append("")

        # Generate section for each pattern category
        for category in analysis_result.all_categories():
            if category.patterns:
                sections.append(f"### {category.name}")
                sections.append("")
                sections.append(f"*{category.description}*")
                sections.append("")

                # Group by pattern type
                patterns_by_type: dict[str, list[PatternExample]] = {}
                for p in category.patterns:
                    if p.pattern not in patterns_by_type:
                        patterns_by_type[p.pattern] = []
                    patterns_by_type[p.pattern].append(p)

                for pattern_type, examples in patterns_by_type.items():
                    sections.append(f"**{pattern_type}**")
                    for ex in examples[:3]:  # Limit to 3 examples
                        sections.append(f"- \"{ex.quote}\"")
                        if ex.context:
                            sections.append(f"  - Context: *{ex.context}*")
                    sections.append("")

        # Anti-Patterns Section
        sections.append("---")
        sections.append("")
        sections.append("## Anti-Patterns: What NOT to Do")
        sections.append("")
        sections.append(
            "The following patterns should be avoided as they do not match Sean's "
            "communication style."
        )
        sections.append("")
        sections.append("### Do NOT use emojis")
        sections.append("")
        sections.append(
            "Sean's messages do not include emojis. Avoid all emoji usage including:"
        )
        sections.append("")
        sections.append("- Smiley faces (😀, 😊, 🙂)")
        sections.append("- Thumbs up (👍)")
        sections.append("- Hearts or reactions (❤️, 💯)")
        sections.append("- Any other emoji characters")
        sections.append("")
        sections.append("### Do NOT use markdown formatting")
        sections.append("")
        sections.append(
            "Telegram messages should be plain text without markdown:"
        )
        sections.append("")
        sections.append("- No **bold** text")
        sections.append("- No *italic* text")
        sections.append("- No `code` blocks")
        sections.append("- No bullet points or numbered lists")
        sections.append("- No headers or structured formatting")
        sections.append("")
        sections.append("### Do NOT use verbose confirmations")
        sections.append("")
        sections.append(
            "Avoid lengthy acknowledgments. Sean's confirmations are brief:"
        )
        sections.append("")
        sections.append("| Instead of... | Write... |")
        sections.append("|--------------|----------|")
        sections.append("| \"I have received your message and will process it accordingly.\" | \"Mk\" |")
        sections.append("| \"Thank you for letting me know. I appreciate the update.\" | \"cool thanks\" |")
        sections.append("| \"That sounds like a good plan. I'm on board with that.\" | \"Yep sounds good\" |")
        sections.append("| \"Understood. I will take care of that right away.\" | \"on it\" |")
        sections.append("")
        sections.append("### Do NOT over-explain")
        sections.append("")
        sections.append(
            "Avoid providing excessive context or reasoning. Trust that the "
            "recipient understands the situation."
        )
        sections.append("")
        sections.append("| Instead of... | Write... |")
        sections.append("|--------------|----------|")
        sections.append("| \"I think it would be best if we scheduled the meeting for tomorrow because I have a conflict today and want to be fully present.\" | \"tomorrow works better\" |")
        sections.append("| \"I apologize for the delay in responding. I was in meetings all day.\" | \"sorry, just seeing this\" |")
        sections.append("")

        # Sample Transformations
        sections.append("---")
        sections.append("")
        sections.append("## Sample Transformations")
        sections.append("")
        sections.append(
            "These examples show how to transform formal/robotic text into Sean's style."
        )
        sections.append("")
        sections.append("### Requests")
        sections.append("")
        sections.append("**Formal:** \"Would it be possible for you to check on the status of the reservation?\"")
        sections.append("")
        sections.append("**Sean:** \"can you check on the reservation please\"")
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("### Follow-ups")
        sections.append("")
        sections.append("**Formal:** \"I wanted to follow up on my previous message regarding the hotel booking. Have you had a chance to receive any updates?\"")
        sections.append("")
        sections.append("**Sean:** \"just checking in on the hotel\"")
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("### Hedging")
        sections.append("")
        sections.append("**Formal:** \"I'm not entirely certain, but I believe the appointment might be scheduled for Tuesday.\"")
        sections.append("")
        sections.append("**Sean:** \"I think it's tuesday? not 100% sure\"")
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("### Corrections")
        sections.append("")
        sections.append("**Formal:** \"I need to make a correction to my previous statement. The meeting is actually at 3pm, not 2pm.\"")
        sections.append("")
        sections.append("**Sean:** \"wait, its 3pm not 2\"")
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("### Acknowledgments")
        sections.append("")
        sections.append("**Formal:** \"Thank you for the information. I will proceed accordingly.\"")
        sections.append("")
        sections.append("**Sean:** \"cool ty\"")
        sections.append("")

        # Implementation Guidelines
        sections.append("---")
        sections.append("")
        sections.append("## Implementation Guidelines")
        sections.append("")
        sections.append(
            "When generating text in Sean's voice, follow these rules:"
        )
        sections.append("")
        sections.append("1. **Keep it short**: If a response can be one word, use one word")
        sections.append("2. **Allow typos**: Minor typos are acceptable and add authenticity")
        sections.append("3. **Use lowercase**: Start sentences with lowercase for casual tone")
        sections.append("4. **Casual punctuation**: Periods are optional, multiple question marks are ok")
        sections.append("5. **No formalities**: Skip \"Dear\", \"Best regards\", \"I hope this finds you well\"")
        sections.append("6. **Be direct**: State the need or question without preamble")
        sections.append("7. **Natural pauses**: Use \"one sec\", \"brb\", \"gimme a min\" when appropriate")
        sections.append("8. **Simple acknowledgments**: \"Yep\", \"Mk\", \"cool\", \"ty\" instead of full sentences")
        sections.append("")

        return "\n".join(sections)


__all__ = [
    "StyleAnalyzer",
    "StyleAnalysisResult",
    "PatternCategory",
    "PatternExample",
]
