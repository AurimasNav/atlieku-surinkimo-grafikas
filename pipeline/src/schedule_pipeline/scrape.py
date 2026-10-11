"""Finds the schedule files linked from the nemenkom.lt schedule page."""

from __future__ import annotations

import urllib.request
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

from .model import Kind, SourceFile

PAGE_URL = "https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/"
USER_AGENT = (
    "atlieku-surinkimo-grafikas/0.1 (+https://github.com/AurimasNav/atlieku-surinkimo-grafikas)"
)
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
    """Uses the upload folder name to tell the schedules apart, since file names change."""
    folder = unquote(PurePosixPath(urlparse(url).path).parent.name).casefold()
    # Check glass first: its folder is "Stiklo pakuotės", which also contains "pakuot".
    if "stikl" in folder:
        return "glass"
    if "pakuo" in folder:
        return "packaging"
    if "buitin" in folder:
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
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()
