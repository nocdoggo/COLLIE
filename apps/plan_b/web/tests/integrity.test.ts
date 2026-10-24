// Checks the replay verifier against vectors produced by the server's own canonical_json
// (tests/make_vectors.py). Run with `npm test` (Node >= 22.18 strips the type annotations).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  type IntegrityReport,
  type JsonNode,
  MAX_INT_DIGITS,
  MAX_NESTING,
  canonicalJson,
  compareCodePoints,
  decodeTraceBytes,
  foldChain,
  parseJsonLossless,
  pythonFloatRepr,
  sha256Hex,
  traceShapeProblems,
  verifyTraceBytes,
  verifyTraceText,
} from "../src/replay/integrity.ts";

interface Vector {
  name: string;
  text: string;
  canonical: string;
  sha256: string;
}

type CheckName = "algorithm" | "kind" | "trace_version" | "final_revision" | "frames" | "chain" | "content";

/** Shared cases that both verifiers reject before any hash is computed, and the browser's reason. */
const MALFORMED_REASON = {
  byte_order_mark: /^The trace starts with a UTF-8 byte order mark \(EF BB BF\)/,
  lone_surrogate: /^String is not well-formed Unicode \(a lone UTF-16 surrogate\)/,
  nesting: /^Nesting deeper than 256 levels/,
} as const;
type MalformedCheck = keyof typeof MALFORMED_REASON;

interface TraceCase {
  name: string;
  failing_check: CheckName | MalformedCheck;
  description: string;
  text: string;
}

interface VectorFile {
  vectors: Vector[];
  trace_text: string;
  tampered_trace_text: string;
  trace_cases: TraceCase[];
  nesting_limit_trace_text: string;
}

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/canonical_vectors.json", import.meta.url), "utf-8"),
) as VectorFile;

/** Every check of a report by name, in the vocabulary of the vectors' failing_check. */
function checksOf(report: Extract<IntegrityReport, { status: "checked" }>): Record<CheckName, boolean> {
  return {
    algorithm: report.algorithmOk,
    kind: report.kindOk,
    trace_version: report.traceVersionOk,
    final_revision: report.finalRevision.ok,
    frames: report.framesOk,
    chain: report.chain.ok,
    content: report.content.ok,
  };
}

const failedChecks = (report: Extract<IntegrityReport, { status: "checked" }>): CheckName[] =>
  (Object.entries(checksOf(report)) as [CheckName, boolean][]).filter(([, ok]) => !ok).map(([name]) => name);

for (const vector of fixture.vectors) {
  test(`canonical JSON matches Python for ${vector.name}`, async () => {
    const canonical = canonicalJson(parseJsonLossless(vector.text));
    assert.equal(canonical, vector.canonical);
    assert.equal(await sha256Hex(canonical), vector.sha256);
  });
}

test("float repr follows Python's thresholds", () => {
  assert.equal(pythonFloatRepr(1), "1.0");
  assert.equal(pythonFloatRepr(-0), "-0.0");
  assert.equal(pythonFloatRepr(1e16), "1e+16");
  assert.equal(pythonFloatRepr(1e15), "1000000000000000.0");
  assert.equal(pythonFloatRepr(0.0001), "0.0001");
  assert.equal(pythonFloatRepr(0.00001), "1e-05");
  assert.equal(pythonFloatRepr(1.5e300), "1.5e+300");
});

test("keys sort by code point, not UTF-16 unit", () => {
  const keys = ["\u{1F600}", "￿", "a", ""].sort(compareCodePoints);
  assert.deepEqual(keys, ["a", "", "￿", "\u{1F600}"]);
});

test("integers keep full precision and floats keep their type", () => {
  assert.equal(canonicalJson(parseJsonLossless("[9007199254740993, 2.0, -0]")), "[9007199254740993,2.0,0]");
});

test("parser rejects malformed JSON", () => {
  assert.throws(() => parseJsonLossless('{"a": 1,}'));
  assert.throws(() => parseJsonLossless('"unterminated'));
  assert.throws(() => parseJsonLossless("[1] extra"));
  assert.throws(() => parseJsonLossless('"raw\ncontrol"'));
});

test("a trace exported with the documented hashes verifies", async () => {
  const report = await verifyTraceText(fixture.trace_text);
  assert.equal(report.status, "checked");
  if (report.status !== "checked") return;
  assert.equal(report.framesOk, true);
  assert.equal(report.chain.ok, true);
  assert.equal(report.content.ok, true);
  assert.equal(report.ok, true);
  assert.deepEqual(failedChecks(report), []);
  assert.deepEqual(report.finalRevision, { lastFrame: 5, finalState: 5, ok: true });
  assert.deepEqual(traceShapeProblems(JSON.parse(fixture.trace_text)), []);
});

const bytesOf = (text: string): Uint8Array => new TextEncoder().encode(text);
const isMalformedCheck = (name: string): name is MalformedCheck => Object.hasOwn(MALFORMED_REASON, name);

