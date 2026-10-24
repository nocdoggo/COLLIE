// Client-side trace integrity check (contract section 13).
//
// The exporter hashes `canonical_json(value)` from plan_b/domain/digest.py, i.e. Python's
// json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) encoded as UTF-8.
// Re-serializing with JSON.parse + JSON.stringify would not reproduce it: JS loses the
// int/float distinction (Python writes 1.0, JS writes 1), rounds integers above 2^53, formats
// exponents differently, and sorts keys by UTF-16 code unit instead of code point. This module
// therefore parses the trace text itself, keeps every number's lexical type, and writes the
// canonical form exactly as Python would.
//
// Both verifiers also reject the same byte-level input (review item 4): a UTF-8 byte order
// mark, bytes that are not UTF-8, a string that is not well-formed Unicode (a lone UTF-16
// surrogate, which Python cannot encode), nesting deeper than MAX_NESTING, and an integer longer
// than MAX_INT_DIGITS (Python's default int conversion limit). The nesting limit also keeps the
// recursive parser far from the JavaScript stack limit.
//
// This file performs no network calls and imports only types.

import type { SanitizedTrace } from "../types";

export type JsonNode =
  | { readonly kind: "object"; readonly entries: ReadonlyMap<string, JsonNode> }
  | { readonly kind: "array"; readonly items: readonly JsonNode[] }
  | { readonly kind: "string"; readonly value: string }
  | { readonly kind: "int"; readonly value: bigint }
  | { readonly kind: "float"; readonly value: number }
  | { readonly kind: "bool"; readonly value: boolean }
  | { readonly kind: "null" };

export class JsonSyntaxError extends Error {
  readonly position: number;
  constructor(message: string, position: number) {
    super(`${message} at character ${position}`);
    this.name = "JsonSyntaxError";
    this.position = position;
  }
}

