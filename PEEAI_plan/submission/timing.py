"""Count the spoken words of each slide in a script and estimate its time at a steady pace.

A script is a Markdown file with one "## Slide N. Title" heading per slide, an italic line
"_about S seconds_" under it, and the spoken paragraphs. Lines starting with ">" or "_", and
headings, are not spoken. Prints, per slide, the words, the estimate at 140 words per minute and
the planned seconds, then the totals.

    python3 timing.py slides/pres-note.md
    python3 timing.py poster/poster-note.md
"""

import re
import sys
from pathlib import Path

WORDS_PER_MINUTE = 140


def main(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    total_words = total_planned = 0
    print(f"{'slide':<44} {'words':>5} {'est s':>6} {'plan s':>6}")
    for part in parts:
        title, _, body = part.partition("\n")
        planned = re.search(r"^_about (\d+) seconds_", body, re.M)
        spoken = [
            line
            for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith((">", "_", "#", "---", "|"))
        ]
        words = len(re.findall(r"[A-Za-z0-9$][\w'$.,:/]*", " ".join(spoken)))
        seconds = int(planned.group(1)) if planned else 0
        total_words += words
        total_planned += seconds
        print(f"{title[:44]:<44} {words:>5} {words * 60 / WORDS_PER_MINUTE:>6.0f} {seconds:>6}")
    estimate = total_words * 60 / WORDS_PER_MINUTE
    print(f"{'total':<44} {total_words:>5} {estimate:>6.0f} {total_planned:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
