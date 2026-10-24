// Read-only loader for sanitized traces. It issues GET requests only, sends no credentials,
// and does not import src/api.ts: a replay can never call a tool or a moderator control.

import type { SanitizedTrace } from "../types";
import { decodeTraceBytes, traceShapeProblems } from "./integrity";

export interface LoadedTrace {
  /** Where the trace came from, for the banner ("server: name" or "file: name"). */
  readonly origin: string;
  /** Exact text, which the integrity check hashes. */
  readonly text: string;
  readonly trace: SanitizedTrace;
}

/**
 * The loader's only fetch options: a GET with no body, no headers and no credentials. The browser
 * reads every RequestInit key from the options, inherited ones included, so a `body` or `headers`
 * key, or a getter that rewrites `method` while the keys are read, that any module put on
 * Object.prototype would otherwise reach the request. With no prototype the options have only
 * these own keys, and frozen, nothing can add or change one. The boundary lint requires this
 * construction and holds the keys to an allowlist, with the method stated: an explicit "GET" also
 * overrides the method of a Request input.
 */
const GET_ONLY: RequestInit = Object.freeze(
  Object.assign(Object.create(null) as RequestInit, {
    method: "GET",
    cache: "no-store",
    credentials: "omit",
  } satisfies RequestInit),
);

/** The response body's exact bytes: response.text() would drop a leading byte order mark. */
async function getBytes(path: string): Promise<Uint8Array> {
  let response: Response;
  try {
    response = await fetch(path, GET_ONLY);
  } catch {
    throw new Error("The server could not be reached.");
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (!response.ok) {
    const text = new TextDecoder().decode(bytes);
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 300) || response.statusText}`);
  }
  return bytes;
}

/** Names of the traces the server offers. Accepts a list of names or of {name} objects. */
export async function listReplays(): Promise<string[]> {
  const text = new TextDecoder().decode(await getBytes("/api/replays"));
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new Error("The replay list was not JSON.");
  }
  const items: unknown =
    typeof body === "object" && body !== null && !Array.isArray(body)
      ? ((body as Record<string, unknown>).replays ?? (body as Record<string, unknown>).names)
      : body;
  if (!Array.isArray(items)) throw new Error("The replay list has an unexpected shape.");
  return items.map((item) => {
    if (typeof item === "string") return item;
    if (typeof item === "object" && item !== null) {
      const name = (item as Record<string, unknown>).name;
      if (typeof name === "string") return name;
    }
    throw new Error("The replay list has an entry without a name.");
  });
}

export function parseTrace(text: string, origin: string): LoadedTrace {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new Error(`Not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  const problems = traceShapeProblems(value);
  if (problems.length > 0) throw new Error(`Not a Plan B trace: ${problems.join(" ")}`);
  return { origin, text, trace: value as SanitizedTrace };
}

/**
 * Decode a trace file's exact bytes, then parse it. A byte order mark or bytes that are not
 * UTF-8 are rejected here, as `plan-b verify-trace` rejects them, so such a file never renders.
 */
export function parseTraceBytes(bytes: Uint8Array, origin: string): LoadedTrace {
  return parseTrace(decodeTraceBytes(bytes), origin);
}

export async function loadServerReplay(name: string): Promise<LoadedTrace> {
  return parseTraceBytes(await getBytes(`/api/replays/${encodeURIComponent(name)}`), `server: ${name}`);
}

export async function loadLocalReplay(file: File): Promise<LoadedTrace> {
  // file.text() would drop a leading byte order mark as well.
  return parseTraceBytes(new Uint8Array(await file.arrayBuffer()), `file: ${file.name}`);
}