const NUMBER_RE = /-?(?:0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?/y;

/** Deepest nesting of objects and arrays a trace may have; the trace object itself is level 1. */
export const MAX_NESTING = 256;

/** Longest integer a trace may hold, in digits without the sign (Python's int_max_str_digits). */
export const MAX_INT_DIGITS = 4300;

/** Matches a UTF-16 surrogate that is not half of a pair (the u flag reads pairs as one code point). */
const LONE_SURROGATE = /[\uD800-\uDFFF]/u;

/** Parse JSON text the way Python's json.loads does, keeping each number's int/float type. */
export function parseJsonLossless(text: string): JsonNode {
  let pos = 0;
  let depth = 0;

  function fail(message: string): never {
    throw new JsonSyntaxError(message, pos);
  }

  const skipWhitespace = (): void => {
    while (pos < text.length) {
      const c = text.charCodeAt(pos);
      if (c === 0x20 || c === 0x09 || c === 0x0a || c === 0x0d) pos += 1;
      else break;
    }
  };

  const parseString = (): string => {
    // The opening quote has been consumed.
    let out = "";
    let chunkStart = pos;
    while (true) {
      if (pos >= text.length) fail("Unterminated string");
      const c = text.charCodeAt(pos);
      if (c === 0x22) {
        out += text.slice(chunkStart, pos);
        if (LONE_SURROGATE.test(out)) fail("String is not well-formed Unicode (a lone UTF-16 surrogate)");
        pos += 1;
        return out;
      }
      if (c < 0x20) fail("Unescaped control character in string");
      if (c !== 0x5c) {
        pos += 1;
        continue;
      }
      out += text.slice(chunkStart, pos);
      pos += 1;
      const esc = text[pos];
      pos += 1;
      switch (esc) {
        case '"':
          out += '"';
          break;
        case "\\":
          out += "\\";
          break;
        case "/":
          out += "/";
          break;
        case "b":
          out += "\b";
          break;
        case "f":
          out += "\f";
          break;
        case "n":
          out += "\n";
          break;
        case "r":
          out += "\r";
          break;
        case "t":
          out += "\t";
          break;
        case "u": {
          const hex = text.slice(pos, pos + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("Invalid \\u escape");
          out += String.fromCharCode(parseInt(hex, 16));
          pos += 4;
          break;
        }
        default:
          fail("Invalid escape");
      }
      chunkStart = pos;
    }
  };

  const enter = (): void => {
    depth += 1;
    if (depth > MAX_NESTING) fail(`Nesting deeper than ${MAX_NESTING} levels`);
    pos += 1;
  };

  const parseValue = (): JsonNode => {
    skipWhitespace();
    if (pos >= text.length) fail("Unexpected end of input");
    const ch = text[pos];
    if (ch === "{") {
      enter();
      const entries = new Map<string, JsonNode>();
      skipWhitespace();
      if (text[pos] === "}") {
        pos += 1;
        depth -= 1;
        return { kind: "object", entries };
      }
      while (true) {
        skipWhitespace();
        if (text[pos] !== '"') fail("Expected a property name");
        pos += 1;
        const key = parseString();
        skipWhitespace();
        if (text[pos] !== ":") fail("Expected ':'");
        pos += 1;
        // A repeated key keeps the last value, as in Python.
        entries.set(key, parseValue());
        skipWhitespace();
        if (text[pos] === ",") {
          pos += 1;
          continue;
        }
        if (text[pos] === "}") {
          pos += 1;
          depth -= 1;
          return { kind: "object", entries };
        }
        fail("Expected ',' or '}'");
      }
    }
    if (ch === "[") {
      enter();
      const items: JsonNode[] = [];
      skipWhitespace();
      if (text[pos] === "]") {
        pos += 1;
        depth -= 1;
        return { kind: "array", items };
      }
      while (true) {
        items.push(parseValue());
        skipWhitespace();
        if (text[pos] === ",") {
          pos += 1;
          continue;
        }
        if (text[pos] === "]") {
          pos += 1;
          depth -= 1;
          return { kind: "array", items };
        }
        fail("Expected ',' or ']'");
      }
    }
    if (ch === '"') {
      pos += 1;
      return { kind: "string", value: parseString() };
    }
    if (text.startsWith("true", pos)) {
      pos += 4;
      return { kind: "bool", value: true };
    }
    if (text.startsWith("false", pos)) {
      pos += 5;
      return { kind: "bool", value: false };
    }
    if (text.startsWith("null", pos)) {
      pos += 4;
      return { kind: "null" };
    }
    // Python's json.loads also accepts these non-standard constants.
    if (text.startsWith("NaN", pos)) {
      pos += 3;
      return { kind: "float", value: Number.NaN };
    }
    if (text.startsWith("Infinity", pos)) {
      pos += 8;
      return { kind: "float", value: Number.POSITIVE_INFINITY };
    }
    if (text.startsWith("-Infinity", pos)) {
      pos += 9;
      return { kind: "float", value: Number.NEGATIVE_INFINITY };
    }
    NUMBER_RE.lastIndex = pos;
    const m = NUMBER_RE.exec(text);
    if (m === null) return fail("Unexpected character");
    const lexeme = m[0];
    const isFloat = m[1] !== undefined || m[2] !== undefined;
    if (!isFloat && lexeme.replace("-", "").length > MAX_INT_DIGITS) {
      fail(`Integer longer than ${MAX_INT_DIGITS} digits`);
    }
    pos += lexeme.length;
    return isFloat ? { kind: "float", value: Number(lexeme) } : { kind: "int", value: BigInt(lexeme) };
  };

  const root = parseValue();
  skipWhitespace();
  if (pos !== text.length) fail("Extra data after the JSON value");
  return root;
}

/** Python's repr(float), which json.dumps uses for floats. */
export function pythonFloatRepr(x: number): string {
  if (Number.isNaN(x)) return "NaN";
  if (x === Number.POSITIVE_INFINITY) return "Infinity";
  if (x === Number.NEGATIVE_INFINITY) return "-Infinity";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const sign = x < 0 ? "-" : "";
  // toExponential() without an argument yields the shortest round-trip digits, as Python's repr.
  const [mantissa = "", exponentText = "0"] = Math.abs(x).toExponential().split("e");
  const digits = mantissa.replace(".", "");
  const exponent = Number(exponentText);
  const decimalPoint = exponent + 1;
  if (decimalPoint <= -4 || decimalPoint > 16) {
    const head = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    const magnitude = Math.abs(exponent);
    const expDigits = magnitude < 10 ? `0${magnitude}` : String(magnitude);
    return `${sign}${head}e${exponent < 0 ? "-" : "+"}${expDigits}`;
  }
  if (decimalPoint <= 0) return `${sign}0.${"0".repeat(-decimalPoint)}${digits}`;
  if (decimalPoint >= digits.length) {
    return `${sign}${digits}${"0".repeat(decimalPoint - digits.length)}.0`;
  }
  return `${sign}${digits.slice(0, decimalPoint)}.${digits.slice(decimalPoint)}`;
}

/** Compare strings by Unicode code point, as Python's sorted() does for str keys. */
export function compareCodePoints(a: string, b: string): number {
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const ca = a.codePointAt(i) as number;
    const cb = b.codePointAt(j) as number;
    if (ca !== cb) return ca < cb ? -1 : 1;
    i += ca > 0xffff ? 2 : 1;
    j += cb > 0xffff ? 2 : 1;
  }
  const restA = a.length - i;
  const restB = b.length - j;
  return restA === restB ? 0 : restA < restB ? -1 : 1;
}

// JSON.stringify escapes exactly the characters Python's ensure_ascii=False encoder escapes
// (", \, and U+0000..U+001F with the same short forms and lowercase \u00xx), and leaves every
// other character, including U+2028/U+2029 and non-BMP characters, unescaped.
const encodeString = (value: string): string => JSON.stringify(value);

/**
 * Python canonical_json of a parsed node: sorted keys, "," and ":" separators. The walk keeps an
 * explicit stack instead of recursing, so no nesting depth can overflow the call stack.
 */
export function canonicalJson(node: JsonNode): string {
  const out: string[] = [];
  // Pending work, last item first: a node to write or literal text to emit.
  const stack: (JsonNode | string)[] = [node];
  while (stack.length > 0) {
    const n = stack.pop() as JsonNode | string;
    if (typeof n === "string") {
      out.push(n);
      continue;
    }
    switch (n.kind) {
      case "object": {
        const keys = [...n.entries.keys()].sort(compareCodePoints);
        stack.push("}");
        for (let index = keys.length - 1; index >= 0; index -= 1) {
          const key = keys[index] as string;
          stack.push(n.entries.get(key) as JsonNode, `${encodeString(key)}:`);
          if (index > 0) stack.push(",");
        }
        stack.push("{");
        break;
      }
      case "array":
        stack.push("]");
        for (let index = n.items.length - 1; index >= 0; index -= 1) {
          stack.push(n.items[index] as JsonNode);
          if (index > 0) stack.push(",");
        }
        stack.push("[");
        break;
      case "string":
        out.push(encodeString(n.value));
        break;
      case "int":
        out.push(n.value.toString());
        break;
      case "float":
        out.push(pythonFloatRepr(n.value));
        break;
      case "bool":
        out.push(n.value ? "true" : "false");
        break;
      case "null":
        out.push("null");
        break;
    }
  }
  return out.join("");
}

/**
 * A trace file's text from its exact bytes. The browser decodes the bytes itself because
 * Response.text() and Blob.text() silently drop a leading byte order mark; `plan-b verify-trace`
 * rejects one, and so does this. Bytes that are not UTF-8 are rejected too, never replaced.
 */
export function decodeTraceBytes(bytes: Uint8Array): string {
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    throw new Error("The trace starts with a UTF-8 byte order mark (EF BB BF); a trace has none.");
  }
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    throw new Error("The trace is not valid UTF-8.");
  }
}

