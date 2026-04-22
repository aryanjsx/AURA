"""
AURA — Plugin Safety Manifest loader.

Reads ``plugins_manifest.yaml`` and exposes a typed, read-only view used
by the plugin loader to enforce that *every* plugin-declared action
matches an externally-reviewed policy entry.  Plugins cannot self-declare
trust — the manifest is the source of truth.

Contract
--------
* Absent manifest file ⇒ :class:`PluginManifestError`.
* Unknown action at load time ⇒ registration is refused.
* Declaration mismatch (permission_level / destructive) ⇒ refused.
* Destructive action without at least one ``audit_events`` entry ⇒
  refused at manifest-parse time (this is the "destructive command
  MUST have audit coverage" rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from aura.core.errors import AuraError
from aura.security.permissions import PermissionLevel


class PluginManifestError(AuraError):
    """Raised when the manifest is missing, malformed, or violated."""


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    plugin: str
    action: str
    permission_level: PermissionLevel
    destructive: bool
    audit_events: tuple[str, ...]


class PluginManifest:
    def __init__(self, entries: dict[str, ManifestEntry]) -> None:
        self._by_action = dict(entries)

    # ------------------------------------------------------------------
    # Test helper — NEVER use in production.
    # ------------------------------------------------------------------
    @classmethod
    def permissive(cls) -> "PluginManifest":
        """Return a manifest that accepts any action/plugin combination.

        This exists for unit tests that don't exercise manifest enforcement.
        Production code paths (``main.bootstrap`` and the worker) load the
        real manifest from ``plugins_manifest.yaml`` instead.
        """
        return _PermissiveManifest()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "PluginManifest":
        p = Path(path)
        if not p.exists():
            raise PluginManifestError(
                f"Plugin manifest not found at {p}. This file is the "
                f"authoritative list of allowed plugin actions and must "
                f"exist before AURA starts."
            )
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PluginManifestError(f"Manifest {p} is not valid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise PluginManifestError(
                f"Manifest {p} must be a mapping at top level"
            )
        plugins = raw.get("plugins")
        if not isinstance(plugins, dict) or not plugins:
            raise PluginManifestError(
                f"Manifest {p} has no 'plugins' mapping"
            )

        entries: dict[str, ManifestEntry] = {}
        for plugin_name, plugin_body in plugins.items():
            if not isinstance(plugin_name, str) or not plugin_name.strip():
                raise PluginManifestError(
                    f"Manifest plugin name must be non-empty str: {plugin_name!r}"
                )
            if not isinstance(plugin_body, dict):
                raise PluginManifestError(
                    f"Plugin {plugin_name!r} body must be a mapping"
                )
            actions = plugin_body.get("actions")
            if not isinstance(actions, dict) or not actions:
                raise PluginManifestError(
                    f"Plugin {plugin_name!r} has no 'actions' mapping"
                )

            for action, action_body in actions.items():
                if not isinstance(action, str) or not action.strip():
                    raise PluginManifestError(
                        f"{plugin_name}: action name must be non-empty str "
                        f"(got {action!r})"
                    )
                if action in entries:
                    raise PluginManifestError(
                        f"Duplicate action {action!r} in manifest "
                        f"(already declared by {entries[action].plugin!r})"
                    )
                if not isinstance(action_body, dict):
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: body must be a mapping"
                    )

                level_raw = action_body.get("permission_level")
                if level_raw is None:
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: 'permission_level' is required"
                    )
                try:
                    level = PermissionLevel.parse(level_raw)
                except (TypeError, ValueError) as exc:
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: invalid permission_level "
                        f"{level_raw!r} ({exc})"
                    ) from exc

                destructive = action_body.get("destructive")
                if not isinstance(destructive, bool):
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: 'destructive' must be a "
                        f"bool, got {type(destructive).__name__}"
                    )

                events_raw = action_body.get("audit_events", [])
                if not isinstance(events_raw, list):
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: 'audit_events' must be a "
                        f"list, got {type(events_raw).__name__}"
                    )
                events: list[str] = []
                for ev in events_raw:
                    if not isinstance(ev, str) or not ev.strip():
                        raise PluginManifestError(
                            f"{plugin_name}.{action}: audit_events entries "
                            f"must be non-empty str (got {ev!r})"
                        )
                    events.append(ev.strip())

                if destructive and not events:
                    raise PluginManifestError(
                        f"{plugin_name}.{action}: destructive actions "
                        f"MUST declare at least one audit_events entry"
                    )

                entries[action] = ManifestEntry(
                    plugin=plugin_name,
                    action=action,
                    permission_level=level,
                    destructive=destructive,
                    audit_events=tuple(events),
                )
        return cls(entries)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get(self, action: str) -> ManifestEntry | None:
        return self._by_action.get(action)

    def actions(self) -> Iterable[ManifestEntry]:
        return self._by_action.values()

    # ------------------------------------------------------------------
    # Enforcement helper
    # ------------------------------------------------------------------
    def check(
        self,
        *,
        plugin: str,
        action: str,
        permission_level: PermissionLevel,
        destructive: bool,
    ) -> ManifestEntry:
        """Return the manifest entry, or raise if the plugin disagrees."""
        entry = self.get(action)
        if entry is None:
            raise PluginManifestError(
                f"Plugin {plugin!r} declared unknown action {action!r}. "
                f"Add it to plugins_manifest.yaml after review."
            )
        if entry.plugin != plugin:
            raise PluginManifestError(
                f"Action {action!r} is owned by plugin {entry.plugin!r} "
                f"per manifest, not {plugin!r}"
            )
        if entry.permission_level is not permission_level:
            raise PluginManifestError(
                f"{plugin}.{action}: permission_level mismatch — "
                f"plugin says {permission_level.value!r}, "
                f"manifest says {entry.permission_level.value!r}"
            )
        if bool(entry.destructive) is not bool(destructive):
            raise PluginManifestError(
                f"{plugin}.{action}: destructive flag mismatch — "
                f"plugin says {bool(destructive)!r}, "
                f"manifest says {bool(entry.destructive)!r}"
            )
        return entry


class _PermissiveManifest(PluginManifest):
    """Test-only manifest that accepts any action the caller supplies."""

    def __init__(self) -> None:
        super().__init__({})

    def check(
        self,
        *,
        plugin: str,
        action: str,
        permission_level: PermissionLevel,
        destructive: bool,
    ) -> ManifestEntry:
        return ManifestEntry(
            plugin=plugin,
            action=action,
            permission_level=permission_level,
            destructive=bool(destructive),
            audit_events=(),
        )


# ---------------------------------------------------------------------------
# Default discovery
# ---------------------------------------------------------------------------
def default_manifest_path(project_root: Path | None = None) -> Path:
    root = project_root or Path.cwd()
    return root / "plugins_manifest.yaml"


# ---------------------------------------------------------------------------
# Manifest hash (cross-process binding)
# ---------------------------------------------------------------------------
def manifest_sha256(path: str | Path) -> str:
    """Compute the SHA-256 hex digest of the manifest file on disk.

    Used by the main process to bind the manifest across to the worker
    via the ``AURA_MANIFEST_SHA256`` environment variable; the worker
    recomputes this locally and refuses to start on mismatch.
    """
    import hashlib

    p = Path(path)
    if not p.exists():
        raise PluginManifestError(
            f"Cannot hash manifest: file does not exist: {p}"
        )
    return hashlib.sha256(p.read_bytes()).hexdigest()
