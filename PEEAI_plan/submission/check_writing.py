"""The owner's writing-rule check for the three submission items.

Two rule sets.

1. Punctuation, on everything this check has always read. Every PDF (pdftotext), the Word
   document's text (document.xml, its headers and footers, core properties), the spoken scripts,
   this directory's README, DRAFT.md and STORY_PLAN.md, and the Wave 3 handoff packet's Markdown
   must contain no em dash, no en dash (nor any other typographic dash or minus sign), no "--" and
   no semicolon. In the Word document, text in the two monospace code styles (command lines and
   identifiers) is not prose and is skipped. In the Markdown files, code blocks and inline code are
   skipped for the same reason.

2. The deliverables only, stricter. The rendered slides.pdf and poster.pdf (and their PDF
   metadata), the speaker notes in slides.tex, pres-note.md, poster-note.md and the Word
   document's visible text. They must contain
   (a) no colon (clock times read "5.25 pm" or "17.25"),
   (b) no "https://" or "http://" (show addresses without it, a link target may keep it),
   (c) none of the owner's banned AI-sounding words and none of the mechanical words that say
       nothing to the audience (whole words, any case, the usual inflections included),
   (d) on the deck, the poster and the scripts, no code identifiers and no case codes,
   (e) in the Word document, no unfilled "{name}" placeholder,
   (f) no author other than Noctis Zhang,
   and (g) the speaker notes in slides.tex must say exactly what pres-note.md says.
   In the Word document, whole paragraphs in the monospace "Code" style are command lines and are
   exempt. Inline code runs are checked for (a), (b) and (e) but not for words, because a file
   path is not prose.

The working notes AUDIT_BEFORE.md, REVISION_PLAN.md, RESEARCH_BRIEF.md and COMPARISON_BRIEF.md
quote the old wording on purpose and are never read.

Prints each hit with its file, line and rule, and exits 1 when there is any.

    python3 check_writing.py
"""

import html
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDFS = ["slides/slides.pdf", "poster/poster.pdf"]
DOCX = ["documentation/Plan_B_Project_Documentation.docx"]
SCRIPTS = ["slides/pres-note.md", "poster/poster-note.md"]
SLIDES_TEX = "slides/slides.tex"
READMES = ["README.md", "DRAFT.md", "STORY_PLAN.md"] + sorted(
    f"../handoffs/wave_3/{path.name}" for path in (HERE / "../handoffs/wave_3").glob("*.md")
)
FORBIDDEN = re.compile(r"[\u2012\u2013\u2014\u2015\u2212]|--|;")

# The owner's list of words that sound machine-written, and the mechanical words that name a part
# of the code instead of saying what happens. Each entry is a regular expression for one word and
# its usual inflections, matched as a whole word in any case.
AI_WORDS = [
    r"seamless(ly)?", r"leverag(e|es|ed|ing)", r"robust(ly|ness)?", r"delv(e|es|ed|ing)",
    r"harness(es|ed|ing)?", r"empower(s|ed|ing|ment)?", r"cutting[- ]edge", r"state[- ]of[- ]the[- ]art",
    r"unlock(s|ed|ing)?", r"elevat(e|es|ed|ing)", r"streamlin(e|es|ed|ing)", r"game[- ]changer(s)?",
    r"revolutioni[sz](e|es|ed|ing)", r"transform(s|ed|ing|ative)?", r"synerg(y|ies)", r"holistic(ally)?",
    r"tapestr(y|ies)", r"landscape(s)?", r"navigat(e|es|ed|ing)", r"realm(s)?", r"paradigm(s)?",
    r"foster(s|ed|ing)?", r"unleash(es|ed|ing)?", r"supercharg(e|es|ed|ing)", r"next[- ]level",
    r"pivotal", r"intricate(ly)?", r"meticulous(ly)?", r"embark(s|ed|ing)?", r"journey(s)?",
    r"ecosystem(s)?", r"innovative", r"powerful(ly)?", r"effortless(ly)?", r"smart(er|est)?",
    r"world[- ]class", r"comprehensive(ly)?",
]
MECHANICAL_WORDS = [
    r"gat(e|es|ed|ing)", r"gatekeep\w*", r"arm(s|ed|ing)?", r"pipeline(s)?", r"orchestrat\w*", r"checkpoint(s)?",
    r"guardrail(s)?",
    r"fallback(s)?", r"fall[- ]back", r"modul(e|es|ar)", r"polic(y|ies)", r"executor(s)?", r"grant(s|ed)?",
    r"episode(s)?", r"negative control(s)?", r"denominator(s)?", r"schema(s)?", r"API(s)?",
]
BANNED = re.compile(r"\b(" + "|".join(AI_WORDS + MECHANICAL_WORDS) + r")\b", re.I)
IDENTIFIER = re.compile(
    r"\b[a-z]+_[a-z0-9_]+\b|\b(cand|rcpt|obs)_|\b[CT]\d{2}\b|\b[\w-]+\.(py|tex|md|json|pdf|txt|sql)\b"
)
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
OTHER_AUTHORS = re.compile(r"\bet al\b", re.I)
STRICT = [
    ("colon", re.compile(r":")),
    ("web address with https", re.compile(r"https?://", re.I)),
    ("banned word", BANNED),
    ("other author", OTHER_AUTHORS),
]


def pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True
    ).stdout


def pdf_metadata(path: Path) -> str:
    info = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout
    return "\n".join(
        line.split(":", 1)[1].strip()
        for line in info.splitlines()
        if line.split(":", 1)[0] in ("Title", "Subject", "Keywords", "Author", "Creator", "Producer")
    )


def docx_paragraphs(path: Path) -> list[tuple[str, str]]:
    """Each paragraph of the document as (prose, inline code), without whole paragraphs in the
    monospace "Code" style, then the core properties."""
    out = []
    with zipfile.ZipFile(path) as archive:
        parts = [n for n in archive.namelist() if re.fullmatch(r"word/(document|header\d*|footer\d*)\.xml", n)]
        document = "".join(archive.read(name).decode("utf-8") for name in sorted(parts))
        for paragraph in re.findall(r"<w:p[ >].*?</w:p>", document, re.S):
            if '<w:pStyle w:val="Code"/>' in paragraph:
                continue
            prose, code = [], []
            for run in re.findall(r"<w:r[ >].*?</w:r>", paragraph, re.S):
                text = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", run, re.S))
                (code if '<w:rStyle w:val="InlineCode"/>' in run else prose).append(text)
            out.append((html.unescape("".join(prose)), html.unescape(" ".join(code))))
        core = archive.read("docProps/core.xml").decode("utf-8")
        out += [(html.unescape(v), "") for v in re.findall(r"<(?:dc|cp):[A-Za-z]+>(.*?)</(?:dc|cp):[A-Za-z]+>", core, re.S)]
    return out


def docx_text(path: Path) -> str:
    return "\n".join(prose for prose, _ in docx_paragraphs(path))


def markdown_prose(path: Path) -> str:
    """A Markdown file without its fenced code blocks, inline code and table rule lines."""
    text = re.sub(r"^```.*?^```", "", path.read_text(encoding="utf-8"), flags=re.S | re.M)
    text = re.sub(r"^\|[ :|-]+\|$", "", text, flags=re.M)
    return re.sub(r"`[^`]*`", "", text)


def tex_notes(path: Path) -> list[str]:
    """The text of every \\note{...} block in a beamer source, with braces balanced."""
    source = path.read_text(encoding="utf-8")
    notes = []
    for match in re.finditer(r"\\note\{", source):
        depth, i = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(source[i], 0)
            i += 1
        notes.append(source[match.end() : i - 1])
    return notes


def tex_to_text(tex: str) -> str:
    """Plain words of a short LaTeX passage, enough to compare it with the script."""
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    tex = tex.replace("\\$", "$").replace("\\%", "%").replace("~", " ").replace("\\,", " ")
    tex = re.sub(r"\\(textbf|textit|emph|emphasize)\{([^{}]*)\}", r"\2", tex)
    tex = re.sub(r"\\[A-Za-z]+\*?", " ", tex)
    return re.sub(r"\s+", " ", tex.replace("{", " ").replace("}", " ")).strip()