export function subtleCryptoAvailable(): boolean {
  return typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.subtle !== "undefined";
}

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Chain fold used to check `integrity.chain_sha256`. The contract says only that the chain
 * "folds [the frame hashes] in order"; this verifier uses
 *   acc = "" ; for each h in frame_hashes: acc = sha256_hex(acc + h) ; chain_sha256 = acc
 * where `+` concatenates the lowercase hex strings and the hash is over their UTF-8 bytes.
 */
export const CHAIN_FOLD_DESCRIPTION =
  'acc = ""; for each frame hash h: acc = sha256_hex(acc + h) (hex strings, UTF-8)';

export async function foldChain(frameHashes: readonly string[]): Promise<string> {
  let acc = "";
  for (const h of frameHashes) acc = await sha256Hex(acc + h);
  return acc;
}

export interface HashComparison {
  readonly expected: string | null;
  readonly actual: string;
  readonly ok: boolean;
}

export interface FrameHashResult extends HashComparison {
  readonly index: number;
}

export interface RevisionComparison {
  readonly lastFrame: number | null;
  readonly finalState: number | null;
  readonly ok: boolean;
}

/** The trace kind and version both verifiers accept (plan_b/evaluation/export_trace.py). */
export const TRACE_KIND = "plan_b_sanitized_trace";
export const TRACE_VERSION = "1.0.0";

