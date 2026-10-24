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
npm test            # replay integrity, boundary lint, helper and component tests (node --test)
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
- An applied receipt that changed nothing (`revision_after == revision_before` and no
  `state_changes`, as for a duplicate observation) reads "Applied, no change (duplicate)" in the
  live announcement, the submission status, the change feed and the Action history, never
  "applied and confirmed in state revision N".
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
- A join link shows only the first 4 characters of its one-time code ("Join link for
  participant_presenter (code P9Ne…)"); the full code is only in the link's `href`. Each link
  carries `data-join-link="<principal id>"`, the selector for tests and screenshot masks.
- Replay recomputes `frame_hashes`, `chain_sha256` and `content_sha256` in the browser with
  SubtleCrypto, using a Python-exact canonical JSON (`src/replay/integrity.ts`). It also checks
  that `integrity.algorithm` is `sha256`, `kind` is `plan_b_sanitized_trace`, `trace_version` is
  `1.0.0`, and that the last frame's state revision equals `final_state.revision`. These are the
  same checks as `plan-b verify-trace`.
- Both verifiers read the trace's exact bytes. The browser decodes them itself (`TextDecoder`
  with `fatal: true, ignoreBOM: true`) for server and local-file traces alike, because
  `response.text()` and `Blob.text()` silently drop a byte order mark. Both reject, as a
  reported problem: a UTF-8 byte order mark, bytes that are not UTF-8, a string with a lone
  UTF-16 surrogate (not well-formed Unicode), nesting deeper than 256 levels, and an integer
  longer than 4300 digits. A file with a byte order mark or invalid UTF-8 is refused when it
  is loaded and never renders. Both also reject an `integrity.frame_hashes` that is missing or
  not a list, even in a trace with no frames (the exporter writes an empty list). The vectors'
  `trace_cases` run through both verifiers from the same bytes, so the two accept and reject
  the same traces.
- The hashes are not signed. "Integrity check passed" means the trace is consistent with its own
  hashes: the check detects corruption, not deliberate edits, because whoever edits a trace can
  recompute them. A failed check says which kind of check failed: "not consistent with its own
  hashes", or "fails a structural check: <names>" (algorithm label, kind, trace version,
  final-state revision against the last frame) when every hash matches. The sticky replay
  banner shows the state (checking, passed, failed, not checked). If the verifier itself throws
  or rejects, the trace is reported as failed ("The trace could not be checked: ..."), so the
  banner never stays at checking. A trace that fails keeps its board viewable, but outlined,
  dimmed and headed by "Integrity check failed: the values below may not be what was recorded."
- A trace the replay cannot render never blanks the page. The parts that render trace data (the
  "Loaded ..." summary, the frame controls and the board) sit inside an error boundary. If one
  throws, as the synthetic vector traces do, the banner shows the integrity check as failed
  whatever the hashes say, and a notice "This trace could not be rendered." with the error takes
  the board's place. The Trace card keeps the hash checks, and another trace can be opened. A
  frame state without `latest_evaluation`, with a non-object there, or with an `evaluation_ref`
  that is not an own key of `evaluations` shows no evaluation.

## Boundary lint

`npm run lint` runs `scripts/check-boundaries.mjs`. It is a static guard against *accidental*
use of the network, storage or mutating code from the read-only replay and board, not a
sandbox. The enforcement is at run time: the browser walkthrough fails on any non-GET request
the replay page sends, and `test_replay_endpoints_perform_no_writes` checks that the replay
endpoints write nothing. The lint reads the files under `src` (and `dist/` for the
private-vocabulary check) and nothing else: `index.html`, `vite.config.ts`, `package.json` and
`tsconfig.json` are build configuration, trusted and reviewed by hand. Code written to evade
the lint still can. These are the known evasions, and `tests/boundaries.test.ts` checks that
each one still passes, so this list stays accurate:

- an aliased global object or prototype, such as the round-1 case
  `const g = globalThis as unknown as Record<...>; g["fe" + "tch"](...)` or
  `const p = Object.prototype; p.body = ...`, or one passed through a function, an array or an
  object (`[window][0][k]`, `e.view[k]`);
