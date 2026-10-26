"""Count the visible words on each page of a slide PDF, the owner's limit being about 25 to 35
words per main slide, title included.

The footer (the text logo and the page number) is not counted, and neither is an icon, which
pdftotext prints as one stray letter. Words are runs of letters, digits
and the signs $ % . , ' joined to them, so "5.25", "$35" and "100+" are one word each.

    python3 tools/wc.py slides/slides.pdf          every page
    python3 tools/wc.py slides/slides.pdf 13       the first 13 pages
"""

import re
import subprocess
import sys


def page_words(pdf: str, page: int) -> list[str]:
    text = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), pdf, "-"], capture_output=True, text=True, check=True
    ).stdout
    text = re.sub(r"\b([A-Z]) ([A-Z]{2,})", r"\1\2", text)  # small capitals split by pdftotext
    text = re.sub(r"^\s*\d+\s*/\s*\d+\s*$", "", text, flags=re.M)  # page number "3 / 13"
    words = re.findall(r"[A-Za-z0-9$][A-Za-z0-9’'.\-$%/,+]*", text)
    # An icon from the fontawesome font comes out as one stray letter, which is not a word.
    return [w for w in words if len(w) > 1 or w in "aAIB" or w.isdigit()]


def main() -> int:
    pdf = sys.argv[1]
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
    if len(sys.argv) > 2:
        pages = min(pages, int(sys.argv[2]))
    for page in range(1, pages + 1):
        words = page_words(pdf, page)
        print(f"{page:>3} {len(words):>4}  {' '.join(words)[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
