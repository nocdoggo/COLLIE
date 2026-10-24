# Plan B web board and replay

Browser app for the fictional campus sandbox: the live board (W1.5) and the recorded replay
(W1.6). React 18 + TypeScript (strict) + Vite, plain CSS, no external fonts or CDNs, so it
works offline. The bundle contains no credentials. Each tab keeps its own bearer token in
`sessionStorage` (`planb.session`).

## Commands

Run these from `apps/plan_b/web` with Node 22.18 or newer.

```sh
npm ci              # install the exact versions in package-lock.json
npm run dev         # http://127.0.0.1:5173, proxies /api to http://127.0.0.1:8765
npm run build       # tsc -b && vite build -> dist/ (the Plan B server serves it at /)
npm run typecheck   # tsc --noEmit -p .
npm run lint        # boundary checks (below)
npm test            # replay integrity, helper and component tests (node --test)
```

`npm test` loads `tests/support/register.mjs`, a test-only hook that transpiles the `.ts`/`.tsx`
sources with the project's TypeScript, so components render with `react-dom/server` in Node.

The canonical-JSON test vectors come from the server's own `plan_b.domain.digest`. To
regenerate them, run `uv run python web/tests/make_vectors.py` from `apps/plan_b`.

## Routes

| Hash | View |
| --- | --- |
| `#/` | Sign-in (moderator code or join code), then the board for the signed-in role |
| `#/join/<code>` | Exchanges a one-time join code for a session, then opens the board |
| `#/replay`, `#/replay/<name>` | Recorded replay of a sanitized trace (server list or local file) |

## Rules the code keeps

- Success appears only when a receipt with status `applied` is present in a fresh state read.
  A click, a policy decision or an envelope by itself never counts as success: until that read,
  an applied receipt shows a neutral "Applied — confirming in a fresh state read".
- Each logical submission gets one idempotency key, and retries reuse the identical request. A
  lost response shows "Checking whether this was recorded". The "Check action status" control
  then calls `get_action_receipt` with the original key. The app never resends with a fresh key.
- Every observation carries a `client_record_id` fixed in its request. While an earlier update's
  outcome is unknown, the form says so and sends nothing new until it is checked or no longer
  tracked; an identical update typed again keeps the earlier record id, so the server stores it
  once.
- A passed planner check is a "Confirmed" fact only when no candidate assumption backs it;
  otherwise it "Passes under assumption" and names the assumption. A stale evaluation never
  offers "Can be applied now".
- "Checked in" means the latest check-in's availability covers the slot (or, with no slot left,
  the clock). A chosen "Available until" time that has passed blocks the check-in with an
  explanation instead of being dropped.
- Loading a case asks for confirmation whenever an episode might be active, including when the
  current-episode read failed. Moderator results are stamped with the action and the scenario
  time it ran. A 401 `EPISODE_CLOSED` tells the tab its episode was reset.
- Scenario times are formatted in the event timezone from the state view, never in the
  browser's local timezone.
- Replay recomputes `frame_hashes`, `chain_sha256` and `content_sha256` in the browser with
  SubtleCrypto, using a Python-exact canonical JSON (`src/replay/integrity.ts`).
- `npm run lint` fails in these cases:
  - `src/replay`, `src/board` or `src/components` imports, even indirectly, `src/api.ts`,
    `src/panels` or `src/views`. Replay renders the same board but cannot reach a tool call.
  - Any source uses `dangerouslySetInnerHTML` or `localStorage`.
  - A source outside `src/api.ts` sets an authorization header.
  - Private runner vocabulary appears in the sources or in `dist/`.
