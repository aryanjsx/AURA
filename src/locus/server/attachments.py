"""Files attached to chat messages.

``POST /v1/attachments`` reads uploaded files and returns their content for
the client to send with a chat message: extracted text for documents, a
resized JPEG for images. Nothing is stored on the server. The chat route then
folds that content into the prompt with :func:`render_attachments`, within a
size budget so large documents can't push the question out of a local model's
context window.

Text extraction uses only the standard library plus ``pdfplumber`` (PDF) and
Pillow (images), so every format below works in the desktop runtime:

* PDF; Office Open XML (``.docx``, ``.pptx``, ``.xlsx``); OpenDocument
  (``.odt``, ``.ods``, ``.odp``); EPUB; HTML; RTF; Jupyter notebooks
* Anything that decodes as text: plain text, Markdown, CSV, JSON, XML, YAML,
  logs, source code, and so on
* Images Pillow can open (PNG, JPEG, GIF, WebP, BMP, TIFF, ICO, ...)

Other binary files are accepted and described by name, type and size so the
model can at least tell the user what it received.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import zipfile
from html.parser import HTMLParser
from typing import Any, Iterable, List, Optional, Sequence
from xml.etree import ElementTree

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from locus.server.models import MessageAttachment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/attachments", tags=["attachments"])

#: Largest file accepted, per file.
MAX_FILE_BYTES = 25 * 1024 * 1024
#: Most files accepted in one upload.
MAX_FILES = 10
#: Extracted text kept per file. The prompt budget below trims further.
MAX_TEXT_CHARS = 200_000
#: Attachment text sent to the model per request, across all messages. About
#: 10k tokens, which leaves room for the conversation and the answer in the
#: default 16k-token Ollama context.
PROMPT_BUDGET_CHARS = 40_000
#: Images are scaled down so their longest side is at most this many pixels.
IMAGE_MAX_SIDE = 1568

_ZIP_MAGIC = b"PK\x03\x04"


class Attachment(BaseModel):
    """What the client gets back for one uploaded file."""

    name: str
    kind: str  # "document" | "image" | "unsupported"
    format: str
    size: int
    text: Optional[str] = None
    truncated: bool = False
    image: Optional[str] = None  # base64 JPEG
    width: Optional[int] = None
    height: Optional[int] = None
    note: Optional[str] = None


class AttachmentsResponse(BaseModel):
    attachments: List[Attachment]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


class _HTMLText(HTMLParser):
    """Collect visible text, one block element per line."""

    _BLOCKS = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "pre",
        "blockquote",
        "td",
        "th",
    }
    _SKIP = {"script", "style", "noscript", "template", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCKS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCKS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return _tidy("".join(self._parts))


def _tidy(text: str) -> str:
    """Collapse runs of spaces and blank lines."""
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    parser.close()
    return parser.text()


def _xml_text(xml: bytes, paragraph_tags: Iterable[str]) -> str:
    """One line per paragraph element, with all the text inside it."""
    paragraph_tags = set(paragraph_tags)
    root = ElementTree.fromstring(xml)
    lines = [
        "".join(elem.itertext())
        for elem in root.iter()
        if elem.tag.rsplit("}", 1)[-1] in paragraph_tags
    ]
    return _tidy("\n".join(lines))


def _natural_key(name: str) -> List[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _docx_text(zf: zipfile.ZipFile) -> str:
    parts = [
        n
        for n in zf.namelist()
        if re.fullmatch(r"word/(document|footnotes|endnotes)\.xml", n)
    ]
    return "\n\n".join(_xml_text(zf.read(n), {"p"}) for n in sorted(parts))


def _pptx_text(zf: zipfile.ZipFile) -> str:
    slides = sorted(
        (n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=_natural_key,
    )
    return "\n\n".join(
        f"Slide {i}:\n{_xml_text(zf.read(n), {'p'})}" for i, n in enumerate(slides, 1)
    )


def _xlsx_text(zf: zipfile.ZipFile) -> str:
    """Render each sheet as tab-separated rows."""
    shared: List[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.iter():
            if si.tag.rsplit("}", 1)[-1] == "si":
                shared.append(
                    "".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))
                )
    sheets = sorted(
        (n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
        key=_natural_key,
    )
    out: List[str] = []
    for i, name in enumerate(sheets, 1):
        rows: List[str] = []
        root = ElementTree.fromstring(zf.read(name))
        for row in root.iter():
            if row.tag.rsplit("}", 1)[-1] != "row":
                continue
            cells: List[str] = []
            for cell in row:
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                value = next((v.text for v in cell if v.tag.endswith("}v")), None)
                inline = "".join(
                    t.text or "" for t in cell.iter() if t.tag.endswith("}t")
                )
                if cell.get("t") == "s" and value is not None and value.isdigit():
                    idx = int(value)
                    cells.append(shared[idx] if idx < len(shared) else "")
                else:
                    cells.append(inline or value or "")
            if any(cells):
                rows.append("\t".join(cells))
        out.append(f"Sheet {i}:\n" + "\n".join(rows))
    return "\n\n".join(out)


def _odf_text(zf: zipfile.ZipFile) -> str:
    return _xml_text(zf.read("content.xml"), {"p", "h"})


def _epub_text(zf: zipfile.ZipFile) -> str:
    pages = sorted(
        (n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))),
        key=_natural_key,
    )
    return "\n\n".join(
        html_to_text(zf.read(n).decode("utf-8", "replace")) for n in pages
    )


def _notebook_text(data: bytes) -> str:
    nb = json.loads(data.decode("utf-8"))
    out: List[str] = []
    for cell in nb.get("cells", []):
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else source
        out.append(f"[{cell.get('cell_type', 'cell')}]\n{source}")
    return "\n\n".join(out)


def _rtf_text(rtf: str) -> str:
    """Strip RTF control words; good enough for prose documents."""
    text = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda m: bytes.fromhex(m.group(1)).decode("cp1252"),
        rtf,
    )
    text = re.sub(r"\\par[d]?\b|\\line\b", "\n", text)
    text = re.sub(r"\{\\\*[^{}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    return _tidy(text.replace("{", "").replace("}", ""))


def _pdf_text(data: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return _tidy("\n\n".join(page.extract_text() or "" for page in pdf.pages))


def _decode_text(data: bytes) -> Optional[str]:
    """Decode ``data`` if it looks like text; ``None`` for binary data."""
    if not data:
        return ""
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if data.startswith(bom):
            return data.decode(encoding, "replace")
    sample = data[:8192]
    if b"\x00" in sample:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    text = data.decode("latin-1")
    printable = sum(ch.isprintable() or ch in "\n\r\t" for ch in text[:8192])
    return text if printable / max(len(text[:8192]), 1) > 0.95 else None


_ZIP_FORMATS = {
    ".docx": ("Word document", _docx_text),
    ".docm": ("Word document", _docx_text),
    ".pptx": ("PowerPoint presentation", _pptx_text),
    ".pptm": ("PowerPoint presentation", _pptx_text),
    ".xlsx": ("Excel spreadsheet", _xlsx_text),
    ".xlsm": ("Excel spreadsheet", _xlsx_text),
    ".odt": ("OpenDocument text", _odf_text),
    ".ods": ("OpenDocument spreadsheet", _odf_text),
    ".odp": ("OpenDocument presentation", _odf_text),
    ".epub": ("EPUB book", _epub_text),
}

_LEGACY_OFFICE = {
    ".doc": "Word 97-2003",
    ".xls": "Excel 97-2003",
    ".ppt": "PowerPoint 97-2003",
}


def _extension(name: str) -> str:
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def extract_text(name: str, data: bytes) -> tuple[Optional[str], str, Optional[str]]:
    """Return ``(text, format_label, note)`` for a non-image file.

    ``text`` is ``None`` when the file's content can't be read; ``note`` then
    says why, in words the model can relay to the user.
    """
    ext = _extension(name)
    if data.startswith(b"%PDF") or ext == ".pdf":
        text = _pdf_text(data)
        note = (
            None
            if text
            else "The PDF has no selectable text (it may be a scanned image)."
        )
        return text, "PDF", note
    if data.startswith(_ZIP_MAGIC) and ext in _ZIP_FORMATS:
        label, reader = _ZIP_FORMATS[ext]
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return reader(zf), label, None
    if ext in _LEGACY_OFFICE:
        return (
            None,
            _LEGACY_OFFICE[ext],
            f"Locus can't read the old {_LEGACY_OFFICE[ext]} format. "
            "Save it as a newer file "
            f"(for example .{ext[1:]}x) and attach it again.",
        )
    if ext == ".ipynb":
        return _notebook_text(data), "Jupyter notebook", None

    text = _decode_text(data)
    if text is None:
        label = f"{ext[1:].upper()} file" if ext else "binary file"
        return (
            None,
            label,
            "This is a binary file, so its content can't be read as text.",
        )
    if ext in {".html", ".htm", ".xhtml"} or text.lstrip()[:15].lower().startswith(
        ("<!doctype html", "<html")
    ):
        return html_to_text(text), "web page", None
    if ext == ".rtf" or text.startswith("{\\rtf"):
        return _rtf_text(text), "RTF document", None
    label = f"{ext[1:].upper()} file" if ext else "text"
    return text, label, None


def prepare_image(data: bytes) -> Optional[tuple[str, int, int, str]]:
    """Return ``(base64_jpeg, width, height, format)``, or ``None`` if not an image."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or "image"
            img.seek(0)  # first frame of animations
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.getchannel("A"))
                img = background
            else:
                img = img.convert("RGB")
            img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=85)
            return (
                base64.b64encode(out.getvalue()).decode("ascii"),
                img.width,
                img.height,
                fmt,
            )
    except Exception:
        return None


