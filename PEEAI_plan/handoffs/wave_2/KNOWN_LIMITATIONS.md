# Known limitations

The categories follow the Wave 1 packet. Anything Wave 2 requires that is missing or failed is
listed as unpassed or unverified, never reclassified as optional. The Wave 1 limitations in
[`../wave_1/KNOWN_LIMITATIONS.md`](../wave_1/KNOWN_LIMITATIONS.md) still apply unless an item
below says otherwise.

## Unpassed or partial Wave 2 items

* **W2.4 (MBTA, stretch) is not done.** There is no `integrations/` module and no transit
  adapter, and the MBTA key was not read.
* **Closed while finishing Wave 2 (2026-10-25)**, each kept here so the first version of this
  packet can be read against it:
  * *The live agent could not run the pantry profile.* P2 (`live/1.0.0`) now offers the pantry
    adapter's own stock candidates (contract section 16). Its development run
    `live_p2-live_pantry_dev01` completed the canonical sequence: a handoff request, the staff
    receipt (24/16 → 40/0), a 40-kit hold, the commit, and 40 of 40 distributed on time. P3 did
    the same. The failed Wave 2 run `live_pantry_dev01` (0 model calls, 0 of 40) is kept as
    recorded.
  * *Future comparison parity was partial.* P1 (`tool-use/1.0.0`) and P3 (`verify-all/1.0.0`)
    are built. `agent/policies/selective.py` re-exports P2. P0–P3 read the same grant, tools and
    candidates (`tests/test_policy_parity.py`), and each completes all three suites with a
    scripted model (`tests/test_live_workflow.py`).
  * *W2.5 files.* `tests/test_live_workflow.py` and `plan_b/evaluation/development/` exist.
  * *Isolation list.* The agent modules, the pantry rule policy and the pantry adapter and stock
    modules are in `tests/test_runner_isolation.py::ISOLATED_MODULES`.

## Live-run limitations

* **The P1-P3 development runs** (`plan_b/evaluation/development/README.md`) are one trial
  each, on development cases. They make no comparative claim and measure no variance.
  * **P1's recorded runs span two prompts.** The first five P1 runs used `tool_use.v1` with a
    1536-token turn limit. After the pantry_dev01 run failed on our documentation defect
    (DECISIONS W2-D11), each of the five cases was run once more under the shipped `tool_use.v2`
    with 4096 tokens: pantry_dev01 in the finishing step, and dev01, dev02, dev04 and
    skills_dev01 in the audit step. The five `tool_use.v1` runs are kept as recorded and marked
    superseded; every current P1 run used `tool_use.v2`.
  * **P1 reached the 8-call model cap in three of its five current runs** (dev01 at 17:24,
    dev02 at 17:44, skills_dev01 at 10:06), and in three superseded runs (dev02 at 17:44,
    skills_dev01 at 10:06, the first pantry_dev01 run at 12:35). Each new observation, such as a
    check-in or an arrival notice, is material to its attention rule, so P1 spends a model call
    confirming `keep` after each one. In those runs the plan was already in place, but a later
    disruption would have gone unanswered.
  * **P3's model-call counts are not P2's.** P3's status checks are made by the server without
    a model call, so fewer model calls do not mean less verification.
  * **P1's per-run spend** was 0.16–0.26 USD in these development runs, because each P1 turn
    carries the full state and the evaluation. Per-run figures for every policy are in
    VERIFICATION.md section 4; they support no cost comparison.
  * **The output-token limits differ by policy.** P1, P2 and P3 share the endpoint, the model id
    and the caps, but not `max_tokens`: P1 sends 4096 per turn; P2 and P3 send 1024 per choice
    and 2048 per interpretation. Reasoning tokens count against each limit, which is the defect
    W2-D11 found in P1's first limit. No P2 or P3 call was cut off in the recorded runs. Each
    call records its own `max_tokens`; the Wave 3 freeze should fix these values with the
    prompts.
* **One run per case, not repeated.** Each recorded live run is a single trial. Model choices,
  call latencies and the calls' wall-clock `started_at` vary between runs, so live traces are
  evidence of that one run, not reproducible artifacts. Replay is the reproducible form. Nothing
  here measures variance or supports a comparative claim.
