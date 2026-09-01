"""Task 14 acceptance tests: the derivation note is complete and machine-checkable where possible.

The note is prose, so most of it is reviewed by a human. These tests guard the parts that Tasks
15-17 will depend on programmatically: the validity table must exist and cover every family, the
scope disclaimers must be present, every source must be cited, and the alpha allocation the note
specifies must actually sum to a valid budget.

Guards collie-verifier R1.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from collie.contracts import ShockFamily

NOTE = Path(__file__).resolve().parents[1] / "docs" / "derivation_note.md"


@pytest.fixture(scope="module")
def note() -> str:
    if not NOTE.is_file():
        pytest.fail("docs/derivation_note.md is the Task 14 deliverable and blocks Tasks 15-16")
    return NOTE.read_text(encoding="utf-8")


def test_the_claim_scope_is_stated_and_the_overclaims_are_explicitly_denied(note: str) -> None:
    """R1.2: the probability statement's scope must be unambiguous in the note itself."""
    assert "model-conditional, anytime-valid, per-episode" in note
    for denial in (
        "not** dataset-wide family-wise control",
        "a safety guarantee",
        "a profit guarantee",
        "wrong-family activation",
    ):
        assert denial in note, f"the note must explicitly deny: {denial!r}"


def test_filtration_and_event_ordering_are_fixed(note: str) -> None:
    """R1.7: the (F_{r-1}, A_{r-1}) conditioning is the whole basis of admissibility."""
    assert "immediately before `A_t` is\n  chosen**" in note or "immediately before" in note
    assert "(F_{r-1}, A_{r-1})" in note
    assert "A_t` influences `Y_{t+1}`" in note
    # The closed-loop argument is the subtle part; it must be written down, not assumed.
    assert "closed-loop" in note.lower()


def test_post_selection_freezing_argument_is_present(note: str) -> None:
    assert "F_{tau_j}`-measurable" in note
    assert "starts at `tau_j + 1`" in note or "start at `tau_j + 1`" in note


def test_the_theorem_states_the_ville_plus_union_bound(note: str) -> None:
    """R1.2: the exact statement, with the geometric allocation that makes it sum to alpha."""
    assert "Ville" in note
    assert "alpha_episode * 2^{-j}" in note
    assert "SUM_{j>=1} 2^{-j}  =  1" in note or "SUM_{j>=1} 2^{-j} = 1" in note


def test_alpha_allocation_actually_sums_within_budget() -> None:
    """The note's allocation must be arithmetically valid for the permitted proposal count.

    Checked in code rather than trusted in prose, because Task 15.1 asserts the same property.
    """
    alpha_episode = 0.05
    for max_proposals in (1, 2, 3, 10):
        spent = sum(alpha_episode * 2**-j for j in range(1, max_proposals + 1))
        assert spent <= alpha_episode + 1e-12, (
            f"allocation over {max_proposals} proposals exceeds the episode budget"
        )
    # With the primary design's two proposals, at least half the budget is never spent.
    two = sum(alpha_episode * 2**-j for j in (1, 2))
    assert two == pytest.approx(0.75 * alpha_episode)


def test_forward_recursion_is_specified_with_a_finite_state_argument(note: str) -> None:
    """R1.3: exactness depends on the state space being genuinely finite."""
    assert "forward" in note.lower()
    assert "(L_max + 2)^{L_max}" in note
    assert "1296" in note, "the concrete state-space bound for L_max=4 should be stated"
    assert "brute-force" in note, "exactness must be validated against enumeration"


def test_no_fifo_identity_is_assumed_on_the_arrival_side(note: str) -> None:
    assert "marginalise" in note or "marginalize" in note
    assert "FIFO" in note


def test_compound_decision_forbids_multiplying_marginals(note: str) -> None:
    """R1.5: the prohibited shortcut must be named as prohibited."""
    assert "alpha splitting" in note.lower() or "alpha split" in note.lower()
    assert "prohibited" in note
    assert "conditional_independence" in note


def test_validity_table_covers_every_family_and_marks_the_exclusions(note: str) -> None:
    """R1.4: the table is authoritative and Task 16 asserts code agreement with it."""
    table_section = note.split("## 9.")[1].split("## 10.")[0]
    for family in ShockFamily:
        if family is ShockFamily.NO_CHANGE:
            continue
        assert f"`{family.value}`" in table_section, f"validity table omits {family.value}"
    assert "empirical-only" in table_section
    assert "anytime-valid" in table_section


def test_the_censored_observation_model_has_no_formal_claim_yet(note: str) -> None:
    """Formal claims are restricted to observation models where validity is established."""
    table_section = note.split("## 9.")[1].split("## 10.")[0]
    censored_row = next(line for line in table_section.splitlines() if "censored sales" in line)
    assert "empirical-only" in censored_row


def test_the_plug_in_variant_is_permanently_unguaranteed(note: str) -> None:
    assert "no finite-sample guarantee" in note
    table_section = note.split("## 9.")[1].split("## 10.")[0]
    plug_in_row = next(line for line in table_section.splitlines() if "plug-in" in line)
    assert "permanently" in plug_in_row


def test_official_instances_are_excluded_from_arrival_side_claims(note: str) -> None:
    """The honest limitation: the stochastic lead-time law's probabilities are unpublished."""
    assert "COLLIE-ShockSpec episodes" in note
    assert "not published" in note or "unpublished" in note or "are not\npublished" in note


def test_refutation_and_expiry_are_marked_empirical(note: str) -> None:
    assert "Refutation and expiry are empirical" in note


def test_all_three_primary_sources_are_cited_with_identifiers(note: str) -> None:
    """R1.6: every claim cites a source or the environment contract."""
    for ident in ("arXiv:2210.01948", "arXiv:2203.03532", "PMLR 202:30908"):
        assert ident in note, f"missing citation {ident}"
    assert "docs/env_contract.md" in note
    for tag in ("[S1]", "[S2]", "[S3]", "[C]"):
        assert tag in note


def test_sources_are_paraphrased_not_quoted_at_length(note: str) -> None:
    """Licensing discipline: no long verbatim runs from any source."""
    sources_section = note.split("## 11.")[1]
    quoted = re.findall(r'"([^"]{120,})"', sources_section)
    assert not quoted, f"overlong quoted passage in the sources section: {quoted}"


def test_the_note_lists_what_tasks_15_to_17_must_implement(note: str) -> None:
    impl = note.split("## 10.")[1].split("## 11.")[0]
    for module in ("alpha.py", "eprocess.py", "supply_forward.py", "lifecycle.py"):
        assert module in impl, f"the note must tell Task 15-17 to build {module}"
    assert "2,000 Monte-Carlo" in impl
