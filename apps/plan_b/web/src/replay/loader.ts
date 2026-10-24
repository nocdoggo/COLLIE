// Read-only loader for sanitized traces. It issues GET requests only, sends no credentials,
// and does not import src/api.ts: a replay can never call a tool or a moderator control.

import type { SanitizedTrace } from "../types";
import { traceShapeProblems } from "./integrity";

export interface LoadedTrace {
  /** Where the trace came from, for the banner ("server: name" or "file: name"). */
  readonly origin: string;
  /** Exact text, which the integrity check hashes. */
  readonly text: string;
  readonly trace: SanitizedTrace;
}

async function getText(path: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
    });
  } catch {
    throw new Error("The server could not be reached.");
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 300) || response.statusText}`);
  }
  return text;
}

/** Names of the traces the server offers. Accepts a list of names or of {name} objects. */
export async function listReplays(): Promise<string[]> {
  const text = await getText("/api/replays");
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

export async function loadServerReplay(name: string): Promise<LoadedTrace> {
  const text = await getText(`/api/replays/${encodeURIComponent(name)}`);
  return parseTrace(text, `server: ${name}`);
}

export async function loadLocalReplay(file: File): Promise<LoadedTrace> {
  const text = await file.text();
  return parseTrace(text, `file: ${file.name}`);
}