def script_slides(path: Path) -> list[str]:
    """The spoken text of each "## Slide" part of pres-note.md, stage directions included."""
    parts = re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]
    out = []
    for part in parts:
        _, _, body = part.partition("\n")
        lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", ">", "|"))]
        out.append(re.sub(r"\s+", " ", " ".join(lines).replace("_", "")).strip())
    return out


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9$%]+", " ", text.lower()).strip()


def main() -> int:
    hits = 0
    checked = 0

    def report(name: str, number: int, rule: str, line: str) -> None:
        nonlocal hits
        hits += 1
        print(f"{name}:{number}: [{rule}] {line.strip()[:160]}")

    # Rule set 1, punctuation on everything.
    sources = [(p, pdf_text) for p in PDFS] + [(p, docx_text) for p in DOCX]
    sources += [(p, lambda f: f.read_text(encoding="utf-8")) for p in SCRIPTS]
    sources += [(p, markdown_prose) for p in READMES]
    for name, read in sources:
        path = HERE / name
        if not path.exists():
            print(f"missing: {name}")
            continue
        checked += 1
        for number, line in enumerate(read(path).splitlines(), 1):
            if FORBIDDEN.search(line):
                report(name, number, "dash or semicolon", line)
    # The raw speaker notes too, since "--" in a note is an en dash once typeset.
    if (HERE / SLIDES_TEX).exists():
        checked += 1
        for number, note in enumerate(tex_notes(HERE / SLIDES_TEX), 1):
            if FORBIDDEN.search(note):
                report(f"{SLIDES_TEX} note", number, "dash or semicolon", note)

    # Rule set 2, the deliverables.
    strict = []  # (name, number, prose, code, identifiers checked)
    for name in PDFS:
        path = HERE / name
        if path.exists():
            text = pdf_text(path) + "\n" + pdf_metadata(path)
            strict += [(name, n, line, "", True) for n, line in enumerate(text.splitlines(), 1)]
    for name in SCRIPTS:
        path = HERE / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            strict += [(name, n, line, "", True) for n, line in enumerate(text.splitlines(), 1)]
    tex_path = HERE / SLIDES_TEX
    notes = tex_notes(tex_path) if tex_path.exists() else []
    for n, note in enumerate(notes, 1):
        strict.append((f"{SLIDES_TEX} note", n, tex_to_text(note), "", True))
    for name in DOCX:
        path = HERE / name
        if path.exists():
            strict += [(name, n, prose, code, False) for n, (prose, code) in enumerate(docx_paragraphs(path), 1)]
            for n, (prose, code) in enumerate(docx_paragraphs(path), 1):
                if PLACEHOLDER.search(prose + " " + code):
                    report(name, n, "unfilled placeholder", prose + " " + code)
    for name, number, prose, code, identifiers in strict:
        for rule, pattern in STRICT:
            target = prose if rule in ("banned word", "other author") else prose + " " + code
            match = pattern.search(target)
            if match:
                report(name, number, f"{rule} '{match.group(0)}'", target)
        if identifiers:
            match = IDENTIFIER.search(prose)
            if match:
                report(name, number, f"code identifier '{match.group(0)}'", prose)

    # (g) The speaker notes say what the script says.
    script = HERE / "slides/pres-note.md"
    if notes and script.exists():
        spoken = script_slides(script)
        if len(spoken) > len(notes):
            report(SLIDES_TEX, 0, "notes", f"{len(spoken)} script parts but {len(notes)} notes")
        for n, (said, note) in enumerate(zip(spoken, notes), 1):
            if normalise(said) != normalise(tex_to_text(note)):
                report(SLIDES_TEX, n, "note differs from pres-note.md", tex_to_text(note))

    print(f"{checked} files checked, {hits} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