- `Reflect.get(window, name)`, or any helper handed a global object, with a computed name;
- a mutator (`defineProperty`, `assign`, `set`, ...) called other than by its own name:
  through `.call` (`Object.defineProperty.call(null, Object.prototype, ...)`), held in a
  variable of another name (`const dp = Object.defineProperty; dp(Object.prototype, ...)`), or
  through `Reflect.apply(Object.defineProperty, null, [Object.prototype, ...])`;
- a name assembled from strings outside an index on a global object, `navigator` or `document`;
- a string of code handed to `setTimeout` or `setInterval`;
- the Function constructor reached through a variable or one of its methods
  (`const F = f.constructor; F("...")`, `f.constructor.call(0, "...")`,
  `new f.constructor("...")`, `Reflect.construct(f.constructor, [...])`);
- a tag name or `javascript:` URL built at run time (`"fo" + "rm"`, a value read from a trace);
- a global name (`top`, `parent`, `frames`, `navigator`, `document`, `Object`, ...) in a module
  that declares a binding of that name anywhere, an ambient `declare const navigator` or a
  parameter named `document` included: the lint then reads every use of the name in that module
  as the local binding;
- web APIs the rules below do not name (`document.write`, `DOMParser`, `WebTransport`,
  `window.open`, `location.assign` of a same-origin `blob:` HTML document, ...).

The replay loader does not depend on the prototype rules: its fetch options have no prototype,
so no key that any module puts on `Object.prototype` reaches its requests (see below).

The lint parses every source with the TypeScript compiler API and inspects the syntax tree.
Comments are not inspected (the private-vocabulary check aside), so a comment that names an API
is fine. Names are compared after the parser decodes them, so `\u0066etch` and `"\u0066etch"`
count as `fetch`, and a JSX attribute string has its numeric character references (`&#111;`)
decoded. Type positions (annotations, interfaces, type aliases, `import type`) are skipped
because the build erases them.

The sources are every script file under `src`: `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`,
`.mjs` and `.cjs`, the extension compared ignoring case (`net.JS` is a source, and Vite bundles
it as JavaScript). Every source's module references are resolved: import declarations,
`export ... from`, `import x = require(...)`, dynamic `import()` and
`new URL("...", import.meta.url)`. A relative or `/src/...` specifier names every file it could
resolve to, and each one is checked: the file itself, the `.ts` counterpart of a `.js` name, the
specifier with each of Vite's extensions (`.mjs`, `.js`, `.mts`, `.ts`, `.jsx`, `.tsx`, `.json`)
added, and a directory's index files. A `?query` or `#hash` suffix is kept apart. A script file
is followed; an allowed asset or style file (below) is a leaf, neither followed nor scanned.
Bare package specifiers (`react`) resolve into `web/node_modules` and are not followed. A
read-only module is every source under `src/replay`, `src/board` and `src/components`,
`src/format.ts`, `src/types.ts`, and every script module those reach.

Every module a source references must lie under `src`, so the rules below read every module the
bundle takes from there. A module outside `src` fails at the import, whichever source imports
it and whatever it contains (`import "../../shared/net.js"`, `import "/vite.config.ts"`).

Below, the value of an expression looks through parentheses, `!`, `as`, `satisfies` and `<T>`,
reads `(0, x)` as `x`, and includes either operand of `a || b`, `a && b` and `a ?? b`, either
branch of `c ? a : b`, and the right side of `x = y`. A member is `.name` or a literal key
`["name"]`. A global object is `globalThis`, `window`, `self`, a bare `top`, `parent` or `frames`,
`document.defaultView`, or such a member of a global object (`window["top"]`,
`globalThis.window`). A global binding is an identifier the module does not declare (`Object`,
`document`, `location`). The lint fails in these cases:

- A read-only module reaches `src/api.ts`, `src/panels` or `src/views`, even indirectly.
  `import type` and `export type` are not followed; `import { type X }` is, because
  `verbatimModuleSyntax` keeps it as a side-effect import.
