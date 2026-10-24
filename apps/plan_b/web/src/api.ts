// Typed client for the Plan B HTTP API (contract section 3). This module holds every request
// that can change server state (sign-in, tool calls, moderator controls). The replay module
// must not import it; replay has its own read-only loader in src/replay/loader.ts.
//
// Identity is the bearer token of this browser tab only (sessionStorage). Request bodies never
// carry actor ids; the server derives actor, role and grant from the session.

import type {
  ClockAdvanceResult,
  EventStateView,
  ExportResult,
  IssuedSession,
  JoinAuthResponse,
  JsonObject,
  LoadedEpisode,
  ModeratorAuthResponse,
  ModeratorCase,
  ModeratorCurrent,
  PolicyRunResult,
  RunMinutesResult,
  SessionRole,
  ToolEnvelope,
  ToolName,
  ToolRequest,
  WhoAmIResponse,
} from "./types";

export const SESSION_STORAGE_KEY = "planb.session";

/** The deterministic rule policy (P0) that moderator runs drive. */
export const DETERMINISTIC_POLICY_ID = "rules/1.0.0";

/** The public fixture loaded by the moderator (contract: scenario "dev_fixture_01"). */
export const DEFAULT_SCENARIO_ID = "dev_fixture_01";

const REQUEST_TIMEOUT_MS = 20_000;

export interface StoredSession {
  readonly token: string;
  readonly role: SessionRole;
  readonly principal_id: string;
  readonly display_name: string | null;
  readonly episode_id: string | null;
  readonly event_id: string | null;
  readonly grant_id: string | null;
  readonly expires_wall: string | null;
}

/** event_id and grant_id that every tool request carries (never an actor id). */
export interface ToolBinding {
  readonly event_id: string;
  readonly grant_id: string | null;
}

const SESSION_ROLES: readonly SessionRole[] = [
  "organizer",
  "coordinator_agent",
  "participant",
  "moderator",
];

const optionalString = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

export function loadSession(): StoredSession | null {
  let raw: string | null;
  try {
    raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const role = parsed.role as SessionRole;
    if (typeof parsed.token !== "string" || parsed.token.length === 0) return null;
    if (!SESSION_ROLES.includes(role) || typeof parsed.principal_id !== "string") return null;
    return {
      token: parsed.token,
      role,
      principal_id: parsed.principal_id,
      display_name: optionalString(parsed.display_name),
      episode_id: optionalString(parsed.episode_id),
      event_id: optionalString(parsed.event_id),
      grant_id: optionalString(parsed.grant_id),
      expires_wall: optionalString(parsed.expires_wall),
    };
  } catch {
    return null;
  }
}

export function saveSession(session: StoredSession): void {
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage can be unavailable (private mode). The session then lasts for this page only.
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Nothing stored.
  }
}

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

/** The `code` of an error body: `{detail: {code}}` (FastAPI) or `{error: {code}}` (envelope). */
export function errorCodeOf(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const record = body as Record<string, unknown>;
  for (const key of ["error", "detail"]) {
    const inner = record[key];
    if (typeof inner === "object" && inner !== null && !Array.isArray(inner)) {
      const code = (inner as Record<string, unknown>).code;
      if (typeof code === "string") return code;
    }
  }
  return null;
}

/** The server answered with a client error: the request was refused, not executed. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  readonly code: string | null;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.code = errorCodeOf(body);
  }
}

/** Shown when a role tab's episode was closed by a moderator reset (401 EPISODE_CLOSED). */
export const EPISODE_RESET_MESSAGE = "This episode was reset; ask the moderator for a new link.";

/** Why a 401 ended this tab's session, in words for the person using it. */
export function sessionEndMessage(code: string | null, message: string): string {
  return code === "EPISODE_CLOSED"
    ? EPISODE_RESET_MESSAGE
    : `This tab's session is no longer valid: ${message}`;
}

/** No usable answer (network failure, timeout, server error): the outcome is unknown. */
export class NoResponseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NoResponseError";
  }
}

/** Human-readable text from an error body ({detail}, {error: {code, message}}, ...). */
export function describeErrorBody(body: unknown, status: number): string {
  if (typeof body === "string" && body.trim().length > 0) return body.trim().slice(0, 500);
  if (typeof body === "object" && body !== null) {
    const record = body as Record<string, unknown>;
    const error = record.error;
    if (typeof error === "object" && error !== null) {
      const e = error as Record<string, unknown>;
      if (typeof e.message === "string") {
        return typeof e.code === "string" ? `${e.code}: ${e.message}` : e.message;
      }
    }
    const detail = record.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const d = detail as Record<string, unknown>;
      if (typeof d.message === "string") {
        return typeof d.code === "string" ? `${d.code}: ${d.message}` : d.message;
      }
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "object" && item !== null) {
            const d = item as Record<string, unknown>;
            const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
            return `${loc ? `${loc}: ` : ""}${typeof d.msg === "string" ? d.msg : JSON.stringify(d)}`;
          }
          return String(item);
        })
        .join("; ");
    }
    if (typeof record.message === "string") return record.message;
  }
  return `HTTP ${status}`;
}

