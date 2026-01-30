"""
Personality Loader Service.

Loads personality definitions from ./personalities/*.json files.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default personalities directory
DEFAULT_PERSONALITIES_DIR = "./personalities"


@dataclass
class CommunicationStyle:
    """Communication style traits."""

    tone: str = "professional"
    verbosity: str = "concise"
    formality: float = 0.6
    emotiveness: float = 0.3
    emoji_usage: str = "rare"


@dataclass
class DecisionMaking:
    """Decision-making traits."""

    risk_tolerance: str = "cautious"
    autonomy: str = "supervised"
    patience_level: str = "patient"
    negotiation_style: str = "collaborative"


@dataclass
class Expertise:
    """Expertise/domain traits."""

    domains: list[str] = field(default_factory=list)
    persona: str = "personal assistant"
    background: str = ""


@dataclass
class Traits:
    """All personality traits."""

    communication_style: CommunicationStyle = field(default_factory=CommunicationStyle)
    decision_making: DecisionMaking = field(default_factory=DecisionMaking)
    expertise: Expertise = field(default_factory=Expertise)


@dataclass
class SystemPromptAdditions:
    """Additions to inject into system prompts."""

    preamble: str = ""
    guidelines: list[str] = field(default_factory=list)
    examples: list[dict[str, str]] = field(default_factory=list)
    postscript: str = ""


@dataclass
class PolicyOverrides:
    """Default policy settings for this personality."""

    max_spend_without_approval: float | None = None
    max_messages_per_hour: int | None = None
    require_approval_for: list[str] | None = None
    follow_up_hours: float | None = None


@dataclass
class ModelPreferences:
    """LLM configuration preferences."""

    temperature: float = 0.7
    preferred_model: str | None = None


@dataclass
class Personality:
    """
    A complete personality definition.

    Matches schemas/personality.schema.json.
    """

    id: str
    name: str
    description: str = ""
    traits: Traits = field(default_factory=Traits)
    system_prompt_additions: SystemPromptAdditions = field(default_factory=SystemPromptAdditions)
    policy_overrides: PolicyOverrides = field(default_factory=PolicyOverrides)
    model_preferences: ModelPreferences = field(default_factory=ModelPreferences)

    def format_for_prompt(self) -> str:
        """
        Format this personality for inclusion in a system prompt.

        Returns a section of text describing how the agent should behave.
        """
        lines = []

        # Preamble
        if self.system_prompt_additions.preamble:
            lines.append(self.system_prompt_additions.preamble)
            lines.append("")

        # Core traits section
        lines.append("## Your Personality")
        lines.append("")
        lines.append(f"**Name**: {self.name}")
        if self.description:
            lines.append(f"**Role**: {self.description}")
        lines.append("")

        # Communication style
        cs = self.traits.communication_style
        lines.append("**Communication Style**:")
        lines.append(f"- Tone: {cs.tone}")
        lines.append(f"- Verbosity: {cs.verbosity}")
        if cs.emoji_usage != "never":
            lines.append(f"- Emojis: {cs.emoji_usage}")
        lines.append("")

        # Decision making
        dm = self.traits.decision_making
        lines.append("**Decision Making**:")
        lines.append(f"- Risk tolerance: {dm.risk_tolerance}")
        lines.append(f"- Autonomy level: {dm.autonomy}")
        lines.append(f"- Patience: {dm.patience_level}")
        if dm.negotiation_style != "collaborative":
            lines.append(f"- Negotiation: {dm.negotiation_style}")
        lines.append("")

        # Expertise
        exp = self.traits.expertise
        if exp.domains:
            lines.append(f"**Expertise**: {', '.join(exp.domains)}")
        if exp.persona:
            lines.append(f"**Persona**: {exp.persona}")
        if exp.background:
            lines.append(f"**Background**: {exp.background}")
        lines.append("")

        # Guidelines
        if self.system_prompt_additions.guidelines:
            lines.append("## Guidelines")
            lines.append("")
            for guideline in self.system_prompt_additions.guidelines:
                lines.append(f"- {guideline}")
            lines.append("")

        # Examples
        if self.system_prompt_additions.examples:
            lines.append("## Example Responses")
            lines.append("")
            for ex in self.system_prompt_additions.examples:
                lines.append(f"**Situation**: {ex.get('situation', 'N/A')}")
                lines.append(f"**Response**: {ex.get('response', 'N/A')}")
                lines.append("")

        # Postscript
        if self.system_prompt_additions.postscript:
            lines.append(self.system_prompt_additions.postscript)

        return "\n".join(lines)


def _parse_personality(data: dict[str, Any]) -> Personality:
    """Parse a personality from JSON data."""
    # Parse traits
    traits_data = data.get("traits", {})

    cs_data = traits_data.get("communicationStyle", {})
    communication_style = CommunicationStyle(
        tone=cs_data.get("tone", "professional"),
        verbosity=cs_data.get("verbosity", "concise"),
        formality=cs_data.get("formality", 0.6),
        emotiveness=cs_data.get("emotiveness", 0.3),
        emoji_usage=cs_data.get("emoji_usage", "rare"),
    )

    dm_data = traits_data.get("decisionMaking", {})
    decision_making = DecisionMaking(
        risk_tolerance=dm_data.get("riskTolerance", "cautious"),
        autonomy=dm_data.get("autonomy", "supervised"),
        patience_level=dm_data.get("patienceLevel", "patient"),
        negotiation_style=dm_data.get("negotiationStyle", "collaborative"),
    )

    exp_data = traits_data.get("expertise", {})
    expertise = Expertise(
        domains=exp_data.get("domains", []),
        persona=exp_data.get("persona", "personal assistant"),
        background=exp_data.get("background", ""),
    )

    traits = Traits(
        communication_style=communication_style,
        decision_making=decision_making,
        expertise=expertise,
    )

    # Parse system prompt additions
    spa_data = data.get("systemPromptAdditions", {})
    system_prompt_additions = SystemPromptAdditions(
        preamble=spa_data.get("preamble", ""),
        guidelines=spa_data.get("guidelines", []),
        examples=spa_data.get("examples", []),
        postscript=spa_data.get("postscript", ""),
    )

    # Parse policy overrides
    po_data = data.get("policyOverrides", {})
    policy_overrides = PolicyOverrides(
        max_spend_without_approval=po_data.get("maxSpendWithoutApproval"),
        max_messages_per_hour=po_data.get("maxMessagesPerHour"),
        require_approval_for=po_data.get("requireApprovalFor"),
        follow_up_hours=po_data.get("followUpHours"),
    )

    # Parse model preferences
    mp_data = data.get("modelPreferences", {})
    model_preferences = ModelPreferences(
        temperature=mp_data.get("temperature", 0.7),
        preferred_model=mp_data.get("preferredModel"),
    )

    return Personality(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        traits=traits,
        system_prompt_additions=system_prompt_additions,
        policy_overrides=policy_overrides,
        model_preferences=model_preferences,
    )


class PersonalityLoader:
    """
    Service for loading personality definitions.

    Loads from ./personalities/*.json by default.
    Caches loaded personalities in memory.
    """

    def __init__(self, personalities_dir: str | None = None):
        """
        Initialize the personality loader.

        Args:
            personalities_dir: Directory containing personality JSON files.
                Defaults to ./personalities/
        """
        self._dir = personalities_dir or os.getenv(
            "PERSONALITIES_DIR", DEFAULT_PERSONALITIES_DIR
        )
        self._cache: dict[str, Personality] = {}
        self._loaded = False

    def _load_all(self) -> None:
        """Load all personality files from disk."""
        if self._loaded:
            return

        if not os.path.isdir(self._dir):
            logger.warning("Personalities directory not found: %s", self._dir)
            self._loaded = True
            return

        for filename in os.listdir(self._dir):
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(self._dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    personality = _parse_personality(data)
                    self._cache[personality.id] = personality
                    logger.debug("Loaded personality: %s", personality.id)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load personality from %s: %s", filepath, e)

        self._loaded = True
        logger.info("Loaded %d personalities from %s", len(self._cache), self._dir)

    def get(self, personality_id: str) -> Personality | None:
        """
        Get a personality by ID.

        Args:
            personality_id: The personality ID (e.g., "concierge", "researcher")

        Returns:
            The Personality if found, None otherwise
        """
        self._load_all()
        return self._cache.get(personality_id)

    def get_or_default(self, personality_id: str | None) -> Personality:
        """
        Get a personality by ID, falling back to default.

        Args:
            personality_id: The personality ID (or None for default)

        Returns:
            The requested Personality, or the default personality,
            or a hardcoded fallback if no default exists
        """
        self._load_all()

        if personality_id and personality_id in self._cache:
            return self._cache[personality_id]

        # Try to get default
        if "default" in self._cache:
            return self._cache["default"]

        # Hardcoded fallback
        logger.warning(
            "Personality '%s' not found and no default available, using hardcoded fallback",
            personality_id,
        )
        return Personality(
            id="fallback",
            name="Default Assistant",
            description="Balanced personality for general-purpose tasks",
        )

    def list_all(self) -> list[Personality]:
        """
        List all available personalities.

        Returns:
            List of all loaded personalities
        """
        self._load_all()
        return list(self._cache.values())

    def list_ids(self) -> list[str]:
        """
        List all available personality IDs.

        Returns:
            List of personality IDs
        """
        self._load_all()
        return list(self._cache.keys())

    def reload(self) -> None:
        """Force reload all personalities from disk."""
        self._cache.clear()
        self._loaded = False
        self._load_all()


# Singleton instance
_personality_loader: PersonalityLoader | None = None


def get_personality_loader() -> PersonalityLoader:
    """Get the global personality loader instance."""
    global _personality_loader
    if _personality_loader is None:
        _personality_loader = PersonalityLoader()
    return _personality_loader


__all__ = [
    "Personality",
    "PersonalityLoader",
    "Traits",
    "CommunicationStyle",
    "DecisionMaking",
    "Expertise",
    "get_personality_loader",
]