- A read-only module uses, as an identifier, a property name, a JSX attribute or a string
  literal that spells exactly the name: `fetch`, `XMLHttpRequest`, `sendBeacon`, `WebSocket`,
  `EventSource`, `RTCPeerConnection`, `Request` (so no `new Request`, `const R = Request` or
  `Reflect.construct(Request, ...)`), `sessionStorage`, `indexedDB`, `caches`, `cookie`,
  `cookieStore`, `serviceWorker`, `Worker`, `SharedWorker`, `eval`, `Function`, `innerHTML`,
  `outerHTML`, `insertAdjacentHTML`, `ping`, `__proto__`, `__defineGetter__`,
  `__defineSetter__`, `__lookupGetter__` or `__lookupSetter__`.
- A read-only module uses a string that is exactly `form`, `iframe` or `script` in any case (so
  no `as="form"`, `const Tag = "iframe"` or `createElement("SCRIPT")`); renders a `<form>`,
  `<iframe>` or `<script>` in JSX; calls `document.createElement` with a computed tag; uses a
  `javascript:` URL string; indexes with a computed key, or destructures a computed key from
  (`const { [k]: f } = globalThis`), a global object, `navigator` or `document` (a bare one, a
  member of a global object, or any `x.ownerDocument`), so `(globalThis || 0)[k]`,
  `document["defaultView"][k]` and `el.ownerDocument[k]` fail too; reaches the Function constructor through `.constructor.constructor` or the `.constructor`
  of a function or class expression, or calls any `x.constructor(...)`; uses `import.meta` other
  than `import.meta.env` and `import.meta.url` (so no `import.meta.glob`); or imports a module
  with a Vite `?worker` suffix.
- A read-only module changes a shared object. It writes (assigns with any operator, `++`, `--`,
  `delete`, or a destructuring or `for-in`/`for-of` target) `X.prototype` for any `X`, or a
  member of a prototype (`X.prototype`, `Object.getPrototypeOf(...)`), of a global object, of a
  global binding (`Object.freeze = ...`, `document.title = ...`) or of a member of a global
  object (`window.Object.freeze = ...`), or assigns a global binding itself (`name = ...`). Or it
  calls `defineProperty`, `defineProperties`, `setPrototypeOf`, `assign`, `set` or
  `deleteProperty` (on `Object`, `Reflect` or any other receiver) with one of those as the first
  argument, as in `Object.defineProperty(Object.prototype, "body", ...)`.
- **Read-only modules may not write globals, by design.** This rule fails closed: a replay,
  board or component module writes no global at all, so ordinary navigation or title code such
  as `location.hash = "#/replay/" + name` or `document.title = "Replay"` fails the lint there,
  and so does a global object as the first argument of any `set` or `assign`, even on the
  module's own map (`new WeakMap().set(window, 1)`). Navigation and title code belongs in a
  trusted module: `src/App.tsx` owns the route and passes it down as a prop (ReplayView's
  `initialName`). A read-only module navigates with a plain `<a href="#/...">` link (as
  ReplayView's "Leave replay" does) or a callback a trusted module gives it.
- The one exception is `fetch` in `src/replay/loader.ts`. There every `fetch` must be the
  callee of a direct call `fetch(url, OPTIONS)` with two arguments, `OPTIONS` an identifier the
  loader declares once, as a top-level
  `const OPTIONS = Object.freeze(Object.assign(Object.create(null), { ... }))` built with the
  real `Object`. The browser reads every RequestInit key from the options, inherited ones
  included, in lexicographic order, so a `body` getter on `Object.prototype` could rewrite
  `method` before it is read, and an inherited `headers` would be sent. Options with no
  prototype have only their own keys, and frozen, none can be added or changed. The `{ ... }`
  literal's keys must be plain identifiers or strings (no computed key, no spread, no method or
  accessor), each one of `method`, `credentials`, `cache`, `signal`, `redirect`, `mode`,
  `referrer`, `referrerPolicy`, `integrity` and `priority`, so there are no `headers`, no `body`
  and no `__proto__`. It must state `method` as a string literal equal to `"GET"` ignoring case
  (`"GET" + x` fails): the options' method overrides that of a `Request` passed as the URL, and a
  GET with a body is a TypeError, so a `Request` input cannot turn the call into a POST. It must
  set `credentials: "omit"`. The loader's options are `{method: "GET", cache: "no-store",
  credentials: "omit"}`.
- Any source, a `.js` or `.mjs` one included, has a dynamic `import()` whose argument is not one
  quoted string literal, a `new URL(..., import.meta.url)` whose path is not a quoted string,
  or a use of `import.meta.glob`.
- Any source imports, re-exports or dynamically imports a URL specifier: one that starts with a
  scheme (`data:`, `blob:`, `http:`, `https:`, `file:`, ...) or with `//`. Vite would inline a
  `data:` module's code into the bundle and keep a remote import, and neither can be followed.
