"""The user's name, so the assistant knows what to call them.

``GET/PUT /v1/profile`` read and write a small block in the persona's
``USER.md``, which :class:`~locus.prompt.builder.SystemPromptBuilder` adds to
every system prompt under "User Profile". Anything else the user keeps in that
file is left alone. The block is plain text, so the CLI and agents see the same
name, and editing it by hand works too.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/profile", tags=["profile"])

START = "<!-- locus:profile (set in the Locus app) -->"
END = "<!-- /locus:profile -->"
_BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
_FIELDS = (
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("nickname", "Nickname"),
)
MAX_LEN = 50


class Profile(BaseModel):
    first_name: str = Field("", max_length=MAX_LEN)
    last_name: str = Field("", max_length=MAX_LEN)
    nickname: str = Field("", max_length=MAX_LEN)


def _clean(value: str) -> str:
    """One line of plain text: no line breaks or comment markers."""
    value = value.replace("<!--", "").replace("-->", "")
    return re.sub(r"\s+", " ", value).strip()


def render_block(profile: Profile) -> str:
    """The USER.md block for ``profile``, or "" when it's empty."""
    values = {key: _clean(getattr(profile, key)) for key, _ in _FIELDS}
    if not any(values.values()):
        return ""
    lines = [START]
    lines += [f"{label}: {values[key]}" for key, label in _FIELDS if values[key]]
    call_them = values["nickname"] or values["first_name"]
    if call_them:
        lines.append(
            f'Address the user as "{call_them}" when you greet them or speak to them '
            "directly, unless they ask you to use a different name."
        )
    lines.append(END)
    return "\n".join(lines) + "\n"


def parse_block(text: str) -> Profile:
    """The profile stored in USER.md ``text`` (empty if there is none)."""
    match = _BLOCK_RE.search(text)
    if not match:
        return Profile()
    found = {}
    for key, label in _FIELDS:
        line = re.search(rf"^{label}: (.*)$", match.group(0), re.M)
        if line:
            found[key] = line.group(1).strip()
    return Profile(**found)


def write_profile(path: Path, profile: Profile) -> None:
    """Replace (or add, or remove) the profile block in ``path``."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rest = _BLOCK_RE.sub("", existing).lstrip("\n")
    block = render_block(profile)
    if not block and not rest:
        if path.exists():
            path.unlink()
        return
    content = block + ("\n" + rest if block and rest else rest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def profile_path(request: Request) -> Path:
    """The USER.md the system prompt reads, honouring a named persona."""
    from locus.core.config import load_config
    from locus.prompt.builder import SystemPromptBuilder

    config = getattr(request.app.state, "config", None) or load_config()
    resolved = SystemPromptBuilder._resolve_persona(config.memory_files)
    if not resolved.user_path:
        # persona_name = "none" turns persona files off entirely.
        raise HTTPException(
            status_code=409,
            detail='Persona files are turned off (persona_name = "none"), '
            "so Locus can't use your name.",
        )
    return Path(resolved.user_path).expanduser()


@router.get("", response_model=Profile)
def get_profile(request: Request) -> Profile:
    path = profile_path(request)
    return parse_block(path.read_text(encoding="utf-8")) if path.exists() else Profile()


@router.put("", response_model=Profile)
def put_profile(profile: Profile, request: Request) -> Profile:
    cleaned = Profile(**{key: _clean(getattr(profile, key)) for key, _ in _FIELDS})
    write_profile(profile_path(request), cleaned)
    return cleaned


__all__ = ["Profile", "parse_block", "render_block", "router", "write_profile"]
