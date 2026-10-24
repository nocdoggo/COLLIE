# Known limitations

Separated as requested. Anything that is a required Wave 1 feature and missing is listed under
"Actual defects" or "Unverified acceptance criteria", never reclassified as optional.

## Deliberate Wave 1 scope

* **No LLM.** The coordinator is the documented deterministic rule policy `rules/1.0.0`. It
  accepts only the strict message forms in contract section 11 (`rules-parser/1.2.0`) and leaves
  all other wording unresolved. It is not a natural-language reasoner, and Wave 1 makes no claim
  of comparative policy performance.
* **Precision over recall in the rule policy.** A genuine supplier message in unsupported wording
  ("Order P17 was cancelled because the van broke down.") is not weighed as a claim. If it names
  a resource, the policy verifies it through the status source after its decision step, and acts
  on the typed answer. When the status service is also down, the policy does not hedge on such
  wording, so the dependent activities can fail where a looser parser would have booked the
  backup. This is the deliberate trade-off that makes false assertions impossible by construction.
  Wave 2's language interpretation is meant to recover this recall.
* **Verify-only checks cost coordinator time.** Each check of an unsupported, status-worded
  supplier notice takes the source's 2-minute latency, after the decision step. A long stream of
  such notices therefore uses more coordinator time than the earlier freshness skip did: 81
  projector queries against 51 over the six stream runs in the comparison (VERIFICATION.md,
  section 4). No case is lost by it.
* **Verify-only identification gaps.** An event-scoped notice prompts verification only if it
  names its resource and says something about delivery status. Two recall gaps were seen in the
  final reproduction run:
  * "Delivery for P17 is delayed by roughly 45 minutes." identifies nothing, because the order
    is not written as "order P17".
  * "The backup_projector is broken." identifies nothing, because "broken" is not a status
    word.

  Neither message causes a plan change, a hold or a spend.
* **One profile executed.** `campus_showcase` (fixture `dev_fixture_01`). The adapter accepts
  `community_skills_exchange`, but no runtime fixture for it is shipped (Wave 2, W2.2).
* **Development cases only.** dev01, dev02 and the focused variants dev04, dev05, dev06. They are
  not the held-out C01–C08 evaluation cases, and passing them says nothing about evaluation
  results.
* **Minimal participation.** Role tabs for the facilitator, presenter, host and organizer, with
  self check-in, free-text observations, preference presets and grant changes. The richer
  community experience is Wave 2.
* **Local only.** Everything is a local SQLite sandbox: no university booking, purchase,
  delivery, email or message.

## Unimplemented later-wave functionality (by design)

* Live LLM policy, provider adapter and caps (W2.1). The OpenRouter credential is stored but has
  not been exercised beyond a read-only key check (see WAVE_2_HANDOFF.md).
* Pantry adapter, stock ledger, `record_stock_receipt`, `record_distribution`, staff role (W2.3).
* MBTA adapter (W2.4, optional).
* Held-out evaluation (80 campus and 40 pantry episodes), the seven-minute deck, and rehearsals
  (Wave 3).
* Production authentication, multitenancy, hosting.

## Actual defects

Every confirmed or partial finding of the review rounds was fixed with a regression test, except
the accepted limitations below. The regression tests are in `tests/test_review_fixes.py`,
`tests/test_review_fixes_round3.py`, `tests/test_verify_only_end_to_end.py` and the audit-fix test
files; VERIFICATION.md section 3 gives the rounds and counts. The following were knowingly left as
they are:

* **`planner_policy-03` (accepted limitation).** The policy weighs notices by identity checks
  (order reference, date reference, source lineage, polarity, supersession), not by message age.
  A scenario-delivered reminder that names the current order and no date is treated as current
  and is hedged against when verification is unavailable.
* **Hold renewal near expiry.** If an organizer authorization arrives within the apply duration of
  a hold's expiry (one minute in the fixture), the rule policy does not renew the hold in time,
  and the option can be lost at the commitment cutoff. No shipped case hits this; the
  re-verification reproduced it only with altered hold lifetimes and latencies.
* **`web-2` (part).** Unresolved submissions and their idempotency keys live in tab memory. A
  reload loses the tab's "Check action status" control for them; the caller's own receipts still
  appear in Action history after reload.
* **Authentication failures are not persisted.** A missing, unknown, revoked or expired token,
  and a tool call made with a moderator session, are answered with 401 or 403 but not recorded,
  because there is no resolved actor and episode to attach them to. Every failure after the
  session is resolved is recorded, as an attempt or as a rejected receipt (contract section 5).

