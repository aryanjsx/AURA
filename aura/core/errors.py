"""
AURA — Unified error taxonomy.

All AURA-internal failure paths raise one of these exceptions so that the
centralised error handler can translate them into structured results
without falling back to a generic ``Exception`` catch-all.
"""

from __future__ import annotations


class AuraError(Exception):
    """Root of all AURA-raised exceptions."""


class ConfigError(AuraError):
    """Raised when required configuration keys are missing or invalid."""


class SchemaError(AuraError):
    """Raised when a command payload violates the strict DSL schema."""


class SandboxError(AuraError):
    """Raised when a filesystem path escapes the sandbox root."""


class PluginError(AuraError):
    """Raised when a plugin cannot be loaded or registered."""


class PolicyError(AuraError):
    """Raised when an execution is blocked by policy."""


class RegistryError(AuraError):
    """Raised for unknown / duplicate / direct-access violations."""


class ExecutionError(AuraError):
    """Wraps any unexpected failure inside a registered handler."""


class PermissionDenied(AuraError):
    """Raised when a command's permission level exceeds the source's cap."""


class ConfirmationDenied(AuraError):
    """Raised when the user explicitly declines confirmation."""


class ConfirmationTimeout(AuraError):
    """Raised when the safety gate times out waiting for confirmation."""


class RateLimitError(AuraError):
    """Raised when the rate limiter rejects a command."""


class PlanError(AuraError):
    """Raised for an invalid or failed multi-step task plan."""


class EngineError(AuraError):
    """Raised for ExecutionEngine misuse or missing executors."""