// The same cases, from the same UTF-8 bytes, run through verify_trace_bytes in
// tests/test_trace_verifier.py (review WEB-3 and item 4).
test("the shared trace cases cover every check the two verifiers add", () => {
  assert.deepEqual(
    fixture.trace_cases.map((c) => c.failing_check),
    ["algorithm", "final_revision", "kind", "trace_version", "byte_order_mark", "lone_surrogate", "nesting", "frames"],
  );
});

for (const c of fixture.trace_cases) {
  test(`${c.name} fails only its ${c.failing_check} check: ${c.description}`, async () => {
    const report = await verifyTraceBytes(bytesOf(c.text));
    const check = c.failing_check;
    if (isMalformedCheck(check)) {
      assert.equal(report.status, "malformed");
      if (report.status !== "malformed") return;
      assert.match(report.reason, MALFORMED_REASON[check]);
      return;
    }
    assert.equal(report.status, "checked");
    if (report.status !== "checked") return;
    assert.equal(report.ok, false);
    assert.deepEqual(failedChecks(report), [check]);
  });
}

test("the intact trace verifies from its bytes, and the deepest shared trace still verifies", async () => {
  assert.equal(MAX_NESTING, 256);
  for (const text of [fixture.trace_text, fixture.nesting_limit_trace_text]) {
    const report = await verifyTraceBytes(bytesOf(text));
    assert.equal(report.status, "checked");
    assert.equal(report.status === "checked" && report.ok, true);
  }
});

// A missing or non-list integrity.frame_hashes is a reported problem, as in verify_trace, even
// with no frames to hash (round-2 verify:web). The shared case t11 leaves it out; these put a
// value back by editing the text, since a JSON round trip here would turn 1.0 into 1.
const t11Text = (): string => {
  const found = fixture.trace_cases.find((c) => c.name === "t11_frame_hashes_missing");
  assert.ok(found !== undefined);
  return found.text;
};
const withFrameHashes = (text: string, value: string): string => {
  const out = text.replace('"integrity": {', `"integrity": {"frame_hashes": ${value}, `);
  assert.notEqual(out, text);
  return out;
};

for (const [label, value] of [
  ["missing", null],
  ["null", "null"],
  ["a string", '"none"'],
  ["an object", "{}"],
  ["a number", "0"],
] as const) {
  test(`a zero-frame trace whose frame_hashes is ${label} fails the frame check only`, async () => {
    const text = value === null ? t11Text() : withFrameHashes(t11Text(), value);
    assert.deepEqual((JSON.parse(text) as { frames: unknown[] }).frames, []);
    const report = await verifyTraceText(text);
    assert.equal(report.status, "checked");
    if (report.status !== "checked") return;
    assert.equal(report.ok, false);
    assert.deepEqual(failedChecks(report), ["frames"]);
    assert.equal(report.listedFrameHashes, null);
  });
}

test("a zero-frame trace with the exporter's empty frame_hashes list verifies", async () => {
  const report = await verifyTraceText(withFrameHashes(t11Text(), "[]"));
  assert.equal(report.status === "checked" && report.ok, true);
  assert.equal(report.status === "checked" ? report.listedFrameHashes : -1, 0);
});

test("a trace with frames whose frame_hashes is not a list fails its frame check", async () => {
  const text = fixture.trace_text.replace(/"frame_hashes": \[[^\]]*\]/, '"frame_hashes": "none"');
  assert.notEqual(text, fixture.trace_text);
  const report = await verifyTraceText(text);
  assert.equal(report.status, "checked");
  if (report.status !== "checked") return;
  assert.equal(report.framesOk, false);
  assert.equal(report.listedFrameHashes, null);
  // The chain folds the listed hashes, and there are none.
  assert.deepEqual(failedChecks(report), ["frames", "chain"]);
});

// ------------------------------------------------------------------ item 4: byte-level input

test("a byte order mark is rejected from the bytes and from decoded text", async () => {
  const bom = new Uint8Array([0xef, 0xbb, 0xbf, ...bytesOf(fixture.trace_text)]);
  assert.throws(() => decodeTraceBytes(bom), /byte order mark/);
  // What Response.text() and Blob.text() would have handed the verifier: the BOM silently gone.
  assert.equal(await new Blob([bom]).text(), fixture.trace_text);
  const report = await verifyTraceText(`\ufeff${fixture.trace_text}`);
  assert.equal(report.status, "malformed");
  assert.match(report.status === "malformed" ? report.reason : "", /byte order mark \(U\+FEFF\)/);
});

for (const [name, bad] of [
  ["an invalid byte", [0x63, 0x61, 0x66, 0xff]],
  ["a truncated sequence", [0x63, 0x61, 0x66, 0xc3]],
  ["an encoded surrogate", [0x63, 0x61, 0x66, 0xed, 0xa0, 0x80]],
] as const) {
  test(`bytes with ${name} are not UTF-8 and are rejected, never replaced`, async () => {
    const intact = bytesOf(fixture.trace_text);
    const cafe = bytesOf("café");
    const at = Buffer.from(intact).indexOf(Buffer.from(cafe));
    assert.ok(at > 0);
    const data = new Uint8Array([...intact.slice(0, at), ...bad, ...intact.slice(at + cafe.length)]);
    assert.throws(() => decodeTraceBytes(data), /not valid UTF-8/);
    assert.deepEqual(await verifyTraceBytes(data), { status: "malformed", reason: "The trace is not valid UTF-8." });
  });
}