export type IntegrityReport =
  | { readonly status: "unavailable"; readonly reason: string }
  | { readonly status: "malformed"; readonly reason: string }
  | {
      readonly status: "checked";
      readonly ok: boolean;
      readonly algorithm: string | null;
      readonly algorithmOk: boolean;
      readonly kind: string | null;
      readonly kindOk: boolean;
      readonly traceVersion: string | null;
      readonly traceVersionOk: boolean;
      /** The last frame's state revision against final_state's (vacuous with no frames). */
      readonly finalRevision: RevisionComparison;
      readonly frameCount: number;
      /** How many hashes integrity.frame_hashes lists; null when it is missing or not a list. */
      readonly listedFrameHashes: number | null;
      readonly frames: readonly FrameHashResult[];
      readonly framesOk: boolean;
      readonly chain: HashComparison;
      readonly content: HashComparison;
    };

const getEntry = (node: JsonNode, key: string): JsonNode | undefined =>
  node.kind === "object" ? node.entries.get(key) : undefined;

const stringOf = (node: JsonNode | undefined): string | null =>
  node !== undefined && node.kind === "string" ? node.value : null;

/** A state's integer revision; anything else (missing, float, string) is null. */
const revisionOf = (state: JsonNode | undefined): bigint | null => {
  const node = state !== undefined ? getEntry(state, "revision") : undefined;
  return node !== undefined && node.kind === "int" ? node.value : null;
};

/**
 * Recompute every documented hash of a trace from its exact text, and make the same checks as
 * the server's `plan-b verify-trace` (verify_trace in plan_b/evaluation/export_trace.py): the
 * algorithm label, the trace kind and version, and that the last frame's revision is the final
 * state's. The two verifiers must accept and reject the same traces; the shared vectors in
 * tests/fixtures/canonical_vectors.json check that in both test suites.
 *
 * The hashes are not signed. A passing check shows the trace is consistent with its own hashes,
 * which detects corruption, not deliberate edits: whoever edits a trace can recompute them.
 */
export async function verifyTraceText(text: string): Promise<IntegrityReport> {
  if (text.charCodeAt(0) === 0xfeff) {
    return { status: "malformed", reason: "The trace starts with a byte order mark (U+FEFF); a trace has none." };
  }
  let root: JsonNode;
  try {
    root = parseJsonLossless(text);
  } catch (error) {
    return { status: "malformed", reason: describeError(error) };
  }
  if (root.kind !== "object") return { status: "malformed", reason: "The trace is not an object." };
  if (!subtleCryptoAvailable()) {
    return {
      status: "unavailable",
      reason:
        "This browser context has no SubtleCrypto (it needs https, localhost or 127.0.0.1), " +
        "so the hashes were not checked.",
    };
  }
  const frames = getEntry(root, "frames");
  const integrity = getEntry(root, "integrity");
  if (frames === undefined || frames.kind !== "array") {
    return { status: "malformed", reason: "The trace has no frames array." };
  }
  if (integrity === undefined || integrity.kind !== "object") {
    return { status: "malformed", reason: "The trace has no integrity block." };
  }
  // A missing or non-list frame_hashes fails the frame check even with no frames, as in
  // verify_trace: it is not the empty list the exporter writes for a trace without frames.
  const listedNode = getEntry(integrity, "frame_hashes");
  const listedIsList = listedNode !== undefined && listedNode.kind === "array";
  const listed: (string | null)[] = listedIsList ? listedNode.items.map((item) => stringOf(item)) : [];

  const frameResults: FrameHashResult[] = [];
  for (let index = 0; index < frames.items.length; index += 1) {
    const actual = await sha256Hex(canonicalJson(frames.items[index] as JsonNode));
    const expected = listed[index] ?? null;
    frameResults.push({ index, expected, actual, ok: expected === actual });
  }
  const framesOk =
    listedIsList && listed.length === frames.items.length && frameResults.every((result) => result.ok);

  const listedStrings = listed.filter((h): h is string => h !== null);
  const chainActual =
    listedStrings.length === listed.length ? await foldChain(listedStrings) : "";
  const chainExpected = stringOf(getEntry(integrity, "chain_sha256"));

  const withoutIntegrity = new Map(root.entries);
  withoutIntegrity.delete("integrity");
  const contentActual = await sha256Hex(
    canonicalJson({ kind: "object", entries: withoutIntegrity }),
  );
  const contentExpected = stringOf(getEntry(integrity, "content_sha256"));

  const algorithm = stringOf(getEntry(integrity, "algorithm"));
  const algorithmOk = algorithm === "sha256";
  const kind = stringOf(getEntry(root, "kind"));
  const kindOk = kind === TRACE_KIND;
  const traceVersion = stringOf(getEntry(root, "trace_version"));
  const traceVersionOk = traceVersion === TRACE_VERSION;
  const lastFrame = frames.items[frames.items.length - 1];
  const lastRevision = lastFrame !== undefined ? revisionOf(getEntry(lastFrame, "state")) : null;
  const finalRevision = revisionOf(getEntry(root, "final_state"));
  const revision: RevisionComparison = {
    lastFrame: lastRevision !== null ? Number(lastRevision) : null,
    finalState: finalRevision !== null ? Number(finalRevision) : null,
    ok: lastFrame === undefined || (lastRevision !== null && lastRevision === finalRevision),
  };
  const chain = { expected: chainExpected, actual: chainActual, ok: chainExpected === chainActual };
  const content = {
    expected: contentExpected,
    actual: contentActual,
    ok: contentExpected === contentActual,
  };
  return {
    status: "checked",
    ok: algorithmOk && kindOk && traceVersionOk && revision.ok && framesOk && chain.ok && content.ok,
    algorithm,
    algorithmOk,
    kind,
    kindOk,
    traceVersion,
    traceVersionOk,
    finalRevision: revision,
    frameCount: frames.items.length,
    listedFrameHashes: listedIsList ? listed.length : null,
    frames: frameResults,
    framesOk,
    chain,
    content,
  };
}

