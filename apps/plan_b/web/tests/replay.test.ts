// Recorded replay presentation (review WEB-2): what the integrity panel claims, the integrity
// state in the sticky banner, and the marked board of a trace that failed its check; a verifier
// that throws is a failed check; the loader decodes a trace's exact bytes, and its fetch options
// have no prototype (round-3 V1); a trace the board cannot render shows a notice and a failed
// banner, never a blank page (round-3 regression).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { BoardView } from "../src/board/BoardView.tsx";
import { NOT_CHECKED_PREFIX, checkTraceIntegrity, integrityState, verifyTraceText } from "../src/replay/integrity.ts";
import type { IntegrityReport } from "../src/replay/integrity.ts";
import { listReplays, loadLocalReplay, loadServerReplay } from "../src/replay/loader.ts";
import {
  IntegrityPanel,
  ReplayBanner,
  ReplayBoardFrame,
  ReplayRenderGuard,
  UNRENDERABLE_NOTICE,
  UNSIGNED_NOTE,
  UNTRUSTED_BOARD_NOTICE,
  UnrenderableNotice,
  integrityHeadline,
  rehydrateState,
  renderFailureReport,
} from "../src/replay/ReplayView.tsx";
import type { CompactedStateView, SanitizedTrace } from "../src/types.ts";
import { makeCandidate, makeEvaluation, makeView, textOf } from "./support/view.ts";

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/canonical_vectors.json", import.meta.url), "utf-8"),
) as { trace_text: string; tampered_trace_text: string; trace_cases: { name: string; text: string }[] };

const caseText = (name: string): string => {
  const found = fixture.trace_cases.find((c) => c.name === name);
  assert.ok(found !== undefined, name);
  return found.text;
};

async function checked(text: string): Promise<Extract<IntegrityReport, { status: "checked" }>> {
  const report = await verifyTraceText(text);
  assert.equal(report.status, "checked");
  if (report.status !== "checked") throw new Error("unreachable");
  return report;
}

const passed = (): Promise<IntegrityReport> => verifyTraceText(fixture.trace_text);
const failed = (): Promise<IntegrityReport> => verifyTraceText(fixture.tampered_trace_text);
const MALFORMED: IntegrityReport = { status: "malformed", reason: "The trace has no frames array." };
const UNAVAILABLE: IntegrityReport = { status: "unavailable", reason: "No SubtleCrypto." };

const panelText = (report: IntegrityReport | "checking") =>
  textOf(renderToStaticMarkup(createElement(IntegrityPanel, { report })));

const banner = (integrity: IntegrityReport | "checking" | null) =>
  renderToStaticMarkup(createElement(ReplayBanner, { integrity }));

function frame(isFailed: boolean): string {
  return renderToStaticMarkup(
    createElement(ReplayBoardFrame, {
      failed: isFailed,
      children: createElement(BoardView, { view: makeView(), mode: "replay" }),
    }),
  );
}

test("a passing check says the trace matches its own unsigned hashes, not that it is authentic", async () => {
  const text = panelText(await passed());
  assert.ok(text.includes("Integrity check passed."), text);
  assert.ok(text.includes("The trace is consistent with its own hashes"), text);
  assert.ok(text.includes("The hashes are not signed"), text);
  assert.ok(text.includes("detects corruption, not deliberate edits"), text);
  assert.ok(text.includes(UNSIGNED_NOTE), text);
  assert.ok(text.includes("✓ Kind: plan_b_sanitized_trace"), text);
  assert.ok(text.includes("✓ Final state revision 5 matches the last frame's (5)"), text);
});

test("a failing check says the board's values may not be what was recorded", async () => {
  const text = panelText(await failed());
  assert.ok(text.includes("Integrity check failed."), text);
  assert.ok(text.includes("The trace is not consistent with its own hashes"), text);
  assert.ok(text.includes("may not be what was recorded"), text);
  assert.ok(text.includes("mismatched frames: 1"), text);
  assert.ok(text.includes(UNSIGNED_NOTE), text);
  assert.ok(panelText(MALFORMED).includes("may not be what was recorded"));
});