for (const escape of ["\\ud800", "\\udfff", "\\ude00\\ud83d"]) {
  test(`a lone surrogate (${escape}) in a value or a key is not well-formed Unicode`, async () => {
    const trace = JSON.parse(fixture.trace_text) as { frames: { summary: string }[] };
    (trace.frames[0] as { summary: string }).summary = "x";
    const plain = JSON.stringify(trace);
    for (const text of [
      plain.replace('"summary":"x"', `"summary":"${escape}"`),
      plain.replace('"summary":"x"', `"${escape}":"x"`),
    ]) {
      assert.notEqual(text, plain);
      const report = await verifyTraceText(text);
      assert.equal(report.status, "malformed");
      assert.match(report.status === "malformed" ? report.reason : "", MALFORMED_REASON.lone_surrogate);
    }
  });
}

test("an escaped surrogate pair is one character and verifies", async () => {
  const text = fixture.trace_text.replaceAll("\u{1F600}", "\\ud83d\\ude00");
  assert.notEqual(text, fixture.trace_text);
  const report = await verifyTraceText(text);
  assert.equal(report.status === "checked" && report.ok, true);
});

for (const depth of [MAX_NESTING + 1, 5_000, 100_000]) {
  test(`nesting ${depth} levels deep is reported as malformed, never thrown`, async () => {
    const pad = "[".repeat(depth - 1) + "]".repeat(depth - 1);
    const text = fixture.trace_text.replace("{", `{"pad": ${pad}, `);
    const report = await verifyTraceText(text);
    assert.equal(report.status, "malformed");
    assert.match(report.status === "malformed" ? report.reason : "", MALFORMED_REASON.nesting);
  });
}

test("canonical JSON is written without recursion, at any depth", () => {
  let node: JsonNode = { kind: "array", items: [] };
  for (let i = 1; i < 200_000; i += 1) node = { kind: "array", items: [node] };
  const out = canonicalJson(node);
  assert.equal(out.length, 400_000);
  assert.ok(out.startsWith("[[[") && out.endsWith("]]]"));
  // Order and separators are unchanged by the explicit stack.
  assert.equal(
    canonicalJson(parseJsonLossless('{"b": [1, {"d": null, "c": true}], "a": "x", "": []}')),
    '{"":[],"a":"x","b":[1,{"c":true,"d":null}]}',
  );
});

test("an integer longer than Python's int conversion limit is malformed", () => {
  assert.equal(MAX_INT_DIGITS, 4300);
  const longest = `-${"9".repeat(MAX_INT_DIGITS)}`;
  assert.equal(canonicalJson(parseJsonLossless(longest)), longest);
  assert.throws(() => parseJsonLossless("9".repeat(MAX_INT_DIGITS + 1)), /Integer longer than 4300 digits/);
  // Floats have no such limit, in Python or here.
  assert.equal(canonicalJson(parseJsonLossless(`${"9".repeat(MAX_INT_DIGITS + 1)}.0`)), "Infinity");
});

test("a final state one revision past the last frame is reported with both revisions", async () => {
  const t5 = fixture.trace_cases.find((c) => c.name === "t5_final_revision_rehashed");
  assert.ok(t5 !== undefined);
  const report = await verifyTraceText(t5.text);
  assert.equal(report.status, "checked");
  if (report.status !== "checked") return;
  assert.deepEqual(report.finalRevision, { lastFrame: 5, finalState: 6, ok: false });
});

test("a revision that is not an integer never matches", async () => {
  const trace = JSON.parse(fixture.trace_text) as { final_state: { revision: unknown } };
  trace.final_state.revision = "5";
  const report = await verifyTraceText(JSON.stringify(trace));
  assert.equal(report.status, "checked");
  if (report.status !== "checked") return;
  assert.deepEqual(report.finalRevision, { lastFrame: 5, finalState: null, ok: false });
});

test("an edited frame fails its frame hash, the content hash, and nothing else", async () => {
  const report = await verifyTraceText(fixture.tampered_trace_text);
  assert.equal(report.status, "checked");
  if (report.status !== "checked") return;
  assert.equal(report.ok, false);
  assert.equal(report.frames[0]?.ok, false);
  assert.equal(report.frames[1]?.ok, true);
  assert.equal(report.content.ok, false);
  // The chain folds the recorded frame hashes, which the edit did not touch.
  assert.equal(report.chain.ok, true);
  assert.deepEqual(failedChecks(report), ["frames", "content"]);
});

test("the chain fold is order-sensitive", async () => {
  const a = await sha256Hex("a");
  const b = await sha256Hex("b");
  assert.notEqual(await foldChain([a, b]), await foldChain([b, a]));
  assert.equal(await foldChain([]), "");
});

test("non-trace input is reported, not rendered", async () => {
  assert.equal((await verifyTraceText("[1, 2]")).status, "malformed");
  assert.equal((await verifyTraceText("{not json")).status, "malformed");
  assert.ok(traceShapeProblems({ kind: "other" }).length > 0);
});