* **Development evidence only.** The cases are the development cases (dev01–dev06,
  skills_dev01/02, pantry_dev01), excluded from any held-out evaluation by the plan.
* **Bounded failures were exercised mostly with scripted transports.** An unknown entity,
  timeouts, HTTP errors, spend caps and lost responses were not induced against the real
  provider. These failure paths did occur live:
  * malformed output: two P1 replies were cut off at the 1536-token limit in the first P1
    pantry_dev01 run. One was repaired; the other ended the run at the model-call cap;
  * exhausted caps: P1 reached the 8-call model cap in six runs (three current, three
    superseded; see above), recorded as `stop`, with nothing invented;
  * a real stale revision in `live_skills_dev02`: an apply rejected `REVISION_CONFLICT` after
    the organizer's goal-version change, recorded as `wait` / `stale_revision`, then re-evaluated
    and applied;
  * a real status outage in `live_dev06`: the query envelope was `unavailable`, and the robust
    swap followed.
* **The model's rationale sometimes misstates a detail.** For example, it called the rank-1
  candidate "lowest-rank" in dev02, and named a candidate id from an earlier evaluation. The
  rationale is stored and shown only as untrusted text, and the action is validated by the
  server, so this never changes a result. It is a reason not to present rationales as
  explanations.
* **Cost accounting** uses the provider-reported usage (`cost_basis: provider_usage` for every
  recorded call). The ledger is the record. It is local to `apps/plan_b/var/`, ignored by git, and
  summarized, not copied, in the evidence.

## Simplifications in the delivered semantics

* **Pantry:**
  * In the browser the staff simulator is off, and a human staff tab records a handoff at once:
    the modeled 2-minute latency is not enforced there.
  * The staff forms do not pre-check the handoff cutoff; the server refuses with
    `HANDOFF_WINDOW_CLOSED`.
  * A late distribution may accrue staffed minutes after the service activity's planned end,
    until the hard end.
  * A committed allocation cannot be cancelled.
  * The pantry fixture has no organizer principal, so no target-changing goal version exists
    there.
  * The standing `staff_handoff_rule` row stays `pending` in `scheduled_actions` by design.
* **The Wave 3 pantry transfer suite (T01–T04, `08_evaluation.md`) and a `pantry_dev03`
  variant** (alternate pool unavailable) are not authored; only pantry_dev01 and pantry_dev02
  exist.
* **`planning_map.py` does not project the pantry fields** to planning artifacts yet.
* **Resource offers:**
  * An offer must cover the registered window to its end.
  * An offer for later makes the resource `expected` until a new offer confirms it.
  * A status or arrival record always outranks the owner's offer.
  * In `dev_fixture_01` nobody speaks for equipment, so every campus offer is refused.
