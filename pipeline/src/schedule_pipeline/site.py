"""Renders Markdown documents (e.g. PRIVACY.md) into standalone pages for GitHub Pages.

The Markdown file in the repo stays the single source of truth; the HTML is generated in CI.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import markdown

TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg: #f4f6f3; --fg: #15201a; --muted: #5e6b63; --line: #dce2da; --accent: #1f7a4d; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #0e1311; --fg: #ecf2ee; --muted: #9aa8a0; --line: #2c3832; --accent: #4cc38a; }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
    font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; }}
  h1 {{ line-height: 1.2; }}
  h2 {{ margin-top: 2em; }}
  a {{ color: var(--accent); }}
  hr {{ border: 0; border-top: 1px solid var(--line); margin: 3em 0; }}
  table {{ border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }}
  th, td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: left; }}
  code {{ font-size: 0.9em; }}
</style>
</head>
<body><main>
{body}
</main></body>
</html>
"""


def render(source: Path, title: str, lang: str = "en") -> str:
    body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["tables"])
    return TEMPLATE.format(lang=lang, title=html.escape(title), body=body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.source, args.title), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
