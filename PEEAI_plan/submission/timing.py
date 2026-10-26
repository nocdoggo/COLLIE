"""Count the spoken words of each slide in a script and estimate its time at a steady pace.

A script is a Markdown file with one "## Slide N. Title" heading per slide, an italic stage
direction "_about S seconds, ends M.SS_" under it, and the spoken paragraphs. Lines starting with
">", "_" or "|", and headings, are not spoken and are not counted. Prints, per slide, the words,
the estimate at 140 words per minute and the planned seconds, then the totals.

With --update, the stage directions are rewritten to the estimates (seconds, and the clock at the
end of each slide), so the plan always matches the words. Run tools/sync_notes.py after it.

    python3 timing.py slides/pres-note.md
    python3 timing.py --update slides/pres-note.md
    python3 timing.py poster/poster-note.md
"""

import re
import sys
from pathlib import Path

WORDS_PER_MINUTE = 140


def spoken_words(body: str) -> int:
    spoken = [
        line
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith((">", "_", "#", "---", "|"))
    ]
    return len(re.findall(r"[A-Za-z0-9$][\w'$.,:/]*", " ".join(spoken)))


def main(args: list[str]) -> int:
    update = "--update" in args
    paths = [a for a in args if a != "--update"]
    path = Path(paths[0]) if paths else Path(__file__).resolve().parent / "slides" / "pres-note.md"
    text = path.read_text(encoding="utf-8")
    head, *parts = re.split(r"^## ", text, flags=re.M)
    total_words = total_planned = 0
    clock = 0
    rewritten = []
    print(f"{'slide':<44} {'words':>5} {'est s':>6} {'plan s':>6}")
    for part in parts:
        title, _, body = part.partition("\n")
        planned = re.search(r"^_about (\d+) seconds", body, re.M)
        words = spoken_words(body)
        estimate = round(words * 60 / WORDS_PER_MINUTE)
        seconds = int(planned.group(1)) if planned else 0
        if update:
            clock += estimate
            stage = f"_about {estimate} seconds, ends {clock // 60}.{clock % 60:02d}_"
            body = re.sub(r"^_about \d+ seconds[^\n]*_$", stage, body, count=1, flags=re.M)
            seconds = estimate
        rewritten.append(f"{title}\n{body}")
        total_words += words
        total_planned += seconds
        print(f"{title[:44]:<44} {words:>5} {estimate:>6} {seconds:>6}")
    print(f"{'total':<44} {total_words:>5} {round(total_words * 60 / WORDS_PER_MINUTE):>6} {total_planned:>6}")
    if update:
        path.write_text(head + "".join("## " + p for p in rewritten), encoding="utf-8")
        print(f"stage directions updated in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