test("each report maps to one banner state", async () => {
  assert.equal(integrityState("checking"), "checking");
  assert.equal(integrityState(await passed()), "passed");
  assert.equal(integrityState(await failed()), "failed");
  assert.equal(integrityState(MALFORMED), "failed");
  assert.equal(integrityState(UNAVAILABLE), "not_checked");
});

test("the sticky banner shows the integrity state once a trace is loaded", async () => {
  const none = banner(null);
  assert.ok(!none.includes("data-integrity"), none);
  assert.ok(textOf(none).includes("Recorded replay"));

  const checking = banner("checking");
  assert.ok(checking.includes('data-integrity="checking"'), checking);
  assert.ok(textOf(checking).includes("⧗ Integrity: checking…"), textOf(checking));

  const ok = banner(await passed());
  assert.ok(ok.includes('data-integrity="passed"'), ok);
  assert.ok(textOf(ok).includes("✔ Integrity check passed (hashes not signed)"), textOf(ok));

  for (const report of [await failed(), MALFORMED]) {
    const bad = banner(report);
    assert.ok(bad.includes('data-integrity="failed"'), bad);
    assert.ok(bad.includes("badge tone-bad"), bad);
    assert.ok(textOf(bad).includes("✖ Integrity check failed: values may not be what was recorded"), textOf(bad));
  }

  assert.ok(textOf(banner(UNAVAILABLE)).includes("? Integrity not checked"));
  // The banner is the sticky element; its state must sit inside it, not only in the Trace card.
  assert.match(ok, /^<div class="replay-banner" role="status">/);
});

test("a board that failed its check is marked but still rendered", () => {
  const marked = frame(true);
  assert.ok(marked.startsWith('<div class="board-untrusted" data-integrity="failed">'), marked.slice(0, 120));
  const text = textOf(marked);
  assert.ok(text.startsWith(`✖ ${UNTRUSTED_BOARD_NOTICE}`), text.slice(0, 160));
  assert.equal(UNTRUSTED_BOARD_NOTICE, "Integrity check failed: the values below may not be what was recorded.");
  // The board itself is still there to inspect.
  assert.ok(text.includes("Action history"), text);
  assert.ok(text.includes("Event budget"), text);

  const plain = frame(false);
  assert.ok(!plain.includes("board-untrusted"));
  assert.ok(!textOf(plain).includes(UNTRUSTED_BOARD_NOTICE));
  assert.ok(textOf(plain).includes("Action history"));
});

// ------------------------------------------------------------------ item 3: the headline

test("a hash mismatch and a structural failure read differently", async () => {
  // Hashes only: the edited frame.
  const hashOnly = integrityHeadline(await checked(fixture.tampered_trace_text));
  assert.ok(hashOnly.startsWith("The trace is not consistent with its own hashes, recomputed in this browser"), hashOnly);
  assert.ok(!hashOnly.includes("structural"), hashOnly);

  // Structural only: every hash matches.
  const t5 = integrityHeadline(await checked(caseText("t5_final_revision_rehashed")));
  assert.equal(
    t5,
    "The trace is consistent with its own hashes, but it fails a structural check: final-state revision " +
      "against the last frame. The values on the board may not be what was recorded.",
  );
  assert.ok(!t5.includes("not consistent"), t5);
  const t4 = integrityHeadline(await checked(caseText("t4_algorithm_label")));
  assert.ok(t4.includes("fails a structural check: algorithm label."), t4);
  assert.ok(integrityHeadline(await checked(caseText("t6_kind_rehashed"))).includes("structural check: kind."));
  assert.ok(
    integrityHeadline(await checked(caseText("t7_version_rehashed"))).includes("structural check: trace version."),
  );

  // Both, with every structural name listed.
  const both = JSON.parse(fixture.tampered_trace_text) as Record<string, unknown> & { integrity: { algorithm: string } };
  both.kind = "other_trace";
  both.integrity.algorithm = "md5";
  const bothText = integrityHeadline(await checked(JSON.stringify(both)));
  assert.ok(bothText.startsWith("The trace is not consistent with its own hashes"), bothText);
  assert.ok(bothText.includes("and it fails a structural check: algorithm label, kind."), bothText);

  // A zero-frame trace without frame_hashes fails a hash check, and the panel says why.
  const t11 = await checked(caseText("t11_frame_hashes_missing"));
  assert.ok(integrityHeadline(t11).startsWith("The trace is not consistent with its own hashes"));
  assert.ok(
    panelText(t11).includes(
      "✖ Frame hashes: 0 of 0 match (the trace's integrity.frame_hashes is missing or not a list)",
    ),
    panelText(t11),
  );

  // The panel carries the headline after its verdict.
  const panel = panelText(await checked(caseText("t5_final_revision_rehashed")));
  assert.ok(panel.includes("Integrity check failed. The trace is consistent with its own hashes, but it fails"), panel);
  assert.ok(panel.includes("✖ Final state revision 6 differs from the last frame's (5)"), panel);
  assert.ok(panelText(await passed()).includes("Integrity check passed. The trace is consistent with its own hashes"));
});

