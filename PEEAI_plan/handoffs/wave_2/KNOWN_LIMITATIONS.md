# Known limitations

The categories follow the Wave 1 packet. Anything Wave 2 requires that is missing or failed is
listed as unpassed or unverified, never reclassified as optional. The Wave 1 limitations in
[`../wave_1/KNOWN_LIMITATIONS.md`](../wave_1/KNOWN_LIMITATIONS.md) still apply unless an item
below says otherwise.

## Unpassed or partial Wave 2 items

* **The live agent cannot run the pantry profile.** `live/1.0.0` has no stock-quantity options:
  its menu holds booking holds from `required_holds`, never `required_stock_holds` or a
  `stock_transfer` hold. The recorded live pantry run (`live_pantry_dev01`) behaved as follows:
  * The pantry fixture's observations are typed status records, so it found no notice to
    interpret and made **0 model calls**.
  * The server recorded `wait` ("no applicable preparation step").
  * Nothing was held, handed off or committed, so the staff simulator distributed **0 of 40**
    kits (unfulfilled 40; `matches_expectation=False`).
  * Stock stayed conserved, and no attestation was made by the agent.

  Only the deterministic `pantry-rules/1.0.0` handles the pantry sequence. Under the evaluation
  plan's rule that all policies get the same quantity adapter, this also leaves **comparison
  parity for the pantry suite unmet** until a live or LLM policy gets equal stock options.
* **Future comparison parity is partial.** P0 (`rules/1.0.0`, `pantry-rules/1.0.0`) and one
  model-driven policy (`live/1.0.0`) share these:
  * candidates, grants, executor, tools, caps and the runner;
  * the scripted actors and staff simulator;
  * prompt recording (prompt id and sha256 on every live decision).

  What is missing:
  * P1 (a capable tool-using LLM without the menu) and P3 (verify-all) are not built.
  * The plan's `agent/policies/selective.py` does not exist as a separate module: `live/1.0.0`
    is the selective controller.
* **W2.5 files not created:** `tests/test_live_workflow.py` and `evaluation/development/`. The
  live workflow is covered instead by:
  * the scripted-transport tests in `tests/test_agent_boundary.py`, which run the real provider
    client, executor and store;
  * the recorded live runs.
* **W2.4 (MBTA, stretch) is not done.** There is no `integrations/` module and no transit
  adapter, and the MBTA key was not read.
* **`tests/test_runner_isolation.py::ISOLATED_MODULES` does not list the agent modules.**
  `tests/test_agent_boundary.py::test_policy_side_modules_cannot_reach_private_input` applies the
  same static rule to them; the integrator may add them to the shared list.

## Live-run limitations

* **One run per case, not repeated.** Each recorded live run is a single trial. Model choices,
  call latencies and the calls' wall-clock `started_at` vary between runs, so live traces are
  evidence of that one run, not reproducible artifacts. Replay is the reproducible form. Nothing
  here measures variance or supports a comparative claim.
* **Development evidence only.** The cases are the development cases (dev01–dev06,
  skills_dev01/02, pantry_dev01), excluded from any held-out evaluation by the plan.
* **Bounded failures were exercised mostly with scripted transports.** Malformed output, an
  unknown entity, exhausted caps, timeouts, HTTP errors, spend caps and lost responses were not
  induced against the real provider. Two failure paths did occur live:
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
* **The planned M2 pantry transfer suite (T01–T04) and a `pantry_dev03` variant** (alternate
  pool unavailable) are not authored; only pantry_dev01 and pantry_dev02 exist.
* **`planning_map.py` does not project the pantry fields** to planning artifacts yet.
* **Resource offers:**
  * An offer must cover the registered window to its end.
  * An offer for later makes the resource `expected` until a new offer confirms it.
  * A status or arrival record always outranks the owner's offer.
  * In `dev_fixture_01` nobody speaks for equipment, so every campus offer is refused.
* **Policy selection is held in memory.** After a server restart:
  * an episode whose last decision came from `live/*` keeps the live policy;
  * one without decisions reverts to `rules`;
  * a fresh `LivePolicy` instance starts its own model-call counter at 0, so one run could exceed
    the episode model cap by up to its instance cap before the host stops waking it.
* **`EventStateView` has no mode-label field.** The label travels on every stored decision and
  through `/api/policy` and `/api/moderator/policy`, so before an episode's first decision only
  those endpoints show it.
* **Role tabs act on their last poll.** A form sends the revision of the tab's last 1.5-second
  poll, so an action just after another change is rejected `REVISION_CONFLICT` and must be resent.
  This is correct behaviour, but there is no automatic refresh before sending.
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
* **Live decisions in a real browser session were not exercised.** The Wave 2 walkthrough
  selects the live agent but never runs it. Live decision cards are covered by web unit tests
  with live-shaped data and by replays of scripted-transport traces.
* **Python 3.11** is declared but not run; every check ran on CPython 3.12.11.

## Process disclosures

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
* **Concurrent workers.** The live runs were recorded after every worker of the wave had
  finished, from the working tree that the integrator then committed. The deterministic
  evidence was regenerated afterwards from a clean checkout of `fd04d48` (DECISIONS W2-D9).

## Wave 1 debt still open

* `AuthorizationRequest` has no stored open or answered state; the board still derives it.
* There is no in-place late start.
* Authentication failures are not persisted.
* Trace hashes are not signed.
* The boundary lint is a static guard.
