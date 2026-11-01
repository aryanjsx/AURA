"""Reading chat attachments and folding them into the prompt."""

from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

fastapi = pytest.importorskip("fastapi")
PIL = pytest.importorskip("PIL")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from locus.server import attachments  # noqa: E402
from locus.server.attachments import (  # noqa: E402
    contents_with_attachments,
    extract_text,
    read_attachment,
    render_attachments,
)
from locus.server.models import ChatMessage, MessageAttachment  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _zip(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return out.getvalue()


def _png(width=40, height=30, mode="RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(
        mode, (width, height), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)
    ).save(out, format="PNG")
    return out.getvalue()


class TestExtractText:
    def test_docx_paragraphs(self):
        data = _zip(
            {
                "word/document.xml": (
                    f'<w:document xmlns:w="{W}"><w:body>'
                    "<w:p><w:r><w:t>Lease renewal</w:t></w:r></w:p>"
                    "<w:p><w:r><w:t>12 months, </w:t></w:r>"
                    "<w:r><w:t>same rent</w:t></w:r></w:p>"
                    "</w:body></w:document>"
                )
            }
        )
        text, label, note = extract_text("lease.docx", data)
        assert text == "Lease renewal\n12 months, same rent"
        assert label == "Word document"
        assert note is None

    def test_pptx_slides_in_order(self):
        slide = (
            '<p:sld xmlns:p="p" xmlns:a="{a}">'
            "<a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:sld>"
        )
        data = _zip(
            {
                "ppt/slides/slide10.xml": slide.format(a=A, t="Last"),
                "ppt/slides/slide2.xml": slide.format(a=A, t="Second"),
                "ppt/slides/slide1.xml": slide.format(a=A, t="First"),
            }
        )
        text, label, _ = extract_text("deck.pptx", data)
        assert label == "PowerPoint presentation"
        assert text.index("First") < text.index("Second") < text.index("Last")
        assert "Slide 3:\nLast" in text

    def test_xlsx_shared_and_inline_strings(self):
        data = _zip(
            {
                "xl/sharedStrings.xml": (
                    f'<sst xmlns="{S}"><si><t>Name</t></si><si><t>Ada</t></si></sst>'
                ),
                "xl/worksheets/sheet1.xml": (
                    f'<worksheet xmlns="{S}"><sheetData>'
                    '<row><c t="s"><v>0</v></c>'
                    '<c t="inlineStr"><is><t>Score</t></is></c></row>'
                    '<row><c t="s"><v>1</v></c><c><v>97</v></c></row>'
                    "</sheetData></worksheet>"
                ),
            }
        )
        text, label, _ = extract_text("scores.xlsx", data)
        assert label == "Excel spreadsheet"
        assert text == "Sheet 1:\nName\tScore\nAda\t97"

    def test_odt_keeps_text_after_spans(self):
        data = _zip(
            {
                "content.xml": (
                    '<o:document-content xmlns:o="o" xmlns:text="t"><o:body>'
                    "<text:p>Paint the <text:span>kitchen</text:span> green</text:p>"
                    "</o:body></o:document-content>"
                )
            }
        )
        text, label, _ = extract_text("notes.odt", data)
        assert label == "OpenDocument text"
        assert text == "Paint the kitchen green"

    def test_epub_pages(self):
        data = _zip(
            {
                "OEBPS/ch1.xhtml": (
                    "<html><body><h1>Chapter 1</h1><p>It begins.</p></body></html>"
                ),
                "OEBPS/ch2.xhtml": "<html><body><p>It ends.</p></body></html>",
            }
        )
        text, label, _ = extract_text("book.epub", data)
        assert label == "EPUB book"
        assert text.index("It begins.") < text.index("It ends.")

    def test_html_drops_scripts_and_styles(self):
        html = (
            b"<html><head><style>p{}</style></head><body><script>x()</script>"
            b"<p>Hello</p><p>World</p></body></html>"
        )
        text, label, _ = extract_text("page.html", html)
        assert label == "web page"
        assert text == "Hello\n\nWorld"

    def test_rtf(self):
        text, label, _ = extract_text(
            "memo.rtf", rb"{\rtf1\ansi{\fonttbl\f0 Arial;}\f0 Hello\par Caf\'e9}"
        )
        assert label == "RTF document"
        assert "Hello" in text and "Café" in text

    def test_notebook_cells(self):
        nb = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "source": "print(1)"},
            ]
        }
        text, label, _ = extract_text("a.ipynb", json.dumps(nb).encode())
        assert label == "Jupyter notebook"
        assert "[markdown]\n# Title" in text and "[code]\nprint(1)" in text

    @pytest.mark.parametrize(
        ("name", "data", "expected"),
        [
            ("data.csv", b"a,b\n1,2\n", "a,b\n1,2\n"),
            ("config.yaml", "name: café\n".encode("utf-8"), "name: café\n"),
            ("legacy.txt", "naïve".encode("latin-1"), "naïve"),
            ("utf16.txt", "hello".encode("utf-16"), "hello"),
            ("script", b"#!/bin/sh\necho hi\n", "#!/bin/sh\necho hi\n"),
        ],
    )
    def test_anything_that_decodes_as_text(self, name, data, expected):
        text, _, note = extract_text(name, data)
        assert text == expected
        assert note is None

    def test_binary_is_described_not_read(self):
        text, label, note = extract_text("archive.bin", b"\x00\x01\x02binary\x00")
        assert text is None
        assert label == "BIN file"
        assert "binary file" in note

    def test_legacy_office_explains_how_to_fix(self):
        text, label, note = extract_text("old.doc", b"\xd0\xcf\x11\xe0binary")
        assert text is None
        assert label == "Word 97-2003"
        assert ".docx" in note

    def test_pdf_without_text_says_so(self):
        out = io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(out, format="PDF")
        text, label, note = extract_text("scan.pdf", out.getvalue())
        assert label == "PDF"
        assert text == ""
        assert "scanned" in note


