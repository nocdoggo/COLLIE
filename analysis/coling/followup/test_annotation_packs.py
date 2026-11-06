"""Legacy synthetic-only pack checks; no new human annotation is planned.

The local test fixture uses private sampler mechanics on invented events. It
does not re-enable the public direct draw or establish a gated real pack.
"""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from analysis.coling.followup.annotation_packs import (
    convention_first_pack, convention_specified_pack, natural_pack, pilot_pack, role_pack,
)
from analysis.coling.followup.prompts import EXPLICIT
from analysis.coling.followup.role_materials import pilot_notices, synthetic_role_programme as role_programme
from analysis.coling.followup.test_references import T0, first
from analysis.coling.followup.test_sampling import catalog, events, select_c, select_n


def test_natural_view_contains_only_notice_and_assigned_identity():
    sample = select_n(events(70), catalog(), package="reduced")
    one = natural_pack(sample, rater="A1")
    two = natural_pack(sample, rater="A2")
    assert len(one.notices) == 60 and one.sha256 != two.sha256
    assert {item.item_id for item in one.notices} == {item.item_id for item in two.notices}
    assert one.condition_block == "" and one.stage == "natural"
    assert set(asdict(one.notices[0])) == {"item_id", "update_date", "notice_text", "group_id"}
    assert natural_pack(sample, rater="A1").sha256 == one.sha256
    with pytest.raises(ValueError, match="anonymous"):
        natural_pack(sample, rater="Example Person")


def test_convention_block_waits_for_both_complete_first_passes():
    corpus = events(240)
    n = select_n(corpus, catalog(), package="reduced")
    c = select_c(corpus, catalog(), package="reduced", natural_draw=n)
    first_view = convention_first_pack(c, rater="A1")
    assert first_view.condition_block == "" and len(first_view.notices) == 30
    first_passes = [replace(first(rater, "unspecified", item=item.event.statement_group_id),
                            judgment_id=f"{item.event.statement_group_id}-{rater}")
                    for item in c.selected for rater in ("A1", "A2")]
    digest = hashlib.sha256(EXPLICIT.encode()).hexdigest()
    specified_view = convention_specified_pack(
        c, rater="A1", first_passes=first_passes, shown_utc=T0 + timedelta(seconds=1),
        condition_block=EXPLICIT, block_sha256=digest,
    )
    assert specified_view.condition_block == EXPLICIT and specified_view.stage == "specified"
    assert {item.item_id for item in specified_view.notices} == {item.item_id for item in first_view.notices}
    with pytest.raises(ValueError, match="both independent"):
        convention_specified_pack(c, rater="A1", first_passes=first_passes[:-1],
                                  shown_utc=T0 + timedelta(seconds=1), condition_block=EXPLICIT, block_sha256=digest)
    with pytest.raises(ValueError, match="follow both"):
        convention_specified_pack(c, rater="A1", first_passes=first_passes,
                                  shown_utc=T0, condition_block=EXPLICIT, block_sha256=digest)
    with pytest.raises(ValueError, match="match its recorded hash"):
        convention_specified_pack(c, rater="A1", first_passes=first_passes,
                                  shown_utc=T0 + timedelta(seconds=1), condition_block=EXPLICIT, block_sha256="0" * 64)


def test_role_views_hide_factor_and_primary_labels_but_keep_seed_groups():
    seeds = role_programme("reduced").assigned[:3]
    a1, a2 = role_pack(seeds, rater="A1"), role_pack(seeds, rater="A2")
    assert len(a1.view.notices) == 12
    assert a1.private_identity_map == a2.private_identity_map
    assert {item.item_id for item in a1.view.notices} == {item.item_id for item in a2.view.notices}
    groups = {item.group_id for item in a1.view.notices}
    assert len(groups) == 3
    assert all(sum(item.group_id == group for item in a1.view.notices) == 4 for group in groups)
    view = json.dumps(asdict(a1.view))
    assert ":competitor:" not in view and ":neutral:" not in view and "primary" not in view
    assert all(len(item.item_id) == 21 and item.item_id.startswith("V") for item in a1.view.notices)


def test_pilot_pack_is_separate_and_does_not_contain_reference_fields():
    pack = pilot_pack(pilot_notices(), rater="A1")
    assert pack.cohort == "pilot" and pack.stage == "practice" and len(pack.notices) == 12
    assert all("Practice notice:" in item.notice_text for item in pack.notices)
    assert "reference" not in json.dumps(asdict(pack))
