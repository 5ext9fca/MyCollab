"""The "Markdown may only reference my own files or an external URL" rule.

Markdown fields (Mission content/acceptance criteria/result and comment
bodies) may only reference:

* a file in the **author's own** library, addressed as
  ``/api/library/files/<id>/`` (the URL returned by the upload API); or
* an external ``http(s)`` URL, including protocol-relative ``//host/...``.

Everything else is rejected at write time: other users' files, arbitrary
internal paths, relative paths, and unknown schemes such as ``javascript:`` or
``data:``. Pure in-document anchors (``#section``) are allowed because they
reference no resource. Links written as raw HTML (``<img src=...>``) are checked
too, as is ``srcset``; fenced/inline code is ignored so code samples do not trip
the rule.
"""

from __future__ import annotations

import re
import uuid
from html.parser import HTMLParser
from urllib.parse import urlsplit

from common.exceptions import ValidationFailure

from .models import LibraryFile

LIBRARY_PATH_PREFIX = "/api/library/files/"
EXTERNAL_SCHEMES = {"http", "https"}

_URL_ATTRS = {"src", "href", "poster", "data", "xlink:href", "srcset"}

# ``![alt](dest)`` / ``[text](dest)``; dest is either ``<wrapped>`` or a run of
# non-space characters that may contain balanced parentheses (so an optional
# "title" after a space is dropped, but ``wiki/Foo_(bar)`` is kept whole).
_INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|(?:[^\s()\n]|\([^\s()\n]*\))+)")
# Reference definitions: ``[label]: /target``.
_DEFINITION = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(\S+)", re.MULTILINE)
_FENCED_CODE = re.compile(r"^([ \t]*)(`{3,}|~{3,}).*?^\1\2[ \t]*$", re.DOTALL | re.MULTILINE)
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)*\1", re.DOTALL)


class _AttributeCollector(HTMLParser):
    """Collect URL-bearing attribute values from raw HTML inside Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._collect(attrs)

    def handle_startendtag(self, tag, attrs):
        self._collect(attrs)

    def _collect(self, attrs) -> None:
        for name, value in attrs:
            key = name.lower()
            if key not in _URL_ATTRS or not value:
                continue
            if key == "srcset":
                # "a.png 1x, b.png 2x" -> take the URL of each candidate.
                self.values.extend(
                    candidate.strip().split(" ")[0]
                    for candidate in value.split(",")
                    if candidate.strip()
                )
            else:
                self.values.append(value)


def _strip_code(text: str) -> str:
    """Remove fenced/inline code so code samples are not treated as links."""
    without_blocks = _FENCED_CODE.sub(" ", text)
    return _INLINE_CODE.sub(" ", without_blocks)


def _clean(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value


def iter_references(markdown: str):
    """Yield every URL-looking target found in ``markdown``."""
    if not markdown:
        return
    text = _strip_code(markdown)
    for match in _INLINE_LINK.finditer(text):
        yield _clean(match.group(1))
    for match in _DEFINITION.finditer(text):
        yield _clean(match.group(1))
    collector = _AttributeCollector()
    try:
        collector.feed(text)
        collector.close()
    except Exception:  # pragma: no cover - HTMLParser is tolerant in practice
        pass
    yield from collector.values


def _is_own_library_file(path: str, owner) -> bool:
    remainder = path[len(LIBRARY_PATH_PREFIX):]
    file_id = remainder.strip("/")
    if not file_id or "/" in file_id:
        return False
    try:
        uuid.UUID(file_id)
    except (ValueError, AttributeError, TypeError):
        return False
    return LibraryFile.objects.filter(pk=file_id, owner=owner).exists()


def is_allowed_reference(target: str, owner) -> bool:
    if not target:
        return True
    if target.startswith("#"):
        # In-document anchor: references no resource.
        return True
    parsed = urlsplit(target)
    if parsed.path.startswith(LIBRARY_PATH_PREFIX):
        return _is_own_library_file(parsed.path, owner)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES and parsed.netloc:
        return True
    # Protocol-relative external URL, e.g. //cdn.example.com/a.png
    if target.startswith("//") and parsed.netloc:
        return True
    return False


def find_forbidden_references(markdown: str, owner) -> list[str]:
    """Return the de-duplicated list of references the author may not use."""
    forbidden: list[str] = []
    seen: set[str] = set()
    for target in iter_references(markdown):
        if not target or target in seen:
            continue
        seen.add(target)
        if not is_allowed_reference(target, owner):
            forbidden.append(target)
    return forbidden


def assert_markdown_references_allowed(markdown: str, owner, *, field: str) -> None:
    """Raise ``ValidationFailure`` if ``markdown`` references someone else's
    library or a non-external target."""
    forbidden = find_forbidden_references(markdown, owner)
    if forbidden:
        raise ValidationFailure(
            "Markdown 只能引用你自己的素材库文件或外部链接。",
            field_errors={field: [f"不允许的引用：{', '.join(forbidden)}"]},
        )
