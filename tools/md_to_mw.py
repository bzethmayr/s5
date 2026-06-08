"""Convert README.md to MediaWiki wikitext for the Esolang wiki."""

from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path

GITHUB_REPO = "https://github.com/bzethmayr/s5"
GITHUB_BLOB = f"{GITHUB_REPO}/tree/main"


class State(Enum):
    NORMAL = 1
    IN_CODE_BLOCK = 2
    IN_TABLE = 3


def is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r"-+\s*", c.strip()) for c in cells)


def extract_cells(line: str) -> list[str]:
    parts = line.strip().split("|")
    return [p for p in parts if p.strip() != ""]


def inline(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"'''\1'''", text)
    text = re.sub(r"\*(.+?)\*", r"''\1''", text)

    def link_repl(m: re.Match) -> str:
        label = m.group(1)
        url = m.group(2)
        if "://" not in url:
            url = f"{GITHUB_BLOB}/{url}"
        return f"[{url} {label}]"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)
    return text


def convert(md_path: Path, mw_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    state = State.NORMAL
    table_header: list[str] | None = None

    i = 0
    while i < len(lines):
        raw = lines[i]

        if raw.startswith("```"):
            if state == State.IN_CODE_BLOCK:
                out.append("</pre>")
                state = State.NORMAL
            else:
                if state == State.IN_TABLE:
                    out.append("|}")
                    state = State.NORMAL
                    table_header = None
                out.append("<pre>")
                state = State.IN_CODE_BLOCK
            i += 1
            continue

        if state == State.IN_CODE_BLOCK:
            out.append(raw)
            i += 1
            continue

        # ── NORMAL or IN_TABLE ──────────────────────────────────

        stripped = raw.strip()

        # Headings
        if stripped.startswith("##") and stripped.startswith("##"):
            # count the # signs to determine level
            if state == State.IN_TABLE:
                out.append("|}")
                state = State.NORMAL
                table_header = None
            level = len(stripped.split()[0])  # ## → 2, ### → 3, etc.
            heading = stripped[level:].strip()
            mw_level = level  # H2 → ==, H3 → ===, H4 → ====
            eq = "=" * mw_level
            out.append(f"{eq} {heading} {eq}")
            i += 1
            continue

        # H1 → skip (becomes article lead)
        if stripped.startswith("# ") or stripped.startswith("# "):
            if state == State.IN_TABLE:
                out.append("|}")
                state = State.NORMAL
                table_header = None
            i += 1
            continue

        # Table row detection
        is_table_row = (
            len(stripped) >= 3
            and stripped.startswith("|")
            and stripped.endswith("|")
            and "|" in stripped[1:-1]
        )

        if is_table_row:
            cells = extract_cells(raw)

            if is_separator_row(cells):
                i += 1
                continue

            if state != State.IN_TABLE:
                # starting a new table
                state = State.IN_TABLE
                table_header = cells
                out.append('{| class="wikitable"')
                header_line = "! " + " !! ".join(inline(c.strip()) for c in cells)
                out.append(header_line)
                i += 1
                continue

            # IN_TABLE, data row
            data_line = "| " + " || ".join(inline(c.strip()) for c in cells)
            out.append("|-")
            out.append(data_line)
            i += 1
            continue

        # Not a table row, close table if open
        if state == State.IN_TABLE:
            out.append("|}")
            state = State.NORMAL
            table_header = None

        # Empty line
        if not stripped:
            out.append("")
            i += 1
            continue

        # List item
        if stripped.startswith("- "):
            rest = stripped[2:]
            out.append(f"* {inline(rest)}")
            i += 1
            continue

        # Regular paragraph
        out.append(inline(raw))
        i += 1

    # Close any open block
    if state == State.IN_TABLE:
        out.append("|}")
    if state == State.IN_CODE_BLOCK:
        out.append("</pre>")

    mw_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    md_path = repo_root / "README.md"
    mw_path = repo_root / "README.mw"
    convert(md_path, mw_path)
    print(f"Wrote {mw_path}")


if __name__ == "__main__":
    main()
