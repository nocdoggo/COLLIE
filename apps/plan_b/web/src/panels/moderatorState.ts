// Moderator panel rules, kept free of React so tests can check them.
//
// * Loading a case closes the active episode and signs out its role tabs, so it is confirmed
//   whenever an episode might be active: an unanswered or failed current-episode read counts as
//   "maybe", and the board's own state is evidence too.
// * An action result is labeled with the action and the scenario time it ran, so an old result
//   never reads as the current state.

import { fmtTime } from "../format";
import type { EventStateView, PolicyRunResult, UtcIso } from "../types";

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
