"""Copy the spoken script into the speaker notes of the deck, so the two never drift apart.

Each "## Slide N" part of slides/pres-note.md fills the N-th \\note{...} block of slides/slides.tex,
in order: the stage direction in bold, then the spoken paragraphs. The backups after the
thirteenth slide keep empty notes. check_writing.py fails when a note and the script differ.

    python3 tools/sync_notes.py
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCRIPT = HERE / "slides" / "pres-note.md"
SLIDES = HERE / "slides" / "slides.tex"


def latex(text: str) -> str:
    return text.replace("\\", "").replace("$", "\\$").replace("%", "\\%").replace("&", "\\&")


def notes_from_script() -> list[str]:
    parts = re.split(r"^## ", SCRIPT.read_text(encoding="utf-8"), flags=re.M)[1:]
    notes = []
    for part in parts:
        _, _, body = part.partition("\n")
        stage = re.search(r"^_(.+)_\s*$", body, re.M)
        spoken = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith(("_", ">", "#", "|"))]
        text = f"\\textbf{{({latex(stage.group(1))})}} " if stage else ""
        notes.append(text + latex(" ".join(spoken)))
    return notes


def main() -> int:
    source = SLIDES.read_text(encoding="utf-8")
    notes = notes_from_script()
    out, pos, index = [], 0, 0
    for match in re.finditer(r"\\note\{", source):
        if match.start() < pos:
            continue
        depth, i = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(source[i], 0)
            i += 1
        body = notes[index] if index < len(notes) else ""
        out.append(source[pos : match.end()])
        out.append("\n    " + body + "\n  " if body else "")
        out.append("}")
        pos, index = i, index + 1
    out.append(source[pos:])
    SLIDES.write_text("".join(out), encoding="utf-8")
    print(f"{min(index, len(notes))} notes written from {len(notes)} script parts, {index} note blocks in the deck")
    return 0 if index >= len(notes) else 1


if __name__ == "__main__":
    sys.exit(main())