interface RawResponse {
  readonly status: number;
  readonly text: string;
  readonly body: unknown;
}

async function send(
  method: "GET" | "POST",
  path: string,
  token: string | null,
  body?: unknown,
): Promise<RawResponse> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token !== null) headers.Authorization = `Bearer ${token}`;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    throw new NoResponseError(
      aborted
        ? `No response within ${REQUEST_TIMEOUT_MS / 1000} s.`
        : "The server could not be reached.",
    );
  } finally {
    window.clearTimeout(timer);
  }
  let text: string;
  try {
    text = await response.text();
  } catch {
    throw new NoResponseError(`The response (HTTP ${response.status}) was cut off.`);
  }
  let parsed: unknown = text;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  return { status: response.status, text, body: parsed };
}

/** JSON request that must succeed with 2xx; otherwise ApiError (4xx) or NoResponseError. */
async function sendJson<T>(
  method: "GET" | "POST",
  path: string,
  token: string | null,
  body?: unknown,
): Promise<T> {
  const raw = await send(method, path, token, body);
  if (raw.status >= 500 || raw.status === 408) {
    throw new NoResponseError(
      `Server error (HTTP ${raw.status}): ${describeErrorBody(raw.body, raw.status)}`,
    );
  }
  if (raw.status < 200 || raw.status >= 300) {
    throw new ApiError(raw.status, describeErrorBody(raw.body, raw.status), raw.body);
  }
  if (typeof raw.body === "string" && raw.text.length > 0) {
    throw new NoResponseError(`The server's reply (HTTP ${raw.status}) was not JSON.`);
  }
  return raw.body as T;
}

// ---------------------------------------------------------------------------
// Authentication and state
// ---------------------------------------------------------------------------

export async function signInModerator(code: string): Promise<StoredSession> {
  const res = await sendJson<ModeratorAuthResponse>("POST", "/api/auth/moderator", null, { code });
  const session: StoredSession = {
    token: res.token,
    role: "moderator",
    principal_id: res.principal_id,
    display_name: null,
    episode_id: null,
    event_id: null,
    grant_id: null,
    expires_wall: optionalString(res.expires_wall),
  };
  saveSession(session);
  return session;
}

export async function exchangeJoinCode(code: string): Promise<StoredSession> {
  const res = await sendJson<JoinAuthResponse>("POST", "/api/auth/join", null, { code });
  const session: StoredSession = {
    token: res.token,
    role: res.role,
    principal_id: res.principal_id,
    display_name: optionalString(res.display_name),
    episode_id: optionalString(res.episode_id),
    event_id: optionalString(res.event_id),
    grant_id: optionalString(res.grant_id),
    expires_wall: null,
  };
  saveSession(session);
  return session;
}

export function whoami(session: StoredSession): Promise<WhoAmIResponse> {
  return sendJson<WhoAmIResponse>("GET", "/api/auth/whoami", session.token);
}

export interface StateRead {
  readonly view: EventStateView;
  /** Raw body, used to skip re-rendering when a poll returns identical state. */
  readonly text: string;
}

export async function readState(session: StoredSession): Promise<StateRead> {
  const raw = await send("GET", "/api/state", session.token);
  if (raw.status >= 500) {
    throw new NoResponseError(`Server error (HTTP ${raw.status}) while reading state.`);
  }
  if (raw.status !== 200) {
    throw new ApiError(raw.status, describeErrorBody(raw.body, raw.status), raw.body);
  }
  if (typeof raw.body !== "object" || raw.body === null) {
    throw new NoResponseError("The state response was not JSON.");
  }
  return { view: raw.body as EventStateView, text: raw.text };
}

// ---------------------------------------------------------------------------
// Tool calls
// ---------------------------------------------------------------------------

export type ToolCallOutcome =
  /** The server produced an envelope (HTTP 200), including business rejections. */
  | { readonly kind: "envelope"; readonly envelope: ToolEnvelope }
  /** Refused before execution (401 session, 400 invalid body, other 4xx). Nothing was done. */
  | {
      readonly kind: "not_executed";
      readonly httpStatus: number;
      readonly code: string | null;
      readonly message: string;
    }
  /** No usable answer. The request may or may not have executed. */
  | { readonly kind: "no_response"; readonly message: string };