// ------------------------------------------------------------------ item 2: a verifier that throws

test("a verifier that throws or rejects is a failed check, never a banner stuck at checking", async () => {
  const throwsNow = (): Promise<IntegrityReport> => {
    throw new RangeError("Maximum call stack size exceeded");
  };
  const rejects = (): Promise<IntegrityReport> => Promise.reject(new Error("digest failed"));
  const throwsOddly = (): Promise<IntegrityReport> => Promise.reject(Object.create(null));
  for (const [verify, reason] of [
    [throwsNow, `${NOT_CHECKED_PREFIX} Maximum call stack size exceeded`],
    [rejects, `${NOT_CHECKED_PREFIX} digest failed`],
    [throwsOddly, `${NOT_CHECKED_PREFIX} an error that cannot be described`],
  ] as const) {
    const report = await checkTraceIntegrity(fixture.trace_text, verify);
    assert.deepEqual(report, { status: "malformed", reason });
    assert.equal(integrityState(report), "failed");
    const shown = banner(report);
    assert.ok(shown.includes('data-integrity="failed"'), shown);
    assert.ok(!shown.includes("checking"), shown);
    const text = panelText(report);
    assert.ok(text.includes("Integrity check failed: The trace could not be checked:"), text);
    assert.ok(text.includes("may not be what was recorded"), text);
  }
  // The replay marks the board for these reports exactly as for a failed check.
  assert.ok(frame(integrityState(await checkTraceIntegrity("{}", throwsNow)) === "failed").includes("board-untrusted"));
  // With the real verifier, deep nesting is a malformed report, not a stack overflow.
  const deep = `{"pad": ${"[".repeat(100_000)}${"]".repeat(100_000)}}`;
  const report = await checkTraceIntegrity(deep);
  assert.equal(report.status, "malformed");
  assert.match(report.status === "malformed" ? report.reason : "", /^Nesting deeper than 256 levels/);
  assert.equal((await checkTraceIntegrity(fixture.trace_text)).status, "checked");
});

// ------------------------------------------------------------------ item 4: exact bytes

const BOM = [0xef, 0xbb, 0xbf];
const traceBytes = (): Uint8Array<ArrayBuffer> => new TextEncoder().encode(fixture.trace_text);

test("a local file is decoded from its bytes: a byte order mark or invalid UTF-8 is refused", async () => {
  const loaded = await loadLocalReplay(new File([traceBytes()], "intact.json"));
  assert.equal(loaded.text, fixture.trace_text);
  assert.equal(loaded.origin, "file: intact.json");
  await assert.rejects(
    loadLocalReplay(new File([new Uint8Array([...BOM, ...traceBytes()])], "t8.json")),
    /starts with a UTF-8 byte order mark/,
  );
  await assert.rejects(
    loadLocalReplay(new File([new Uint8Array([...traceBytes().slice(0, 40), 0xff, ...traceBytes().slice(40)])], "x.json")),
    /not valid UTF-8/,
  );
});