def read_attachment(name: str, data: bytes) -> Attachment:
    """Turn one uploaded file into an :class:`Attachment`."""
    image = prepare_image(data)
    if image is not None:
        b64, width, height, fmt = image
        return Attachment(
            name=name,
            kind="image",
            format=f"{fmt} image",
            size=len(data),
            image=b64,
            width=width,
            height=height,
        )
    try:
        text, label, note = extract_text(name, data)
    except Exception as exc:  # a damaged file shouldn't fail the whole upload
        logger.info("Could not read attachment %s: %s", name, exc)
        return Attachment(
            name=name,
            kind="unsupported",
            format=_extension(name)[1:].upper() or "file",
            size=len(data),
            note=(
                f"The file couldn't be read ({type(exc).__name__}). It may be damaged."
            ),
        )
    if text is None:
        return Attachment(
            name=name, kind="unsupported", format=label, size=len(data), note=note
        )
    truncated = len(text) > MAX_TEXT_CHARS
    return Attachment(
        name=name,
        kind="document",
        format=label,
        size=len(data),
        text=text[:MAX_TEXT_CHARS],
        truncated=truncated,
        note=note,
    )


@router.post("", response_model=AttachmentsResponse)
async def read_attachments(files: List[UploadFile] = File(...)) -> AttachmentsResponse:
    """Read uploaded files for a chat message. Nothing is stored."""
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400, detail=f"Attach at most {MAX_FILES} files at a time."
        )
    out: List[Attachment] = []
    for upload in files:
        name = upload.filename or "file"
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{name} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.",
            )
        out.append(read_attachment(name, data))
    return AttachmentsResponse(attachments=out)


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def render_attachments(
    attachments: Sequence[MessageAttachment], budget: int
) -> tuple[str, int]:
    """Render documents as a prompt block. Returns ``(block, chars_used)``."""
    if not attachments:
        return "", 0
    parts: List[str] = []
    used = 0
    for att in attachments:
        header = f'<attached_file name="{att.name}" format="{att.format}">'
        if att.note and not att.text:
            parts.append(f"{header}\n[{att.note}]\n</attached_file>")
            continue
        room = max(budget - used, 0)
        text = att.text[:room]
        used += len(text)
        shortened = att.truncated or len(text) < len(att.text)
        body = text
        if shortened:
            body += (
                "\n[... the rest of this file was cut to fit the model's context ...]"
            )
        if att.note:
            body = f"[{att.note}]\n{body}"
        parts.append(f"{header}\n{body}\n</attached_file>")
    return "The user attached these files:\n\n" + "\n\n".join(parts), used


def contents_with_attachments(
    messages: Sequence[Any], budget: int = PROMPT_BUDGET_CHARS
) -> List[str]:
    """Each message's content with its documents folded in ahead of it.

    Newer messages get first claim on ``budget``, so the latest files are sent
    in full when the conversation already carries older ones. The messages
    themselves aren't changed.
    """
    contents = [getattr(m, "content", "") or "" for m in messages]
    remaining = budget
    for i in range(len(messages) - 1, -1, -1):
        attachments = getattr(messages[i], "attachments", None)
        if not attachments:
            continue
        block, used = render_attachments(attachments, remaining)
        remaining -= used
        contents[i] = f"{block}\n\n{contents[i]}" if contents[i] else block
    return contents


__all__ = [
    "Attachment",
    "AttachmentsResponse",
    "MessageAttachment",
    "contents_with_attachments",
    "extract_text",
    "html_to_text",
    "prepare_image",
    "read_attachment",
    "render_attachments",
    "router",
]
