"""Crop the Wave 2 storyboard frames to the panels the slides, poster and documentation show.

The frames come from the automated dry run tests/e2e/storyboard.py (Wave 2 packet). Each crop
drops the dark storyboard caption band and keeps one panel at its native resolution.

    python3 crop_frames.py        (needs Pillow)
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / "handoffs" / "wave_2" / "evidence" / "storyboard"
OUT = HERE / "frames"

# name: (source frame, (left, top, right, bottom)) in the 1536 x 942 frame
CROPS: dict[str, tuple[str, tuple[int, int, int, int]]] = {
    "grant_agent": ("story_03_agent_authority.png", (958, 92, 1514, 372)),
    "notice": ("story_04_notice_is_a_claim.png", (57, 222, 724, 412)),
    "status_line": ("story_05_verified_status.png", (42, 405, 920, 462)),
    "receipt_line": ("story_07_committed_with_receipt.png", (42, 143, 870, 173)),
    "status_check": ("story_05_verified_status.png", (22, 92, 940, 585)),
    "before_after": ("story_07_committed_with_receipt.png", (22, 92, 940, 670)),
    "stale_duplicate": ("story_08_stale_and_duplicate.png", (40, 90, 740, 790)),
    "backup_hold": ("story_09_backup_held_and_asked.png", (958, 92, 1514, 465)),
    "live_card": ("story_12_live_decision_card.png", (22, 78, 760, 910)),
    "checkin": ("story_16_participant_check_in.png", (0, 78, 1536, 942)),
    "community_replanned": ("story_17_community_replanned.png", (22, 92, 940, 835)),
    "pantry_loaded": ("story_19_pantry_loaded.png", (22, 92, 940, 560)),
    "pantry_distributed": ("story_23_distributed.png", (22, 92, 940, 590)),
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, (frame, box) in CROPS.items():
        with Image.open(SOURCE / frame) as image:
            image.convert("RGB").crop(box).save(OUT / f"{name}.png", optimize=True)
        print(f"{name}.png from {frame} {box}")


if __name__ == "__main__":
    main()