test("a server trace is decoded from the response bytes, not response.text()", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; init: RequestInit | undefined }[] = [];
  let body: Uint8Array<ArrayBuffer> = traceBytes();
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    seen.push({ url, init });
    return new Response(body, { status: 200 });
  }) as typeof fetch;
  try {
    const loaded = await loadServerReplay("dev01_trace.json");
    assert.equal(loaded.text, fixture.trace_text);
    assert.equal(seen[0]?.url, "/api/replays/dev01_trace.json");
    assert.equal(seen[0]?.init?.method, "GET");
    assert.equal(seen[0]?.init?.credentials, "omit");

    body = new Uint8Array([...BOM, ...traceBytes()]);
    // response.text() would have dropped the BOM and passed the trace.
    assert.equal(await new Response(body).text(), fixture.trace_text);
    await assert.rejects(loadServerReplay("t8.json"), /starts with a UTF-8 byte order mark/);
  } finally {
    globalThis.fetch = original;
  }
});

// ------------------------------------------------------------------ the loader's fetch options

/** The options of each fetch the loader makes for listReplays and loadServerReplay, in order. */
async function loaderInits(): Promise<(RequestInit | undefined)[]> {
  const original = globalThis.fetch;
  const inits: (RequestInit | undefined)[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    inits.push(init);
    const body = url === "/api/replays" ? JSON.stringify([{ name: "dev01_trace.json" }]) : fixture.trace_text;
    return new Response(body, { status: 200 });
  }) as typeof fetch;
  try {
    assert.deepEqual(await listReplays(), ["dev01_trace.json"]);
    await loadServerReplay("dev01_trace.json");
  } finally {
    globalThis.fetch = original;
  }
  return inits;
}

test("the loader fetches with exactly an explicit GET, no-store and no credentials", async () => {
  const inits = await loaderInits();
  assert.equal(inits.length, 2);
  for (const init of inits) {
    // No headers and no body: the boundary lint holds these options to an allowlist of keys.
    assert.deepEqual({ ...init }, { method: "GET", cache: "no-store", credentials: "omit" });
    assert.deepEqual(Object.keys(init ?? {}), ["method", "cache", "credentials"]);
    // No prototype, and frozen: one shared object that nothing can change.
    assert.equal(Object.getPrototypeOf(init), null);
    assert.ok(Object.isFrozen(init));
  }
  assert.equal(inits[0], inits[1]);
});

// The browser converts fetch options to a RequestInit as WebIDL says: it reads each member in
// lexicographic order with [[Get]], which also finds keys on the prototype chain (Chromium does
// this in C++, so a JS model of the reads stands in for it here; Node's own Request is no model,
// because undici reads inherited keys through its own internal objects as well).
const REQUEST_INIT_MEMBERS = [
  "body",
  "cache",
  "credentials",
  "duplex",
  "headers",
  "integrity",
  "keepalive",
  "method",
  "mode",
  "priority",
  "redirect",
  "referrer",
  "referrerPolicy",
  "signal",
  "window",
] as const;

/** The members a browser reads from `init`, as an object (built with defines, not assignments). */
function readAsRequestInit(init: object): Record<string, unknown> {
  const read: [string, unknown][] = [];
  for (const key of REQUEST_INIT_MEMBERS) {
    const value: unknown = (init as Record<string, unknown>)[key];
    if (value !== undefined) read.push([key, value]);
  }
  return Object.fromEntries(read);
}

