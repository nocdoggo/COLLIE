# APIs, credentials, and access

Status: planning and local credential setup, October 23, 2026. The Plan B application and its adapters are not implemented by these documents.

## What the team needs now

The only mandatory external service for the live agent build is one usable language-model endpoint. The repository already describes provider clients and a non-secret [model registry](../docs/module06_model_registry.json). Reuse an existing authorized endpoint if it passes the Wave 2 contract checks. The registry's recorded model names and retrieval dates do not establish current availability. No paid model calls were made for this plan update.

The MBTA credential has been supplied and stored. No additional transit key is needed now. A pantry API, university booking API, email account, map service, or institutional database is required for neither the campus sandbox nor the fictional pantry demonstration.

| Dependency | Current state | Needed by | Team action |
| --- | --- | --- | --- |
| Language model | Existing provider patterns and registry, current endpoint not smoke-tested for this app | Wave 2 live agent gate | Select one existing endpoint, model identifier and allowed spend. If it is unavailable, provide a key file and endpoint configuration locally |
| MBTA V3 | Credential stored, header-authenticated request returned HTTP 200 | Optional Wave 2 transit adapter | No new key request. Choose the route/stop relevance configuration during implementation |
| Local state and UI | Proposed Python API, SQLite store and browser UI | Wave 1 | Install app dependencies and use synthetic fixtures |
| U-ACCESS or pantry operator | No confirmed participant or partner | Workflow validation, optional pilot | Arrange a short operator walkthrough if practical. An interview is more useful than requesting a production API prematurely |
| Pantry records | Synthetic quantities supplied in the development fixture | Wave 2 | No external data needed. For a later pilot, obtain an authorized aggregate inventory export with units and timestamps |
| Campus room reservations | Public rules only, no write access | Outside the three-wave sandbox | No booking credentials needed |
| Canvas submission and hosting | Requirements and deployment target to confirm | Wave 3 packaging | Check submission format and whether a local demo, video, or hosted link is required |

Provider selection does not require training, fine-tuning, a second model provider, or an agent framework subscription. The initial loop needs reliable structured outputs and bounded tool selection. Use the same model configuration across matched policy comparisons and record the actual returned model identifier.

## Local credential storage

- MBTA file: `.local/keys/mbta.key`, relative to repository root.
- Directory permissions: `0700`. Key file permissions: `0600`.
- Explicit root Git ignore entry: `/.local/keys/`.
- Existing repository-wide `*.key` ignore remains in place.
- The file contains the supplied value with a trailing newline. The value is omitted from all planning artifacts.

Git ignore prevents ordinary addition of an untracked file. It is not encryption and does not protect a deliberately force-added file. The current key was checked as ignored and absent from the Git index. Future release packaging must use an allowlist that excludes this directory.

Suggested **future** backend configuration, with no secret values in the environment template:

```dotenv
PLAN_B_MBTA_KEY_FILE=.local/keys/mbta.key
PLAN_B_MBTA_BASE_URL=https://api-v3.mbta.com
PLAN_B_TRANSIT_MODE=fixture
PLAN_B_MODEL_KEY_FILE=.local/keys/model.key
PLAN_B_MODEL_BASE_URL=
PLAN_B_MODEL_ID=
PLAN_B_MODEL_MAX_RUN_COST_USD=
```

These names are a proposed configuration contract, not variables already consumed by application code. Resolve relative paths from a declared repository/configuration root. A deployed backend should use a mounted secret or the host's secret store with equivalent access controls. Never include the key in browser code, public environment variables, URLs, replay artifacts, screenshots, or HTTP logs. Read it on the server and send it in the `x-api-key` header to the configured MBTA host.

If an existing provider key is reused from `cloud_endpoint/`, reference its authorized local path rather than duplicating it. The user need only identify the chosen provider/model and budget if that access already works. Missing credentials can be saved directly to an ignored local key file.

## What was actually verified

On October 23, 2026, a single read-only request to `https://api-v3.mbta.com/routes/Red` used the stored credential in the `x-api-key` header and returned HTTP 200, a `route` resource, and ID `Red`. Only status and resource metadata were printed.

This confirms that the intended endpoint accepted the request using that header at the time of the probe. The endpoint also permits some keyless access, so the response alone does not establish the credential's account identity, assigned quota, or validity for every API operation. It does not test alerts, predictions, app integration, sustained rate limits, or stage-day connectivity. The [MBTA developer portal](https://api-v3.mbta.com/) describes schedules, real-time information, alerts, and key management. The [official API documentation](https://api-v3.mbta.com/docs/swagger/index.html) is the implementation reference.

