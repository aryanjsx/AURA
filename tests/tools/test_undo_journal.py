"""Undo for Agent mode file changes."""

from __future__ import annotations

import pytest

from locus.tools import undo_journal
from locus.tools.undo_journal import MAX_ENTRIES, UndoableFileWriteTool, UndoJournal


@pytest.fixture
def journal(tmp_path):
    return UndoJournal(tmp_path / "undo")


@pytest.fixture
def home(tmp_path):
    folder = tmp_path / "home"
    folder.mkdir()
    return folder


def _tool(home, journal):
    return UndoableFileWriteTool(allowed_dirs=[str(home)], journal=journal)


def test_undo_puts_back_the_old_version(home, journal):
    target = home / "notes.txt"
    target.write_text("original")

    result = _tool(home, journal).execute(path=str(target), content="rewritten")

    assert result.success
    assert target.read_text() == "rewritten"
    done, message = journal.undo(result.metadata["undo_id"])
    assert done, message
    assert target.read_text() == "original"
    # Each change undoes once.
    assert journal.undo(result.metadata["undo_id"])[0] is False


def test_undo_deletes_a_file_the_agent_created(home, journal):
    result = _tool(home, journal).execute(path="new.txt", content="hello")

    created = home / "new.txt"
    assert created.read_text() == "hello"
    done, message = journal.undo(result.metadata["undo_id"])
    assert done
    assert "created" in message
    assert not created.exists()


def test_undo_never_loses_later_edits(home, journal):
    target = home / "notes.txt"
    target.write_text("original")
    result = _tool(home, journal).execute(path=str(target), content="agent")
    target.write_text("the user edited it after")

    done, message = journal.undo(result.metadata["undo_id"])

    assert not done
    assert "changed since" in message
    assert target.read_text() == "the user edited it after"


def test_undo_after_append(home, journal):
    target = home / "log.txt"
    target.write_text("one\n")
    result = _tool(home, journal).execute(
        path=str(target), content="two\n", mode="append"
    )

    assert target.read_text() == "one\ntwo\n"
    assert journal.undo(result.metadata["undo_id"])[0]
    assert target.read_text() == "one\n"


def test_failed_writes_record_nothing(home, journal, tmp_path):
    outside = tmp_path / "outside.txt"
    result = _tool(home, journal).execute(path=str(outside), content="x")

    assert not result.success
    assert "undo_id" not in (result.metadata or {})
    assert journal._load() == []


def test_big_files_are_not_backed_up(home, journal, monkeypatch):
    monkeypatch.setattr(undo_journal, "MAX_BACKUP_BYTES", 4)
    target = home / "big.txt"
    target.write_text("more than four bytes")

    result = _tool(home, journal).execute(path=str(target), content="small")

    assert result.success
    assert "undo_id" not in result.metadata


def test_old_entries_are_dropped(home, journal):
    target = home / "a.txt"
    target.write_text("0")
    ids = []
    for i in range(MAX_ENTRIES + 3):
        ids.append(
            _tool(home, journal)
            .execute(path=str(target), content=str(i + 1))
            .metadata["undo_id"]
        )

    kept = [e.id for e in journal._load()]
    assert len(kept) == MAX_ENTRIES
    assert ids[0] not in kept
    assert not (journal.root / f"{ids[0]}.bak").exists()


def test_undo_endpoint(home, monkeypatch, tmp_path):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient

    from locus.core.config import JarvisConfig
    from locus.server.app import create_app

    journal = UndoJournal(tmp_path / "undo")
    monkeypatch.setattr(undo_journal, "_journal", journal)
    target = home / "notes.txt"
    target.write_text("original")
    undo_id = (
        _tool(home, journal)
        .execute(path=str(target), content="new")
        .metadata["undo_id"]
    )

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    client = TestClient(create_app(object(), "m", config=cfg))

    resp = client.post(f"/v1/chat/undo/{undo_id}")
    assert resp.status_code == 200
    assert target.read_text() == "original"
    again = client.post(f"/v1/chat/undo/{undo_id}")
    assert again.status_code == 409
    assert "can't be undone" in again.json()["detail"]