test("keys put on Object.prototype never reach the loader's requests (round-3 V1)", async () => {
  const [init] = await loaderInits();
  assert.ok(init !== undefined);
  const plain = { method: "GET", cache: "no-store", credentials: "omit" };
  const frozen = Object.freeze({ ...plain });
  let getterRuns = 0;
  let asPlain: Record<string, unknown> = {};
  let asLoader: Record<string, unknown> = {};
  let frozenThrew: unknown = null;
  // The verifier's V1 getter: `body` is read before `method`, and it rewrites the method.
  Object.defineProperty(Object.prototype, "body", {
    configurable: true,
    get(this: Record<string, unknown>) {
      getterRuns += 1;
      if (this.credentials !== "omit") return undefined;
      this.method = "POST";
      return "{}";
    },
  });
  Object.defineProperty(Object.prototype, "headers", {
    configurable: true,
    value: { "X-HTTP-Method-Override": "POST" },
  });
  try {
    asPlain = readAsRequestInit(plain);
    try {
      readAsRequestInit(frozen);
    } catch (error) {
      frozenThrew = error;
    }
    getterRuns = 0;
    asLoader = readAsRequestInit(init);
  } finally {
    delete (Object.prototype as Record<string, unknown>).body;
    delete (Object.prototype as Record<string, unknown>).headers;
  }
  // A plain literal, as the loader had it: the getter turns the GET into a POST with a body.
  assert.equal(asPlain.method, "POST");
  assert.equal(asPlain.body, "{}");
  assert.deepEqual(asPlain.headers, { "X-HTTP-Method-Override": "POST" });
  // Frozen alone: the getter cannot rewrite the method (a TypeError here), but inherited keys
  // such as headers would still be read.
  assert.ok(frozenThrew instanceof TypeError, String(frozenThrew));
  // The loader's options: only their own keys, and the getter never runs.
  assert.deepEqual(asLoader, { cache: "no-store", credentials: "omit", method: "GET" });
  assert.equal(getterRuns, 0);
  // Nothing can add a key, change one or give the options a prototype.
  assert.throws(() => {
    (init as Record<string, unknown>).method = "POST";
  }, TypeError);
  assert.throws(() => Object.defineProperty(init, "body", { value: "{}" }), TypeError);
  assert.throws(() => Object.setPrototypeOf(init, { body: "{}" }), TypeError);
});

test("why the loader states its method: it overrides a Request input's (Fetch spec)", () => {
  const url = "http://127.0.0.1/api/replays";
  // Stated, GET wins over the input's POST, and a GET cannot carry the input's body.
  assert.equal(new Request(new Request(url, { method: "POST" }), { method: "GET", credentials: "omit" }).method, "GET");
  assert.throws(
    () => new Request(new Request(url, { method: "POST", body: "{}" }), { method: "GET", credentials: "omit" }),
    TypeError,
  );
  // Left out, the input's POST survives; and an inherited __proto__ method is read too.
  assert.equal(new Request(new Request(url, { method: "POST" }), { credentials: "omit" }).method, "POST");
  assert.equal(new Request(url, { credentials: "omit", __proto__: { method: "POST" } } as RequestInit).method, "POST");
});

// ------------------------------------------------------------------ a trace the board cannot render

/** A trace to rehydrate states against, with one stored evaluation. */
function traceWithEvaluation(): SanitizedTrace {
  const trace = JSON.parse(fixture.trace_text) as SanitizedTrace;
  return { ...trace, evaluations: { eval_0001: makeEvaluation([makeCandidate()]) } };
}

/** A full frame state whose latest_evaluation is `latest`, or absent when `latest` is "absent". */
function frameState(latest: unknown): CompactedStateView {
  const state: Record<string, unknown> = { ...makeView() };
  if (latest === "absent") delete state.latest_evaluation;
  else state.latest_evaluation = latest;
  return state as unknown as CompactedStateView;
}