* **Policy selection is held in memory.** After a server restart:
  * an episode keeps the policy of its last decision, and the new instance continues its
    model- and tool-call counters and its recorded model spend, so the per-run USD cap holds
    across the restart (the ledger records the new instance's calls under a new run id);
  * one without decisions reverts to `rules`, so a selection made before the coordinator's
    first decision is lost.
* **`EventStateView` has no mode-label field.** The label travels on every stored decision and
  through `/api/policy` and `/api/moderator/policy`, so before an episode's first decision only
  those endpoints show it.
* **Role tabs act on their last poll.** A form sends the revision of the tab's last 1.5-second
  poll, so an action just after another change is rejected `REVISION_CONFLICT` and must be resent.
  This is correct behaviour, but there is no automatic refresh before sending.
* **Pantry policies.** Each (source, destination) handoff is requested once, as by P0, even
  after a partial handoff and its release. In pantry_dev01, P2's wait for the staff handoff was
  model-chosen, because a pool hold stayed on the menu.
* **Live interpretation is not the rule parser.** Verify-only behaviour is approximated: a
  reading that names a registered resource and proposes `query_status` prompts a status check,
  never a hypothesis. The model may class some notices differently from the parser, for example
  `inapplicable` against `unresolved`; the server-side identity checks still apply.
* **New JSON keys with defaults** appear in campus snapshots, candidates and traces (runtime
  1.1.0 fields, `details.policy_mode`). Campus trace bytes therefore differ from the Wave 1
  evidence. Outcomes, request bodies, idempotency keys and digests are unchanged, and the
  dev01–dev06 result lines are identical (`reports/wave1_parity.json`).

## Unverified acceptance criteria

* **Not community validation.** Every fixture is fictional and synthetic, and no participant
  provided feedback. The community workflow is a local multi-tab walkthrough
  (`tests/e2e/walkthrough_wave2.py`), which the plan accepts for implementation and does not
  count as validation.
* **Browsers and accessibility**, as in Wave 1:
  * only Chromium was driven (Playwright);
  * Firefox, Safari and screen readers were not run;
  * comprehension by new viewers was not tested with people.
* **Live decisions in a real browser session were exercised once, by hand, not by a test.** The
  Wave 2 walkthrough selects the live agent but never runs it. In the audit step one press of
  **Run live agent** on a fresh dev01 made 3 paid model calls ($0.03655) and recorded verify,
  the swap and keep; the same check against an unreachable endpoint recorded a labeled `wait`.
  No automated browser test runs a model-driven policy. Live decision cards are otherwise covered
  by web unit tests with live-shaped data and by replays of recorded traces.
* **Python 3.11** is declared but not run; every check ran on CPython 3.12.11.

## Process disclosures

* **Network access while finishing Wave 2 (2026-10-25):**
  * one read-only `GET /api/v1/key` before the development runs. It was made by a scratch
    script that loaded the endpoint configuration, read the key file in-process at call time
    and sent the key only in the `Authorization` header. Only the numeric fields were printed,
    and nothing was written;
  * the completion calls of the 16 recorded development runs, made by the provider;
  * nothing else: no public model list, and the MBTA key was not read.
* **Network access and key use in the audit step (2026-10-25):**
  * the completion calls of the four P1 reruns (30 calls), made by the provider;
  * one press of **Run live agent** through the browser (3 calls), made by the server's provider;
    a second check pointed the endpoint at a closed port on 127.0.0.1, so it reached no network
    (the ledger records it at cost 0);
  * the security audit's key comparison: one script read `.local/keys/openrouter.key` into memory
    and searched the working tree for the key and its encodings, printing file names only. It
    found none. This is a read outside server-side code, made because the audit task asks for
    that comparison; the key was never printed or written.
* **Network access in this wave:**
  * one read-only `GET /api/v1/key` before the live runs (authorized for this step; only numeric
    fields were printed);
  * the gate's and the live runs' completion calls;
  * one unauthenticated `GET` of OpenRouter's public model list, made by the Build 1 worker to
    confirm the model id, its price and structured-output support.
* **A key read outside server-side code.** After the gate, the Build 1 worker read the real key
  into a shell variable to search the gate record and the ledger for it. Nothing was found, and
  the key was never printed or written. This was a read outside server-side code. The live-run
  evidence here is scanned only for credential shapes, without reading the key.
* **One record path still to harden (audit step).** Run records carry `matches_expectation`,
  which, with the public outcome, reveals a case's private expected outcome. That is harmless
  for development cases, whose private files are committed, but a held-out run in Wave 3 should
  keep that bit in `runner_private/` only. The audit's other record path is closed: the
  integration step made `agent/gate.py` record a raised exception's class and a sanitized
  message (no local path, no credential-shaped token; `tests/test_gate_error_text.py`), as
  `scripts/run_live_cases.py` already does. The committed gate record has `error: null`.
* **Concurrent workers.** The live runs were recorded after every worker of the wave had
  finished, from the working tree that the integrator then committed. The deterministic
  evidence was regenerated afterwards from a clean checkout of `fd04d48` (DECISIONS W2-D9).

## Wave 1 debt still open

* `AuthorizationRequest` has no stored open or answered state; the board still derives it.
* There is no in-place late start.
* Authentication failures are not persisted.
* Trace hashes are not signed.
* The boundary lint is a static guard.
