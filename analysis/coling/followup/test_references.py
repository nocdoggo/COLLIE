"""Synthetic annotation ordering, ambiguity, and adjudication checks."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from analysis.coling.followup.records import Certainty, StatementType
from analysis.coling.followup.references import (
    FirstPass, HumanAlternative, SpecifiedPass, adjudicate_convention, adjudicate_natural,
)


T0 = datetime(2028, 1, 1, tzinfo=timezone.utc)


def option(*, start=date(2028, 3, 1), end=date(2028, 3, 14), certainty="estimated",
           model_certainty=Certainty.ESTIMATED):
    return HumanAlternative(StatementType.RECOVERY, "finite", start, end, certainty,
                            model_certainty, "fictional target")


def first(rater, stage="natural", *, item="I1", submitted=T0, options=None, **changes):
    values = dict(judgment_id=f"{rater}-{stage}", item_id=item, rater_code=rater, stage=stage,
                  options=options or (option(),), submitted_utc=submitted,
                  guide_exposure="prior_original_guide", outputs_seen=False, sensitivity_seen=False)
    values.update(changes)
    return FirstPass(**values)


def specified(rater, *, item="I1", shown=T0 + timedelta(seconds=2),
              submitted=T0 + timedelta(seconds=3), **changes):
    values = dict(judgment_id=f"{rater}-specified", item_id=item, rater_code=rater,
                  options=(option(),), shown_utc=shown, submitted_utc=submitted,
                  outputs_seen=False, sensitivity_seen=False)
    values.update(changes)
    return SpecifiedPass(**values)


def natural(*, options=None, passes=None, **changes):
    values = dict(item_id="I1", reference_version="v1", first_passes=passes or [first("A1"), first("A2")],
                  options=(option(),) if options is None else options, adjudicator="ADJ",
                  adjudicated_utc=T0 + timedelta(seconds=5), outputs_seen=False,
                  sensitivity_seen=False, rationale="Resolve from the notice")
    values.update(changes)
    return adjudicate_natural(**values)


def convention(*, first_passes=None, specified_passes=None, **changes):
    values = dict(item_id="I1", reference_version="v1",
                  first_passes=first_passes or [first("A1", "unspecified"), first("A2", "unspecified")],
                  specified_passes=specified_passes or [specified("A1"), specified("A2")],
                  defensible_options=(option(),), specified_options=(option(),), adjudicator="ADJ",
                  adjudicated_utc=T0 + timedelta(seconds=5), outputs_seen=False,
                  sensitivity_seen=False, rationale="Resolve from the notice and specified instruction")
    values.update(changes)
    return adjudicate_convention(**values)


def test_natural_reference_preserves_distinct_defensible_readings():
    alternatives = (option(), option(start=date(2028, 3, 5)))
    result = natural(options=alternatives)
    assert result.human_options == alternatives and len(result.reference.alternatives) == 2
    assert result.reference.missing_reason is None
    assert result.first_pass_ids == ("A1-natural", "A2-natural")
    nonunique = natural(options=(option(), option(end=date(2028, 3, 15))))
    assert nonunique.reference.missing_reason == "reference_endpoint_not_unique"


def test_partial_start_and_unmapped_certainty_do_not_erase_a_unique_end():
    ambiguous = option(start=None, certainty="conditional", model_certainty=None)
    result = natural(options=(ambiguous,))
    assert result.human_options == (ambiguous,)
    assert result.reference.missing_reason is None
    assert result.reference.alternatives[0].end == date(2028, 3, 14)
    assert result.reference.alternatives[0].start is None
    assert result.reference.alternatives[0].certainty is None


def test_unresolved_or_contradictory_alternatives_remain_explicit():
    unresolved = HumanAlternative(StatementType.RECOVERY, "unresolved", None, None,
                                  "unresolved", None, "")
    result = natural(options=(unresolved,))
    assert result.human_options == (unresolved,)
    assert result.reference.missing_reason == "reference_period_unresolved"
    contradictory = option(model_certainty=Certainty.UNDETERMINED)
    result = natural(options=(contradictory,))
    assert result.human_options == (contradictory,)
    assert result.reference.missing_reason == "inconsistent_reference_fields"


def test_blinding_anonymity_and_chronology_gates_are_enforced():
    with pytest.raises(ValueError, match="independent"):
        natural(passes=[first("A1")])
    with pytest.raises(ValueError, match="identities"):
        natural(passes=[first("A1"), first("A1")])
    with pytest.raises(ValueError, match="exposed"):
        natural(passes=[first("A1", outputs_seen=True), first("A2")])
    with pytest.raises(ValueError, match="blind"):
        natural(sensitivity_seen=True)
    with pytest.raises(ValueError, match="follow"):
        natural(adjudicated_utc=T0)
    with pytest.raises(ValueError, match="ADJ"):
        natural(adjudicator="A1")
    with pytest.raises(ValueError, match="UTC"):
        first("A1", submitted=T0.replace(tzinfo=None))
    with pytest.raises(ValueError, match="anonymous"):
        first("Example Person")


def test_convention_second_pass_is_separate_and_after_both_submissions():
    result = convention()
    assert result.specified.interval.end == date(2028, 3, 14)
    assert result.first_pass_ids == ("A1-unspecified", "A2-unspecified")
    assert result.specified_pass_ids == ("A1-specified", "A2-specified")
    too_early = [specified("A1", shown=T0), specified("A2")]
    with pytest.raises(ValueError, match="before both"):
        convention(specified_passes=too_early)
    exposed = [specified("A1", outputs_seen=True), specified("A2")]
    with pytest.raises(ValueError, match="blind"):
        convention(specified_passes=exposed)


def test_convention_reference_preserves_unresolved_human_alternatives():
    ambiguous = option(start=None, certainty="conditional", model_certainty=None)
    result = convention(defensible_options=(option(), ambiguous),
                        specified_options=(option(), option(end=date(2028, 3, 15))))
    assert result.defensible_unresolved_reason == "human_reading_not_fully_mapped"
    assert result.human_defensible_options == (option(), ambiguous)
    assert result.specified is None and result.specified_unresolved_reason == "specified_target_not_unique"
    assert len(result.human_specified_options) == 2


def test_convention_interval_can_be_known_when_human_certainty_has_no_model_mapping():
    conditional = option(certainty="conditional", model_certainty=None)
    result = convention(defensible_options=(conditional,), specified_options=(conditional,))
    assert result.defensible_unresolved_reason is None
    assert result.specified_unresolved_reason is None
    assert result.specified.interval.end == date(2028, 3, 14)
    assert result.human_specified_options == (conditional,)