- Any source references a file outside `src`, as above.
- Any source references a file that is neither a script nor an allowed asset or style file. The
  allowed extensions are `.css`, `.json`, `.svg`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`,
  `.avif`, `.ico`, `.woff`, `.woff2`, `.ttf`, `.otf` and `.txt`, in lower case exactly, imported
  with no suffix or with `?url` or `?raw`. So an extensionless file, a `.md` file, an upper-case
  `x.CSS` or `x.JSON` (Vite bundles each of these as JavaScript) and an asset with `?worker`,
  `?inline` or any other suffix (with `?worker` Vite runs even a CSS file as a worker) all fail.
- Any source imports a directory that holds a `package.json` (Vite would load the entry that
  file names, not the index file), or a package specifier that starts with `#` or holds a `.` or
  `..` segment (`pkg/../../shared/x.js` climbs out of `node_modules`).
- `src` holds a symbolic link (Vite resolves it to the file it points to, wherever that is), a
  `node_modules` folder (a package specifier would resolve into it), a `package.json` (Vite
  applies its `browser` field to the imports of the files beside it), or a `tsconfig*.json` or
  `jsconfig*.json` (esbuild applies its compiler options, such as `jsxImportSource`, there).
- Any source holds a JSX pragma comment (`@jsx`, `@jsxFrag`, `@jsxImportSource`,
  `@jsxRuntime`), which changes what esbuild emits for every element in the file. An
  instantiation expression `(expr)<T>` is read like `expr`; it is not type syntax.
- Any source uses `dangerouslySetInnerHTML` or `localStorage`.
- A source outside `src/api.ts` sets an authorization header: an `Authorization` object key or
  assigned property, an `"authorization"` string in any case, or a string starting `Bearer `.
- Private runner vocabulary appears in the raw text of any file under `src` (a JSON or text
  file included) or of `dist/` (this check is textual on purpose, comments included).
- A source does not parse.

`tests/boundaries.test.ts` copies `src/` to a temporary directory. For each case it plants one
violation and asserts that the lint reports it. The cases include every bypass found in the
round-1 review (no-space and multi-line imports, quotes or semicolons in comments, string-named
imports, `import.meta.glob`, workers, DOM-created forms, `<a ping>`, unicode escapes, computed
keys on the global object and in the loader's options; for B16, the form without the alias),
and every round-2 bypass with a syntax rule (computed keys on `top`, `parent`, `frames`,
`document.defaultView` and `navigator`, computed destructuring, a function's `.constructor`,
aliased and polymorphic `form` and `iframe` tags, `data:` and `https:` imports, the loader's
`Request` input and `__proto__` key, `javascript:` URLs, `innerHTML`, `document.cookie`,
`caches`, `RTCPeerConnection` and `serviceWorker`), and every round-3 bypass (a getter defined on
`Object.prototype` in the loader or in a component, the other prototype and global-object
writes, `.js`, `.mjs`, `.cjs` and `.jsx` sources, literal-key and logical aliases of the global
object, and the loader's options with a prototype or not frozen), and every round-4 bypass
(modules outside `src` reached from the board or a panel, by import, re-export, dynamic
import, `require`, root-absolute specifier, `new URL(..., import.meta.url)`, a symbolic link,
`import.meta.glob`, `..` in a package specifier or a `node_modules` folder; upper-case `.JS`,
extensionless, `.md`, upper-case `.CSS` and `.JSON` files; `?worker` and `?inline` on assets;
`el.ownerDocument[k]`).
It pins the fail-closed writes to globals (`location.hash`, `document.title`,
`m.set(window, ...)`) as failures. It also asserts that the unmodified copy passes, that
comments, CSS and JSON imports, assets with `?url` and `?raw`, package subpaths, reads of
prototypes and globals and the allowed loader forms pass, and that the known evasions above
still pass.