## Unverified acceptance criteria

* **Comprehension by a new viewer (product P1)** and usability with real participants were not
  tested with people. The browser walkthrough checks function, labels, keyboard operation and
  layout; it does not measure understanding.
* **Screen readers.** Semantic HTML, labels and an aria-live region exist, but no screen-reader
  session was run. Keyboard operation and visible focus were checked by automation.
* **Other browsers.** Only Chromium (Playwright 1.64.1, build 1248) was driven. Firefox and
  Safari were not run.
* **Python 3.11.** The app declares 3.11–3.12; all checks ran on CPython 3.12.11.

## Simplifying assumptions

* Whole-minute scenario time. One stored clock per episode, moved only by the moderator, the
  runner and tool durations.
* **No in-place late start.** An activity that is not ready at its scheduled start fails, and
  recovery has to happen before the start.
* One unit of each person/equipment resource per activity. Room occupancy (80 against a target of
  60) and one-at-a-time program exclusivity are checked separately. No travel and no multiple
  rooms.
* Booking terms are as in the fixture: a free provisional hold of at most 10 minutes, exposure
  equal to the booking cost, refundable release, and no cancellation of a committed booking. A
  plan that drops a committed resource keeps the commitment and its cost.
* Status sources answer from a declared observation model at request time. A hold is confirmed by
  the resource's steward (the same model). No noisy or adversarial sources beyond the shipped
  variants.
* Scripted exogenous actors (participant check-ins, the simulated organizer) exist only in
  headless runs and act through their own sessions. In the browser, people act. The simulated
  organizer answers each authorization request at most once.
* `pending` receipt lookup is reserved: the receipt and idempotency record commit atomically, so
  a lookup sees `found` or `not_found`.
* Policy memory lives in the policy instance. After a server restart, a new instance re-derives
  state from public records (decision ids are store-assigned, so they cannot collide).
* The event timezone is fixed to America/New_York by the fixture contract.

## Operational and evaluation limitations

* **Single process, single SQLite file.** All writes serialize through `BEGIN IMMEDIATE`, which
  suits a demo and would not suit production load. Moderator `run` requests block their HTTP
  request until the simulated minutes finish (an 80-minute run takes a few seconds).
* **Trace hashes are not signed.** The integrity block is plain SHA-256 over the trace's own
  canonical JSON. It detects corruption and accidental edits, not deliberate ones: someone who
  edits a trace can recompute every hash, and both verifiers will then accept it. The replay says
  so, and it marks the board when a check fails. Signing exports (for example HMAC or Ed25519
  with a server-held key) is not part of Wave 1.
* **Tool budget per policy run, not per episode.** `max_tool_calls` (16) bounds one policy run.
  A run that exhausts it is woken again on the next tick with a fresh budget. The rule baseline
  therefore uses more than 16 calls per episode in every development case (VERIFICATION.md lists
  the counts). The planned per-episode caps (8 model calls, 16 tool calls) are Wave 2 work, and
  must apply to the rule policy as well, so that comparisons are fair.
* **The boundary lint is a static guard, not a sandbox.** `web/scripts/check-boundaries.mjs`
  parses every source with the TypeScript compiler and refuses the plain ways a read-only module
  could reach the network, storage or a tool call. Deliberately obfuscated code can still pass it,
  for example:
  * an aliased global object or prototype;
  * `Reflect.get` with a computed name;
  * a mutator called through `.call` or a variable;
  * code strings handed to `setTimeout`;
  * names assembled at run time.

  These are listed in the lint header and `web/README.md` and pinned by `KNOWN_EVASIONS` tests.
  The enforcement is at run time: the walkthrough records every non-GET request from the replay,
  and `test_replay_endpoints_perform_no_writes` checks the server. Read-only modules also may not
  write globals, so navigation or title code belongs in a trusted module.
* **Traces are 2–3 MB each.** Each revision stores a full public snapshot. Evaluations are stored
  once per trace and referenced from frames.
* **Moderator code.** Generated into `var/moderator_code.txt` (0600) or taken from
  `PLAN_B_MODERATOR_CODE`. It is a local demo control, not authentication.
* **Join codes appear in URLs** (`#/join/<code>`). They are one-time and expire after 10 minutes;
  the tab removes the code from the URL after exchanging it.
* **Session tokens in `sessionStorage`.** This is acceptable for a local sandbox, but a hosted
  deployment would need hardening.
* **Starlette deprecation warning.** The Starlette test client warns that `httpx` will be replaced
  by `httpx2`. This affects tests only.
