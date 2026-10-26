"""A small stopwatch for a timed human rehearsal of a spoken script.

It reads the slide budgets ("## Slide N. Title" headings with an "_about S seconds_" line, as in
timing.py) and the bold checkpoints of a script, shows the budget of the first slide, and waits.
Press Enter each time you advance to the next slide. After the last slide it prints, per slide,
the time you took against the budget, the running total against the plan, and one Markdown row to
paste into the timing table of PEEAI_plan/handoffs/wave_3/REHEARSALS.md. It writes no file and
needs no network.

    python3 rehearsal_timer.py slides/pres-note.md     # the 7-minute deck, 420 s
    python3 rehearsal_timer.py poster/poster-note.md   # the 2-minute poster, 120 s

Press Enter once to start the clock on slide 1. Type q and Enter to stop early.
"""

import re
import sys
import time
from pathlib import Path


def budgets(path: str) -> list[tuple[str, int]]:
    """Each timed section's title and planned seconds, in order. Sections with no plan (the
    backup slides) are left out."""
    text = Path(path).read_text(encoding="utf-8")
    slides = []
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = part.partition("\n")
        planned = re.search(r"^_about (\d+) seconds_", body, re.M)
        if planned and int(planned.group(1)) > 0:
            slides.append((title.strip(), int(planned.group(1))))
    return slides


def clock(seconds: float) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(round(seconds))
    return f"{sign}{seconds // 60}:{seconds % 60:02d}"


def main(path: str) -> int:
    slides = budgets(path)
    if not slides:
        print(f"no '_about S seconds_' budgets found in {path}")
        return 1
    plan_total = sum(seconds for _, seconds in slides)
    print(f"{len(slides)} timed sections, plan {clock(plan_total)}. Press Enter to start.")
    if sys.stdin.readline().strip().lower() == "q":
        return 0
    start = last = time.monotonic()
    taken: list[float] = []
    planned_so_far = 0
    for number, (title, seconds) in enumerate(slides, start=1):
        planned_so_far += seconds
        nxt = "end" if number == len(slides) else "next slide"
        print(f"\n[{number}/{len(slides)}] {title}")
        print(f"    budget {seconds} s, be done by {clock(planned_so_far)}. Enter for {nxt}.")
        line = sys.stdin.readline()
        now = time.monotonic()
        taken.append(now - last)
        last = now
        elapsed = now - start
        over = elapsed - planned_so_far
        state = "behind" if over > 0 else "ahead"
        print(f"    took {taken[-1]:.0f} s. Total {clock(elapsed)}, {abs(over):.0f} s {state} of plan.")
        if line == "" or line.strip().lower() == "q":
            break
    total = last - start
    print("\nslide                                        took s  plan s   diff")
    for (title, seconds), spent in zip(slides, taken):
        print(f"{title[:44]:<44} {spent:>6.0f} {seconds:>7} {spent - seconds:>+6.0f}")
    print(f"{'total':<44} {total:>6.0f} {plan_total:>7} {total - plan_total:>+6.0f}")
    worst = max(zip(slides, taken), key=lambda pair: pair[1] - pair[0][1])
    print("\nRow for REHEARSALS.md (fill in the date, the place and what went wrong):")
    print(
        f"| _date_ | _place_ | {clock(total)} ({total:.0f} s) | {len(taken)}/{len(slides)} |"
        f" {worst[0][0][:30]} ({worst[1] - worst[0][1]:+.0f} s) | _notes_ |"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