test("rehydration never throws: a missing or odd latest_evaluation shows no evaluation", () => {
  const trace = traceWithEvaluation();
  const stored = trace.evaluations.eval_0001;
  const inline = makeEvaluation([], { evaluation_id: "eval_inline" });
  const cases: [unknown, unknown][] = [
    ["absent", null],
    [null, null],
    ["eval_0001", null],
    [7, null],
    [{ evaluation_ref: "eval_0001" }, stored],
    [{ evaluation_ref: "eval_9999" }, null],
    [{ evaluation_ref: 1 }, null],
    // Own keys only: these are on Object.prototype, not stored evaluations.
    [{ evaluation_ref: "constructor" }, null],
    [{ evaluation_ref: "toString" }, null],
    [{ evaluation_ref: "__proto__" }, null],
    [inline, inline],
  ];
  for (const [latest, expected] of cases) {
    assert.equal(rehydrateState(trace, frameState(latest)).latest_evaluation, expected, JSON.stringify(latest));
  }
  // A trace without an evaluations map finds nothing either.
  const bare = { ...trace, evaluations: undefined } as unknown as SanitizedTrace;
  assert.equal(rehydrateState(bare, frameState({ evaluation_ref: "eval_0001" })).latest_evaluation, null);
});

test("a frame state without latest_evaluation renders the board (the verifier's e1 trace)", () => {
  // Before the fix, `"evaluation_ref" in latest` threw on undefined and the page went blank.
  const view = rehydrateState(traceWithEvaluation(), frameState("absent"));
  const text = textOf(renderToStaticMarkup(createElement(BoardView, { view, mode: "replay" })));
  assert.ok(text.includes("Action history"), text.slice(0, 200));
});

test("the render guard puts the unrenderable notice in place of a board that throws, and reports it", () => {
  // The vector trace t4 has minimal frame states, which the board cannot render. React runs error
  // boundaries only in a browser (the Chromium check loads vec_t4 into the real page); here the
  // guard's own steps run on the error the board really throws.
  const t4 = JSON.parse(caseText("t4_algorithm_label")) as SanitizedTrace;
  const [first] = t4.frames;
  assert.ok(first !== undefined);
  const view = rehydrateState(t4, first.state);
  const board = () => createElement(BoardView, { view, mode: "replay" });
  let thrown: unknown = null;
  try {
    renderToStaticMarkup(board());
  } catch (error) {
    thrown = error;
  }
  assert.ok(thrown instanceof Error, "the board renders t4's minimal state; pick another trace");
  const message = thrown.message;

  const reported: string[] = [];
  const guard = new ReplayRenderGuard({
    onError: (m) => reported.push(m),
    fallback: (m) => createElement(UnrenderableNotice, { message: m }),
    children: board,
  });
  guard.state = ReplayRenderGuard.getDerivedStateFromError(thrown);
  guard.componentDidCatch(thrown);
  assert.deepEqual(reported, [message]);
  const html = renderToStaticMarkup(guard.render());
  assert.ok(html.includes('data-replay-render="failed"'), html);
  assert.ok(html.includes('role="alert"'), html);
  const text = textOf(html);
  assert.ok(text.startsWith(`✖ ${UNRENDERABLE_NOTICE} Rendering it failed with: ${message}`), text);
  assert.ok(text.includes("The board is not shown, and the replay counts the trace as failed"), text);
  assert.equal(UNRENDERABLE_NOTICE, "This trace could not be rendered.");

  // The replay then shows the banner as failed, whatever the hashes said.
  const shown = banner(renderFailureReport(message));
  assert.ok(shown.includes('data-integrity="failed"'), shown);
  assert.ok(textOf(shown).includes("✖ Integrity check failed"), textOf(shown));
  assert.equal(integrityState(renderFailureReport(message)), "failed");

  // A thrown value that cannot be described is still reported, not rethrown.
  assert.deepEqual(ReplayRenderGuard.getDerivedStateFromError(Object.create(null)), {
    error: "an error that cannot be described",
  });
});

test("the render guard renders its part when nothing throws", () => {
  const html = renderToStaticMarkup(
    createElement(ReplayRenderGuard, {
      onError: () => assert.fail("nothing threw"),
      fallback: () => "failed",
      children: () => createElement("p", null, "board"),
    }),
  );
  assert.equal(html, "<p>board</p>");
});
