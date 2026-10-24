// Checks the replay verifier against vectors produced by the server's own canonical_json
// (tests/make_vectors.py). Run with `npm test` (Node >= 22.18 strips the type annotations).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  canonicalJson,
  compareCodePoints,
  foldChain,
  parseJsonLossless,
  pythonFloatRepr,
  sha256Hex,
  traceShapeProblems,
  verifyTraceText,
} from "../src/replay/integrity.ts";

interface Vector {
  name: string;
  text: string;
  canonical: string;
  sha256: string;
}

interface VectorFile {
  vectors: Vector[];
  trace_text: string;
  tampered_trace_text: string;
}

const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/canonical_vectors.json", import.meta.url), "utf-8"),
) as VectorFile;

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
  assert.deepEqual(traceShapeProblems(JSON.parse(fixture.trace_text)), []);
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