## MBTA adapter: useful context with a narrow scope

Use a read-only transit adapter behind `query_status`, with an allowlisted route/stop configured for a fictional volunteer role. Begin with route alerts. Add stop predictions only if the demonstration needs them and the source timestamps and direction are correctly represented. Route `Red` was used only for the access probe. It does not identify an actual participant journey.

Example interaction:

1. A volunteer says their arrival might be affected by transit.
2. The agent reads relevant public route information and shows its observation time and affected interval.
3. The agent requests or reads the volunteer's own availability update through the participant workflow.
4. The deterministic planner checks whether an already registered on-site substitute can cover the activity. An authorized hold or schedule change modifies the local sandbox.

An alert does not establish the volunteer's location, lateness, medical needs, or a donor shipment's ETA. A route prediction is a transit vehicle prediction, not a door-to-door arrival prediction. Do not infer a walking route, transfer time, or connection with a private donation vehicle. MBTA can enrich either demo but is unnecessary to the pantry handoff fixture, which uses two stocks at the same fictional venue.

### Proposed observation contract

Persist source provider, endpoint kind, route and optional stop/direction, source record ID, source update time when provided, retrieval time, active period, public text, normalized relevant effect, and provenance link. Preserve unknown timestamps rather than substituting retrieval time for source observation time. Deduplicate provider record/revision combinations.

Read failures retain `unavailable` or `unknown`. They must not become a synthetic all-clear. A successful response with no alerts means no matching alerts were returned, not that a person will arrive on time. Cache by query scope, retain source freshness, and observe provider response headers. Use bounded backoff for 429/5xx responses, no browser polling per user, and a documented request budget. Do not hard-code an unverified quota into the plan.

### Clock and replay rules

The November development fixtures use a simulated event clock. October live transit conditions cannot be silently inserted into those scenarios as if contemporaneous. Provide two explicit modes:

- `fixture`: recorded or synthetic observations whose timestamps belong to the scenario clock. Label their origin and any time transformation. Use this mode for reproducible experiments and the stage fallback.
- `live`: current wall-clock public context in a separate current-time demonstration. Label fetch time and keep it outside the frozen scenario comparison.

A displayed live feed can demonstrate connectivity without driving the frozen event episode. To let it affect decisions, create an event whose operating time and relevance configuration actually match that live feed. Never retimestamp a live alert silently to make it fit an authored disruption.

### Adapter acceptance checks

Verify relevant and irrelevant route notices, inactive periods, duplicate updates, missing fields, source staleness, empty responses, network timeout, HTTP 429, and malformed responses. Verify credentials are absent from browser assets, tool observations, logs, and exported episodes. The agent cannot choose arbitrary request hosts or header names. One successful access probe is not a substitute for these checks.

## Pantry and community access

The official [U-ACCESS page](https://www.umb.edu/campus-life/current-students/u-access/) links its client workflow. The project has no established authorization to read that system, and the existence of a PantrySoft link does not imply an available public API.

For the planned demo, use authored stock counts, standardized kits, aliases, and staff role tokens. All physical receipt and distribution records are explicitly simulated staff actions. For an eventual operator-approved pilot, begin with a minimal aggregate import:

| Field | Purpose |
| --- | --- |
| `resource_id`, `unit` | Identify a registered stock and its counting unit |
| `on_hand_quantity`, `reserved_quantity` | Confirm usable stock and existing commitments |
| `expected_quantity`, shipment reference | Separate promised supply from received supply |
| `as_of`, source reference | Establish freshness and audit origin |
| Service target, deadline, volunteer availability | Define the operator's session goal and feasible staffing |

Do not import recipient names, eligibility records, household histories, addresses, or payment details for this task. Inventory exports alone do not establish the authority to redistribute stock. The staff member who controls a stock must define permitted holds, handoffs, and service-recording actions.

No contact has been made with staff, volunteers, or service providers as part of this planning work. Any later outreach and institutional integration require their own task authorization. This does not block the synthetic implementation.

## Dependency order

Wave 1 requires no external credentials. Wave 2 requires the selected LLM endpoint only for live agent behavior, and uses the already supplied MBTA credential if the optional adapter is built. The pantry adapter uses fictional local state. Wave 3 requires the same model access for fresh evaluation runs and a known presentation/submission format. Optional integrations must not delay the two completed sandbox workflows or their evaluation.
