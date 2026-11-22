"""No tokens in the files saved from publishers' sites: the test fixtures and pipeline/data,
whose site copies the daily refresh commits unattended (snapshot.save_site_copy redacts Google
API keys in the pages it saves)."""

import re
from pathlib import Path

import pytest

from schedule_pipeline import snapshot

PIPELINE = Path(__file__).resolve().parents[1]
FOLDERS = (PIPELINE / "tests" / "fixtures", PIPELINE / "data")
# Formats of keys and tokens that secret scanners flag.
TOKENS = re.compile(
    rb"|".join(
        [
            snapshot.GOOGLE_API_KEY.pattern,  # Google API key
            rb"gh[pousr]_[0-9A-Za-z]{36}",  # GitHub tokens
            rb"github_pat_[0-9A-Za-z_]{22,}",  # GitHub fine-grained token
            rb"AKIA[0-9A-Z]{16}",  # AWS access key id
            rb"xox[abprs]-[0-9A-Za-z-]{10,}",  # Slack token
            rb"sk_live_[0-9A-Za-z]{24,}",  # Stripe secret key
            rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        ]
    )
)


def found(folder: Path) -> list[str]:
    """The files of `folder` with a token in them, and the token's first characters."""
    return [
        f"{path.relative_to(folder).as_posix()}: {match.group()[:8].decode(errors='replace')}..."
        for path in sorted(folder.rglob("*"))
        if path.is_file()
        for match in TOKENS.finditer(path.read_bytes())
    ]


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda f: f.name)
def test_no_tokens_in_saved_files(folder):
    assert found(folder) == []


def test_the_scan_finds_them(tmp_path):
    # Made up here, so this file has no token in it either.
    (tmp_path / "page.html").write_bytes(b'var key = "AIza' + b"B" * 35 + b'";')
    (tmp_path / "x.txt").write_bytes(b"token " + b"ghp" + b"_" + b"a" * 36)
    assert found(tmp_path) == ["page.html: AIzaBBBB...", "x.txt: ghp_aaaa..."]