class TestReadAttachment:
    def test_image_becomes_flattened_jpeg(self):
        att = read_attachment("photo.png", _png())
        assert att.kind == "image"
        assert att.format == "PNG image"
        assert (att.width, att.height) == (40, 30)
        decoded = Image.open(io.BytesIO(base64.b64decode(att.image)))
        assert decoded.format == "JPEG" and decoded.mode == "RGB"

    def test_large_image_is_scaled_down(self):
        att = read_attachment("big.png", _png(4000, 1000, mode="RGB"))
        assert max(att.width, att.height) == attachments.IMAGE_MAX_SIDE
        assert att.width == attachments.IMAGE_MAX_SIDE

    def test_document(self):
        att = read_attachment("notes.md", b"# Notes\nBuy milk")
        assert att.kind == "document"
        assert att.text == "# Notes\nBuy milk"
        assert att.truncated is False

    def test_long_text_is_truncated(self, monkeypatch):
        monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", 10)
        att = read_attachment("long.txt", b"x" * 25)
        assert att.text == "x" * 10 and att.truncated is True

    def test_damaged_file_does_not_raise(self):
        att = read_attachment("broken.docx", b"PK\x03\x04not really a zip")
        assert att.kind == "unsupported"
        assert "damaged" in att.note


class TestEndpoint:
    @pytest.fixture
    def client(self):
        app = fastapi.FastAPI()
        app.include_router(attachments.router)
        return TestClient(app)

    def test_reads_several_files(self, client):
        resp = client.post(
            "/v1/attachments",
            files=[
                ("files", ("a.txt", b"hello", "text/plain")),
                ("files", ("b.png", _png(), "image/png")),
                ("files", ("c.bin", b"\x00\x00\x00", "application/octet-stream")),
            ],
        )
        assert resp.status_code == 200
        kinds = [a["kind"] for a in resp.json()["attachments"]]
        assert kinds == ["document", "image", "unsupported"]

    def test_rejects_too_many_files(self, client, monkeypatch):
        monkeypatch.setattr(attachments, "MAX_FILES", 1)
        resp = client.post(
            "/v1/attachments",
            files=[
                ("files", ("a.txt", b"a", "text/plain")),
                ("files", ("b.txt", b"b", "text/plain")),
            ],
        )
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, client, monkeypatch):
        monkeypatch.setattr(attachments, "MAX_FILE_BYTES", 4)
        resp = client.post(
            "/v1/attachments", files=[("files", ("a.txt", b"hello", "text/plain"))]
        )
        assert resp.status_code == 413
        assert "a.txt" in resp.json()["detail"]


class TestPromptFolding:
    def test_render_marks_cut_text(self):
        block, used = render_attachments(
            [MessageAttachment(name="a.txt", format="text", text="abcdef")], 4
        )
        assert used == 4
        assert (
            '<attached_file name="a.txt" format="text">\nabcd\n[... the rest' in block
        )

    def test_note_only_attachment(self):
        block, used = render_attachments(
            [MessageAttachment(name="x.bin", format="BIN file", note="Binary.")], 100
        )
        assert used == 0
        assert "[Binary.]" in block

    def test_newest_message_gets_the_budget_first(self):
        old = ChatMessage(
            role="user",
            content="first",
            attachments=[MessageAttachment(name="old.txt", text="o" * 30)],
        )
        new = ChatMessage(
            role="user",
            content="second",
            attachments=[MessageAttachment(name="new.txt", text="n" * 30)],
        )
        contents = contents_with_attachments(
            [old, ChatMessage(role="assistant", content="ok"), new], budget=40
        )
        assert "n" * 30 in contents[2]
        assert "o" * 10 in contents[0] and "o" * 11 not in contents[0]
        assert contents[1] == "ok"
        assert contents[2].endswith("\n\nsecond")

    def test_attachment_only_message(self):
        msg = ChatMessage(
            role="user",
            content="",
            attachments=[MessageAttachment(name="a.txt", text="hi")],
        )
        (content,) = contents_with_attachments([msg])
        assert content.startswith("The user attached these files:")
