// Moderator panel rules, kept free of React so tests can check them.
//
// * Loading a case closes the active episode and signs out its role tabs, so it is confirmed
//   whenever an episode might be active: an unanswered or failed current-episode read counts as
//   "maybe", and the board's own state is evidence too.
// * An action result is labeled with the action and the scenario time it ran, so an old result
//   never reads as the current state.
// * A one-time join code is never shown whole: the page shows a short prefix, and only the link's
//   href carries the full code.

import { DETERMINISTIC_POLICY_LABEL, fmtTime, liveAgentLabel } from "../format";
import type { PolicySelection } from "../components/policyMode";
import type {
  EpisodePolicy,
  EventStateView,
  ModeratorCase,
  PolicyChoice,
  PolicyRunResult,
  PolicySetting,
  UtcIso,
} from "../types";

/** GET /api/moderator/current: an id, null (none), or undefined (no answer yet, or it failed). */
export type CurrentEpisode = string | null | undefined;

type BoardEpisode = Pick<EventStateView, "episode_id" | "episode_status"> | null;

export function resetNeedsConfirmation(current: CurrentEpisode, board: BoardEpisode): boolean {
  return current !== null || board?.episode_status === "active";
}

/** The active episode as best known: the server's answer, else the board's own state read. */
export function knownActiveEpisode(current: CurrentEpisode, board: BoardEpisode): string | null {
  if (typeof current === "string") return current;
  return board?.episode_status === "active" ? board.episode_id : null;
}

/** Which action produced a result, and the scenario clock the board showed when it ran. */
export interface ActionStamp {
  readonly action: string;
  readonly ranAt: UtcIso | null;
}

export interface Stamped<T> extends ActionStamp {
  readonly result: T;
}

function time(iso: UtcIso, tz: string | null): string {
  return tz !== null ? fmtTime(iso, tz) : iso;
}

/** "+1 min at 16:40 → clock 16:41, revision 3". */
export function actionHeadline(stamp: ActionStamp, outcome: string, tz: string | null): string {
  const at = stamp.ranAt !== null ? ` at ${time(stamp.ranAt, tz)}` : "";
  return `${stamp.action}${at} → ${outcome}`;
}

/** "clock 16:41, revision 3", leaving out what the server did not report. */
export function clockOutcome(clock: UtcIso | undefined, revision: number | undefined, tz: string | null): string {
  const parts = [
    ...(clock !== undefined ? [`clock ${time(clock, tz)}`] : []),
    ...(revision !== undefined ? [`revision ${revision}`] : []),
  ];
  return parts.length > 0 ? parts.join(", ") : "finished";
}

/** "waiting after 4 tool calls, until 16:50". */
export function policyOutcome(run: PolicyRunResult, tz: string | null): string {
  const calls = `${run.tool_calls} tool call${run.tool_calls === 1 ? "" : "s"}`;
  const until = run.wait_until !== null ? `, until ${time(run.wait_until, tz)}` : "";
  return `${run.status.replace(/_/g, " ")} after ${calls}${until}`;
}

/** A result whose revision the board has since moved past. */
export function isEarlierResult(resultRevision: number | undefined, view: EventStateView | null): boolean {
  return resultRevision !== undefined && view !== null && view.revision !== resultRevision;
}

/** Characters of a join code the page may show; never more than a quarter of the code. */
export const JOIN_CODE_PREVIEW = 4;

/** "P9Ne…": enough to tell two codes apart, too little to use one. */
export function joinCodePreview(code: string): string {
  return `${code.slice(0, Math.min(JOIN_CODE_PREVIEW, Math.floor(code.length / 4)))}…`;
}

// ---------------------------------------------------------------------------
// Coordinator policy switch
// ---------------------------------------------------------------------------

/** What a policy run button says for the selected policy. */
export const RUN_POLICY_LABEL: Record<PolicyChoice, string> = {
  rules: "Run deterministic policy",
  "tool-use": "Run tool-use agent",
  live: "Run live agent",
  "verify-all": "Run verify-all agent",
};

/** The mode label of each model-driven choice, before the server names the returned model. */
export const MODEL_CHOICE_LABEL: Record<Exclude<PolicyChoice, "rules">, string> = {
  "tool-use": "Tool-use agent",
  live: "Live agent",
  "verify-all": "Verify-all agent",
};

/** The policy id each choice runs (the server's `policy_id` wins when it sent one). */
export const CHOICE_POLICY_ID: Record<Exclude<PolicyChoice, "rules">, string> = {
  "tool-use": "tool-use/1.0.0",
  live: "live/1.0.0",
  "verify-all": "verify-all/1.0.0",
};

/** "<policy label> · <model id>" for a model-driven choice; "Live agent · …" for the live agent. */
export function modelChoiceLabel(choice: Exclude<PolicyChoice, "rules">, modelId: string | null): string {
  return choice === "live" ? liveAgentLabel(modelId) : `${MODEL_CHOICE_LABEL[choice]} · ${modelId ?? "model not reported yet"}`;
}

/** The selection a server setting describes; its model id is the configured one. */
export function selectionOf(setting: EpisodePolicy & { readonly model_id?: string | null }): PolicySelection {
  return {
    choice: setting.policy,
    modelId: setting.policy !== "rules" ? (setting.model_id ?? null) : null,
    label: setting.label ?? null,
  };
}

/** "Deterministic policy" or "<policy label> · <model id>" for a setting (the server's label first). */
export function settingLabel(setting: PolicySetting): string {
  if (typeof setting.label === "string" && setting.label.length > 0) return setting.label;
  return setting.policy !== "rules" ? modelChoiceLabel(setting.policy, setting.model_id ?? null) : DETERMINISTIC_POLICY_LABEL;
}

/**
 * The scenario to load a case on: the one the case list names, else null so the server uses
 * the case's own (a Wave 1 server lists campus cases only and defaults to their scenario).
 */
export function scenarioOfCase(cases: readonly ModeratorCase[] | null, caseRef: string): string | null {
  const row = cases?.find((c) => c.case_ref === caseRef);
  return typeof row?.scenario_id === "string" && row.scenario_id.length > 0 ? row.scenario_id : null;
}
