"""Undo for file changes made in Agent mode.

Before :class:`UndoableFileWriteTool` writes a file, it saves the old contents
(or notes that the file is new) in a journal under ``~/.locus/undo``. Undoing
puts the old contents back, or deletes a file the agent created, but only if
the file still holds what the agent wrote, so later edits are never lost.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from locus.core.types import ToolResult
from locus.tools.file_write import FileWriteTool

#: Files bigger than this aren't backed up, so their changes can't be undone.
MAX_BACKUP_BYTES = 10 * 1024 * 1024
#: Older entries are dropped (with their backups) past this many.
MAX_ENTRIES = 100


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class UndoEntry:
    id: str
    path: str
    created: bool  # the file didn't exist before the change
    written_sha256: str
    timestamp: float


class UndoJournal:
    """Saved file contents from before each change, newest last."""

    def __init__(self, root: Optional[Path] = None) -> None:
        if root is None:
            from locus.core.paths import get_config_dir

            root = Path(get_config_dir()) / "undo"
        self.root = Path(root)
        self._lock = threading.Lock()

    @property
    def _index(self) -> Path:
        return self.root / "index.json"

    def _load(self) -> List[UndoEntry]:
        try:
            rows = json.loads(self._index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [UndoEntry(**row) for row in rows if isinstance(row, dict)]

    def _save(self, entries: List[UndoEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self._index.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(e) for e in entries]), encoding="utf-8")
        tmp.replace(self._index)

    def _backup(self, entry_id: str) -> Path:
        return self.root / f"{entry_id}.bak"

    def record(self, path: Path, previous: Optional[bytes], written: bytes) -> str:
        """Note a change to *path*; *previous* is ``None`` for a new file."""
        entry = UndoEntry(
            id=uuid.uuid4().hex,
            path=str(path),
            created=previous is None,
            written_sha256=_digest(written),
            timestamp=time.time(),
        )
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if previous is not None:
                self._backup(entry.id).write_bytes(previous)
            entries = self._load() + [entry]
            for old in entries[:-MAX_ENTRIES]:
                self._backup(old.id).unlink(missing_ok=True)
            self._save(entries[-MAX_ENTRIES:])
        return entry.id

    def undo(self, entry_id: str) -> Tuple[bool, str]:
        """Undo one change. Returns ``(done, message)``."""
        with self._lock:
            entries = self._load()
            entry = next((e for e in entries if e.id == entry_id), None)
            if entry is None:
                return False, "That change can't be undone any more."
            path = Path(entry.path)
            try:
                current = path.read_bytes() if path.exists() else None
            except OSError as exc:
                return False, f"Couldn't read {path}: {exc}"
            if current is None or _digest(current) != entry.written_sha256:
                return False, f"{path} has changed since, so it wasn't undone."
            try:
                if entry.created:
                    path.unlink()
                    message = f"Deleted {path}, which the agent created."
                else:
                    path.write_bytes(self._backup(entry.id).read_bytes())
                    message = f"Put back the earlier version of {path}."
            except OSError as exc:
                return False, f"Couldn't undo the change to {path}: {exc}"
            self._backup(entry.id).unlink(missing_ok=True)
            self._save([e for e in entries if e.id != entry_id])
            return True, message


_journal: Optional[UndoJournal] = None
_journal_lock = threading.Lock()


def get_journal() -> UndoJournal:
    global _journal
    with _journal_lock:
        if _journal is None:
            _journal = UndoJournal()
        return _journal


class UndoableFileWriteTool(FileWriteTool):
    """``file_write`` that records each change so the user can undo it."""

    def __init__(self, *args: Any, journal: Optional[UndoJournal] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._journal = journal

    def _target(self, raw: Any) -> Optional[Path]:
        if not raw:
            return None
        path = Path(str(raw))
        if not path.is_absolute() and self._allowed_dirs:
            path = self._allowed_dirs[0] / path
        return path

    def preview_for(self, arguments: dict) -> Optional[str]:
        """A diff of the change, shown in the approval before it's written."""
        path = self._target(arguments.get("path"))
        content = arguments.get("content")
        if path is None or not isinstance(content, str):
            return None
        old = ""
        if path.is_file():
            try:
                if path.stat().st_size > MAX_BACKUP_BYTES:
                    return None
                old = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
        new = old + content if arguments.get("mode") == "append" else content
        if new == old:
            return f"No change to {path}."
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=str(path) if path.exists() else "/dev/null",
            tofile=str(path),
        )
        return "".join(diff)

    def execute(self, **params: Any) -> ToolResult:
        path = self._target(params.get("path"))
        previous: Optional[bytes] = None
        can_undo = path is not None
        if path is not None and path.is_file():
            try:
                if path.stat().st_size <= MAX_BACKUP_BYTES:
                    previous = path.read_bytes()
                else:
                    can_undo = False
            except OSError:
                can_undo = False

        result = super().execute(**params)
        if not (result.success and can_undo and path is not None and path.is_file()):
            return result
        try:
            journal = self._journal or get_journal()
            entry_id = journal.record(path, previous, path.read_bytes())
        except OSError:
            return result
        result.metadata = {**(result.metadata or {}), "undo_id": entry_id}
        return result


__all__ = [
    "MAX_BACKUP_BYTES",
    "UndoEntry",
    "UndoJournal",
    "UndoableFileWriteTool",
    "get_journal",
]