function randomUuid(): string {
  const c = globalThis.crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  // randomUUID needs a secure context; getRandomValues does not. Build an RFC 4122 v4 UUID.
  const bytes = c.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** One key per logical submission; retries of that submission reuse it. */
export function newIdempotencyKey(tool: ToolName): string {
  return `web-${tool}-${randomUuid()}`;
}

/**
 * submit_observation `client_record_id`: one per logical observation, kept in the frozen
 * request, so the server stores the observation once however often it arrives.
 */
export function newClientRecordId(): string {
  return `web-obs-${randomUuid()}`;
}

export interface RequestOptions {
  /** Generate an idempotency key (mutations and organizer controls). */
  readonly idempotent?: boolean;
  readonly expectedRevision?: number;
  readonly expectedGoalVersion?: number;
}

/** Build a frozen ToolRequest. The same object must be resent unchanged on a retry. */
export function buildToolRequest(
  binding: ToolBinding,
  tool: ToolName,
  args: JsonObject,
  options: RequestOptions = {},
): ToolRequest {
  const request: ToolRequest = {
    tool,
    event_id: binding.event_id,
    ...(binding.grant_id !== null ? { grant_id: binding.grant_id } : {}),
    ...(options.idempotent === true ? { idempotency_key: newIdempotencyKey(tool) } : {}),
    ...(options.expectedRevision !== undefined
      ? { expected_revision: options.expectedRevision }
      : {}),
    ...(options.expectedGoalVersion !== undefined
      ? { expected_goal_version: options.expectedGoalVersion }
      : {}),
    arguments: args,
  };
  return Object.freeze(request);
}

function looksLikeEnvelope(body: unknown): body is ToolEnvelope {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  return typeof b.status === "string" && typeof b.call_id === "string" && "tool" in b;
}

export async function callTool(session: StoredSession, request: ToolRequest): Promise<ToolCallOutcome> {
  let raw: RawResponse;
  try {
    raw = await send("POST", `/api/tools/${encodeURIComponent(request.tool)}`, session.token, request);
  } catch (error) {
    return {
      kind: "no_response",
      message: error instanceof Error ? error.message : "The request failed.",
    };
  }
  if (raw.status === 200 && looksLikeEnvelope(raw.body)) {
    return { kind: "envelope", envelope: raw.body };
  }
  if (raw.status >= 400 && raw.status < 500 && raw.status !== 408) {
    return {
      kind: "not_executed",
      httpStatus: raw.status,
      code: errorCodeOf(raw.body),
      message: describeErrorBody(raw.body, raw.status),
    };
  }
  return {
    kind: "no_response",
    message:
      raw.status === 200
        ? "The server replied without a readable envelope."
        : `Server error (HTTP ${raw.status}): ${describeErrorBody(raw.body, raw.status)}`,
  };
}

/** get_action_receipt for one of this session's own submissions, by its original key. */
export function lookupReceipt(
  session: StoredSession,
  binding: ToolBinding,
  idempotencyKey: string,
): Promise<ToolCallOutcome> {
  const request = buildToolRequest(binding, "get_action_receipt", {
    idempotency_key: idempotencyKey,
  });
  return callTool(session, request);
}

// ---------------------------------------------------------------------------
// Moderator controls (sandbox operator; not event tools, no idempotency keys)
// ---------------------------------------------------------------------------

export const moderatorApi = {
  cases(session: StoredSession): Promise<ModeratorCase[]> {
    return sendJson<ModeratorCase[]>("GET", "/api/moderator/cases", session.token);
  },
  current(session: StoredSession): Promise<ModeratorCurrent | null> {
    return sendJson<ModeratorCurrent | null>("GET", "/api/moderator/current", session.token);
  },
  loadEpisode(session: StoredSession, scenarioId: string, caseRef: string): Promise<LoadedEpisode> {
    return sendJson<LoadedEpisode>("POST", "/api/moderator/episodes", session.token, {
      scenario_id: scenarioId,
      case_ref: caseRef,
    });
  },
  issueSession(session: StoredSession, principalId: string): Promise<IssuedSession> {
    return sendJson<IssuedSession>("POST", "/api/moderator/sessions", session.token, {
      principal_id: principalId,
    });
  },
  advanceClock(session: StoredSession, minutes: number): Promise<ClockAdvanceResult> {
    return sendJson<ClockAdvanceResult>("POST", "/api/moderator/clock", session.token, {
      advance_minutes: minutes,
    });
  },
  runPolicy(session: StoredSession, maxToolCalls?: number): Promise<PolicyRunResult> {
    return sendJson<PolicyRunResult>(
      "POST",
      "/api/moderator/policy/run",
      session.token,
      maxToolCalls === undefined ? {} : { max_tool_calls: maxToolCalls },
    );
  },
  /** Advance minute by minute; with `policy`, the deterministic policy runs on public changes. */
  runMinutes(session: StoredSession, minutes: number, policy: boolean): Promise<RunMinutesResult> {
    return sendJson<RunMinutesResult>("POST", "/api/moderator/run", session.token, {
      minutes,
      policy,
    });
  },
  exportTrace(session: StoredSession): Promise<ExportResult> {
    return sendJson<ExportResult>("POST", "/api/moderator/export", session.token, {});
  },
};