/** verifyTraceText on a trace file's exact bytes: decoding problems are reported, not thrown. */
export async function verifyTraceBytes(bytes: Uint8Array): Promise<IntegrityReport> {
  let text: string;
  try {
    text = decodeTraceBytes(bytes);
  } catch (error) {
    return { status: "malformed", reason: describeError(error) };
  }
  return verifyTraceText(text);
}

/** An error's message for a report; never throws, whatever was thrown. */
export function describeError(error: unknown): string {
  try {
    return error instanceof Error ? error.message : String(error);
  } catch {
    return "an error that cannot be described";
  }
}

export const NOT_CHECKED_PREFIX = "The trace could not be checked:";

/**
 * The replay's integrity check. It always settles with a report: if the verifier throws or
 * rejects (a stack overflow, a SubtleCrypto failure), the trace is reported as failed, so the
 * banner never stays at "checking" and the board is marked exactly as for a failed check.
 */
export async function checkTraceIntegrity(
  text: string,
  verify: (text: string) => Promise<IntegrityReport> = verifyTraceText,
): Promise<IntegrityReport> {
  try {
    return await verify(text);
  } catch (error) {
    return { status: "malformed", reason: `${NOT_CHECKED_PREFIX} ${describeError(error)}` };
  }
}

/** The names of the structural checks a checked report failed, for the panel's headline. */
export function failedStructuralChecks(report: Extract<IntegrityReport, { status: "checked" }>): string[] {
  const names: string[] = [];
  if (!report.algorithmOk) names.push("algorithm label");
  if (!report.kindOk) names.push("kind");
  if (!report.traceVersionOk) names.push("trace version");
  if (!report.finalRevision.ok) names.push("final-state revision against the last frame");
  return names;
}

/** Whether a checked report failed a recomputed hash (frames, chain or content). */
export const hashesFailed = (report: Extract<IntegrityReport, { status: "checked" }>): boolean =>
  !report.framesOk || !report.chain.ok || !report.content.ok;

export type IntegrityState = "checking" | "passed" | "failed" | "not_checked";

/** The replay banner's word for a report; a failed one also marks the board as untrusted. */
export function integrityState(report: IntegrityReport | "checking"): IntegrityState {
  if (report === "checking") return "checking";
  if (report.status === "unavailable") return "not_checked";
  return report.status === "checked" && report.ok ? "passed" : "failed";
}

/** Structural checks before the board renders a trace's frames. */
export function traceShapeProblems(value: unknown): string[] {
  const problems: string[] = [];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return ["The file is not a JSON object."];
  }
  const trace = value as Partial<SanitizedTrace>;
  if (trace.kind !== TRACE_KIND) {
    problems.push(`kind is ${JSON.stringify(trace.kind)}, expected "${TRACE_KIND}".`);
  }
  if (trace.trace_version !== TRACE_VERSION) {
    problems.push(`trace_version is ${JSON.stringify(trace.trace_version)}, expected "${TRACE_VERSION}".`);
  }
  if (!Array.isArray(trace.frames)) {
    problems.push("frames is missing.");
  } else {
    trace.frames.forEach((frame, index) => {
      const state = (frame as { state?: unknown } | null)?.state;
      if (typeof state !== "object" || state === null) {
        problems.push(`frame ${index} has no state.`);
      }
    });
  }
  return problems;
}
