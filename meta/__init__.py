"""
Meta module for Frank Bot - scripting API and execution engine.

Provides:
- FrankAPI: Synchronous API namespace for scripting
- Script storage and parsing utilities
- Job storage and management
- Script executor with timeout and output capture
- Introspection for documentation generation
"""

from meta.api import FrankAPI

__all__ = ["FrankAPI"]
