"""Finds the schedule files linked from the nemenkom.lt schedule page."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

from . import http
from .model import Kind, SourceFile

PAGE_URL = "https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/"
SUPPORTED_EXTENSIONS = {".xlsx", ".pdf"}


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def classify(url: str) -> Kind | None:
    """Tells the schedules apart by their upload folder, since file names change. Falls back
    to the file name for files uploaded to an unrelated folder (it has happened)."""
    path = PurePosixPath(unquote(urlparse(url).path))
    return _kind_of(path.parent.name) or _kind_of(path.name)


def _kind_of(name: str) -> Kind | None:
    name = name.casefold()
    # Check glass first: "Stiklo pakuotės" also contains "pakuo".
    if "stikl" in name:
        return "glass"
    if "pakuo" in name:
        return "packaging"
    if "buitin" in name:
        return "household"
    return None


def find_schedule_files(html: str, base_url: str = PAGE_URL) -> list[SourceFile]:
    collector = _LinkCollector()
    collector.feed(html)
    files: list[SourceFile] = []
    seen: set[str] = set()
    for href in collector.links:
        url = urljoin(base_url, href)
        path = PurePosixPath(urlparse(url).path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS or "/uploads/" not in path.as_posix():
            continue
        kind = classify(url)
        if kind is None or url in seen:
            continue
        seen.add(url)
        files.append(SourceFile(kind=kind, url=url, file_name=unquote(path.name)))
    return files


def fetch(url: str, timeout: float = 60) -> bytes:
    return http.get(url, timeout=timeout)
