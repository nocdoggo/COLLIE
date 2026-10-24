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

/** Parse JSON text the way Python's json.loads does, keeping each number's int/float type. */
export function parseJsonLossless(text: string): JsonNode {
  let pos = 0;

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

  const parseValue = (): JsonNode => {
    skipWhitespace();
    if (pos >= text.length) fail("Unexpected end of input");
    const ch = text[pos];
    if (ch === "{") {
      pos += 1;
      const entries = new Map<string, JsonNode>();
      skipWhitespace();
      if (text[pos] === "}") {
        pos += 1;
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
          return { kind: "object", entries };
        }
        fail("Expected ',' or '}'");
      }
    }
    if (ch === "[") {
      pos += 1;
      const items: JsonNode[] = [];
      skipWhitespace();
      if (text[pos] === "]") {
        pos += 1;
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
    pos += lexeme.length;
    const isFloat = m[1] !== undefined || m[2] !== undefined;
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

/** Python canonical_json of a parsed node: sorted keys, "," and ":" separators. */
export function canonicalJson(node: JsonNode): string {
  const out: string[] = [];
  const write = (n: JsonNode): void => {
    switch (n.kind) {
      case "object": {
        const keys = [...n.entries.keys()].sort(compareCodePoints);
        out.push("{");
        keys.forEach((key, index) => {
          if (index > 0) out.push(",");
          out.push(encodeString(key), ":");
          write(n.entries.get(key) as JsonNode);
        });
        out.push("}");
        return;
      }
      case "array":
        out.push("[");
        n.items.forEach((item, index) => {
          if (index > 0) out.push(",");
          write(item);
        });
        out.push("]");
        return;
      case "string":
        out.push(encodeString(n.value));
        return;
      case "int":
        out.push(n.value.toString());
        return;
      case "float":
        out.push(pythonFloatRepr(n.value));
        return;
      case "bool":
        out.push(n.value ? "true" : "false");
        return;
      case "null":
        out.push("null");
        return;
    }
  };
  write(node);
  return out.join("");
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

export type IntegrityReport =
  | { readonly status: "unavailable"; readonly reason: string }
  | { readonly status: "malformed"; readonly reason: string }
  | {
      readonly status: "checked";
      readonly ok: boolean;
      readonly algorithm: string | null;
      readonly algorithmOk: boolean;
      readonly frameCount: number;
      readonly listedFrameHashes: number;
      readonly frames: readonly FrameHashResult[];
      readonly framesOk: boolean;
      readonly chain: HashComparison;
      readonly content: HashComparison;
    };

const getEntry = (node: JsonNode, key: string): JsonNode | undefined =>
  node.kind === "object" ? node.entries.get(key) : undefined;

const stringOf = (node: JsonNode | undefined): string | null =>
  node !== undefined && node.kind === "string" ? node.value : null;

/** Recompute every documented hash of a trace from its exact text. */
export async function verifyTraceText(text: string): Promise<IntegrityReport> {
  if (!subtleCryptoAvailable()) {
    return {
      status: "unavailable",
      reason:
        "This browser context has no SubtleCrypto (it needs https, localhost or 127.0.0.1), " +
        "so the hashes were not checked.",
    };
  }
  let root: JsonNode;
  try {
    root = parseJsonLossless(text);
  } catch (error) {
    return { status: "malformed", reason: error instanceof Error ? error.message : String(error) };
  }
  if (root.kind !== "object") return { status: "malformed", reason: "The trace is not an object." };
  const frames = getEntry(root, "frames");
  const integrity = getEntry(root, "integrity");
  if (frames === undefined || frames.kind !== "array") {
    return { status: "malformed", reason: "The trace has no frames array." };
  }
  if (integrity === undefined || integrity.kind !== "object") {
    return { status: "malformed", reason: "The trace has no integrity block." };
  }
  const listedNode = getEntry(integrity, "frame_hashes");
  const listed: (string | null)[] =
    listedNode !== undefined && listedNode.kind === "array"
      ? listedNode.items.map((item) => stringOf(item))
      : [];

  const frameResults: FrameHashResult[] = [];
  for (let index = 0; index < frames.items.length; index += 1) {
    const actual = await sha256Hex(canonicalJson(frames.items[index] as JsonNode));
    const expected = listed[index] ?? null;
    frameResults.push({ index, expected, actual, ok: expected === actual });
  }
  const framesOk =
    listed.length === frames.items.length && frameResults.every((result) => result.ok);

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
  const chain = { expected: chainExpected, actual: chainActual, ok: chainExpected === chainActual };
  const content = {
    expected: contentExpected,
    actual: contentActual,
    ok: contentExpected === contentActual,
  };
  return {
    status: "checked",
    ok: algorithmOk && framesOk && chain.ok && content.ok,
    algorithm,
    algorithmOk,
    frameCount: frames.items.length,
    listedFrameHashes: listed.length,
    frames: frameResults,
    framesOk,
    chain,
    content,
  };
}

/** Structural checks before the board renders a trace's frames. */
export function traceShapeProblems(value: unknown): string[] {
  const problems: string[] = [];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return ["The file is not a JSON object."];
  }
  const trace = value as Partial<SanitizedTrace>;
  if (trace.kind !== "plan_b_sanitized_trace") {
    problems.push(`kind is ${JSON.stringify(trace.kind)}, expected "plan_b_sanitized_trace".`);
  }
  if (trace.trace_version !== "1.0.0") {
    problems.push(`trace_version is ${JSON.stringify(trace.trace_version)}, expected "1.0.0".`);
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
