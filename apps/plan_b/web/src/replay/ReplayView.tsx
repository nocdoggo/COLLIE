// Recorded replay. Reads a sanitized trace (server list or local file), verifies its hashes in
// the browser, and steps through its frames rendering the same board read-only. Nothing here
// imports src/api.ts or the role panels: a replay cannot issue a tool or moderator call.

import { Component, useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";

import { BoardView } from "../board/BoardView";
import { PRODUCT_NAME, SANDBOX_NOTICE } from "../components/BoardHeader";
import { EvidenceCard } from "../components/EvidenceCard";
import { Code, Empty, Section, StatusBadge, Tag, When } from "../components/ui";
import { fmtTime } from "../format";
import type { StatusLabel } from "../format";
import type { CompactedStateView, EvaluationResult, EventStateView, SanitizedTrace, ToolCallRecord } from "../types";
import {
  CHAIN_FOLD_DESCRIPTION,
  checkTraceIntegrity,
  describeError,
  failedStructuralChecks,
  hashesFailed,
  integrityState,
} from "./integrity";
import type { IntegrityReport, IntegrityState } from "./integrity";
import { listReplays, loadLocalReplay, loadServerReplay } from "./loader";
import type { LoadedTrace } from "./loader";

/**
 * Restore a frame's latest_evaluation from the trace's evaluations map (traces store each
 * evaluation once). A missing reference shows no evaluation rather than a guessed one, and so does
 * a frame state that lacks the field or holds something other than an object there (a hand-made
 * or synthetic trace can): rehydration never throws. The reference is looked up as an own key, so
 * "constructor" or "toString" finds nothing.
 */
export function rehydrateState(trace: SanitizedTrace, state: CompactedStateView): EventStateView {
  const latest: unknown = state.latest_evaluation;
  if (typeof latest !== "object" || latest === null) return { ...state, latest_evaluation: null };
  if (!("evaluation_ref" in latest)) return { ...state, latest_evaluation: latest as EvaluationResult };
  const ref: unknown = latest.evaluation_ref;
  const evaluations: unknown = trace.evaluations;
  const found =
    typeof ref === "string" && typeof evaluations === "object" && evaluations !== null && Object.hasOwn(evaluations, ref)
      ? (evaluations as Record<string, EvaluationResult>)[ref]
      : undefined;
  return { ...state, latest_evaluation: found ?? null };
}

export const UNRENDERABLE_NOTICE = "This trace could not be rendered.";

/**
 * The banner's report for a trace the replay could not render: a failed check, whatever its
 * hashes say, as for a verifier that throws.
 */
export const renderFailureReport = (message: string): IntegrityReport => ({
  status: "malformed",
  reason: `${UNRENDERABLE_NOTICE} ${message}`,
});

/** What the replay shows in place of the board when rendering the trace failed. */
export function UnrenderableNotice({ message }: { message: string }) {
  return (
    <div className="notice tone-bad" role="alert" data-replay-render="failed">
      <p>
        <span aria-hidden="true">✖ </span>
        <strong>{UNRENDERABLE_NOTICE}</strong> Rendering it failed with: {message}
      </p>
      <p className="small">
        The board is not shown, and the replay counts the trace as failed, whatever its hashes say. The
        Trace card above still lists its hash checks; open another trace to continue.
      </p>
    </div>
  );
}

/** Calls its render function, so that what the function throws is thrown inside the guard. */
function Deferred({ render }: { render: () => ReactNode }) {
  return <>{render()}</>;
}

interface RenderGuardProps {
  /** Called once with the error's message when rendering the guarded part fails. */
  readonly onError: (message: string) => void;
  /** Shown in place of the guarded part after a failure. */
  readonly fallback: (message: string) => ReactNode;
  /** Renders the guarded part. It runs inside the guard, so what it throws is caught too. */
  readonly children: () => ReactNode;
}

interface RenderGuardState {
  /** The message of the error that stopped rendering, or null. */
  readonly error: string | null;
}

/**
 * An error boundary for the parts of the replay that render trace data. A trace whose shape the
 * board does not expect would otherwise unmount the whole page, leaving it blank with no
 * integrity banner; the guard shows its fallback instead and reports the failure, so the replay
 * marks the trace as failed. React calls the boundary methods only in a browser, not in
 * server rendering.
 */
export class ReplayRenderGuard extends Component<RenderGuardProps, RenderGuardState> {
  override state: RenderGuardState = { error: null };

  static getDerivedStateFromError(error: unknown): RenderGuardState {
    return { error: describeError(error) };
  }

  override componentDidCatch(error: unknown): void {
    this.props.onError(describeError(error));
  }

  override render(): ReactNode {
    const { error } = this.state;
    return error !== null ? this.props.fallback(error) : <Deferred render={this.props.children} />;
  }
}

const PLAY_MS = 1500;

/** What a passing check can and cannot show (review WEB-2). */
export const UNSIGNED_NOTE =
  "The hashes are not signed, so this check detects corruption, not deliberate edits: whoever " +
  "edits a trace can recompute them.";

export const UNTRUSTED_BOARD_NOTICE = "Integrity check failed: the values below may not be what was recorded.";

const BANNER_INTEGRITY: Record<IntegrityState, StatusLabel> = {
  checking: { text: "Integrity: checking…", icon: "⧗", tone: "info" },
  passed: { text: "Integrity check passed (hashes not signed)", icon: "✔", tone: "ok" },
  failed: { text: "Integrity check failed: values may not be what was recorded", icon: "✖", tone: "bad" },
  not_checked: { text: "Integrity not checked", icon: "?", tone: "warn" },
};

const RECOMPUTED = "recomputed in this browser (SHA-256 of canonical JSON)";

/**
 * The sentence after "Integrity check passed." or "Integrity check failed.". A failure names
 * what failed: the trace's own hashes, or a structural check (the algorithm label, kind, trace
 * version, or the final state's revision against the last frame's), which a trace can fail even
 * when every hash matches.
 */
export function integrityHeadline(report: Extract<IntegrityReport, { status: "checked" }>): string {
  if (report.ok) return `The trace is consistent with its own hashes, ${RECOMPUTED}.`;
  const hashes = hashesFailed(report);
  const structural = failedStructuralChecks(report);
  const verdict = hashes
    ? `The trace is not consistent with its own hashes, ${RECOMPUTED}`
    : "The trace is consistent with its own hashes";
  const checks =
    structural.length > 0 ? `, ${hashes ? "and" : "but"} it fails a structural check: ${structural.join(", ")}` : "";
  return `${verdict}${checks}. The values on the board may not be what was recorded.`;
}

export function IntegrityPanel({ report }: { report: IntegrityReport | "checking" }) {
  if (report === "checking") return <p className="notice tone-info">Checking integrity hashes…</p>;
  if (report.status === "unavailable") {
    return (
      <p className="notice tone-warn">
        <span aria-hidden="true">? </span>
        <strong>Integrity not checked.</strong> {report.reason}
      </p>
    );
  }
  if (report.status === "malformed") {
    return (
      <div className="notice tone-bad">
        <p>
          <span aria-hidden="true">✖ </span>
          <strong>Integrity check failed:</strong> {report.reason}
        </p>
        <p className="small">The values on the board may not be what was recorded.</p>
      </div>
    );
  }
  const failedFrames = report.frames.filter((f) => !f.ok);
  const revision = report.finalRevision;
  return (
    <div className={`notice ${report.ok ? "tone-ok" : "tone-bad"}`}>
      <p>
        <span aria-hidden="true">{report.ok ? "✔ " : "✖ "}</span>
        <strong>{report.ok ? "Integrity check passed." : "Integrity check failed."}</strong>{" "}
        {integrityHeadline(report)}
      </p>
      <p className="small">{UNSIGNED_NOTE}</p>
      <ul className="small">
        <li>
          {report.algorithmOk ? "✓" : "✖"} Algorithm: {report.algorithm ?? "missing"}
        </li>
        <li>
          {report.kindOk ? "✓" : "✖"} Kind: {report.kind ?? "missing"}
        </li>
        <li>
          {report.traceVersionOk ? "✓" : "✖"} Trace version: {report.traceVersion ?? "missing"}
        </li>
        <li>
          {report.framesOk ? "✓" : "✖"} Frame hashes: {report.frameCount - failedFrames.length} of {report.frameCount}{" "}
          match
          {report.listedFrameHashes === null
            ? " (the trace's integrity.frame_hashes is missing or not a list)"
            : report.listedFrameHashes !== report.frameCount
              ? ` (the trace lists ${report.listedFrameHashes} hashes for ${report.frameCount} frames)`
              : ""}
          {failedFrames.length > 0 ? `; mismatched frames: ${failedFrames.map((f) => f.index + 1).join(", ")}` : ""}
        </li>
        <li>
          {report.chain.ok ? "✓" : "✖"} Chain hash ({CHAIN_FOLD_DESCRIPTION})
        </li>
        <li>
          {report.content.ok ? "✓" : "✖"} Content hash (everything except the integrity block)
        </li>
        <li>
          {revision.ok ? "✓" : "✖"}{" "}
          {report.frameCount === 0
            ? "Final state: no frames to compare it with"
            : `Final state revision ${revision.finalState ?? "missing"} ${revision.ok ? "matches" : "differs from"} the last frame's (${revision.lastFrame ?? "missing"})`}
        </li>
      </ul>
    </div>
  );
}

/** The sticky replay banner, with the integrity state once a trace is loaded. */
export function ReplayBanner({ integrity }: { integrity: IntegrityReport | "checking" | null }) {
  const state = integrity !== null ? integrityState(integrity) : null;
  return (
    <div className="replay-banner" role="status">
      <span className="replay-banner-title">
        <span aria-hidden="true">▸ </span>Recorded replay
      </span>
      <span>
        Not live. This page plays back a saved trace and never calls tools. {PRODUCT_NAME} · {SANDBOX_NOTICE}
      </span>
      {state !== null ? (
        <span className="replay-integrity" data-integrity={state}>
          <StatusBadge label={BANNER_INTEGRITY[state]} />
        </span>
      ) : null}
      <a className="button secondary small" href="#/">
        Leave replay
      </a>
    </div>
  );
}

/**
 * The board of a trace that failed its integrity check stays viewable but is marked: a notice
 * above it, a dashed outline, and dimmed sections (the frame controls stay at full strength).
 */
export function ReplayBoardFrame({ failed, children }: { failed: boolean; children: ReactNode }) {
  if (!failed) return <>{children}</>;
  return (
    <div className="board-untrusted" data-integrity="failed">
      <p className="notice tone-bad board-untrusted-notice">
        <span aria-hidden="true">✖ </span>
        <strong>{UNTRUSTED_BOARD_NOTICE}</strong> They stay viewable so the trace can be inspected;
        the Trace card lists the checks that failed.
      </p>
      {children}
    </div>
  );
}

function RecordedToolCalls({ calls, tz }: { calls: readonly ToolCallRecord[]; tz: string }) {
  if (calls.length === 0) return <Empty>No tool calls were recorded up to this frame.</Empty>;
  return (
    <ol className="tool-calls">
      {[...calls].reverse().map((c) => {
        const data = (c.envelope as { data?: Record<string, unknown> | null }).data ?? null;
        const freshness =
          c.tool === "query_status" && data !== null && typeof data.freshness === "object" && data.freshness !== null
            ? (data.freshness as { age_minutes?: number; stale?: boolean })
            : null;
        const reason = c.tool === "query_status" && data !== null && typeof data.reason === "string" ? data.reason : null;
        const at = c.completed_at ?? c.requested_at;
        return (
          <li key={c.call_id} className="tool-call">
            <p>
              <strong>{c.tool}</strong> <Tag tone={c.envelope_status === "succeeded" ? "ok" : c.envelope_status === "rejected" ? "bad" : "warn"}>{c.envelope_status}</Tag>{" "}
              <span className="muted small">
                by <Code>{c.actor_id ?? "unknown"}</Code>
                {c.error_code !== null ? ` · ${c.error_code}` : ""}
                {c.receipt_id !== null ? <> · receipt <Code>{c.receipt_id}</Code></> : null}
              </span>
            </p>
            <p className="recorded-label small">
              Recorded at {at !== null ? <When iso={at} text={fmtTime(at, tz)} /> : "an unrecorded time"}, not re-queried
            </p>
            {freshness !== null ? (
              <p className="small">
                Source record was {freshness.age_minutes ?? "?"} min old when retrieved
                {freshness.stale === true ? " (stale for its source)" : ""}.
              </p>
            ) : null}
            {reason !== null ? <p className="small">Reason: {reason}</p> : null}
            <EvidenceCard title="Recorded request and envelope (JSON)" value={{ request: c.request, envelope: c.envelope }} />
          </li>
        );
      })}
    </ol>
  );
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function ReplayView({ initialName }: { initialName: string | null }) {
  const [names, setNames] = useState<string[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<LoadedTrace | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [integrity, setIntegrity] = useState<IntegrityReport | "checking" | null>(null);
  const [index, setIndex] = useState(0);
  const [showFinal, setShowFinal] = useState(false);
  const [playing, setPlaying] = useState(false);
  /** The first render failure of the loaded trace, if any (see ReplayRenderGuard). */
  const [renderError, setRenderError] = useState<string | null>(null);
  /** Counts loads, so that each trace gets fresh render guards. */
  const [loadId, setLoadId] = useState(0);
  const loadSeq = useRef(0);

  const accept = useCallback((trace: LoadedTrace) => {
    loadSeq.current += 1;
    const seq = loadSeq.current;
    setLoaded(trace);
    setLoadId(seq);
    setRenderError(null);
    setLoadError(null);
    setIndex(0);
    setShowFinal(false);
    setPlaying(false);
    setIntegrity("checking");
    // checkTraceIntegrity always settles with a report: a verifier that throws is a failed check.
    void checkTraceIntegrity(trace.text).then((report) => {
      if (loadSeq.current === seq) setIntegrity(report);
    });
  }, []);

  const renderFailed = useCallback((message: string) => setRenderError((first) => first ?? message), []);

  const loadName = useCallback(
    async (name: string) => {
      setLoading(true);
      try {
        accept(await loadServerReplay(name));
      } catch (error) {
        setLoadError(`Could not load ${name}: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        setLoading(false);
      }
    },
    [accept],
  );

  useEffect(() => {
    listReplays().then(setNames, (error: unknown) =>
      setListError(error instanceof Error ? error.message : String(error)),
    );
  }, []);

  useEffect(() => {
    if (initialName !== null) void loadName(initialName);
  }, [initialName, loadName]);

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file === undefined) return;
    setLoading(true);
    try {
      accept(await loadLocalReplay(file));
    } catch (error) {
      setLoadError(`Could not read ${file.name}: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  };

  const trace: SanitizedTrace | null = loaded?.trace ?? null;
  const frameCount = trace?.frames.length ?? 0;
  const last = Math.max(0, frameCount - 1);

  const step = useCallback(
    (delta: number) => {
      if (showFinal) {
        // Leaving the final state goes back to the last frame.
        setShowFinal(false);
        setIndex(last);
        return;
      }
      setIndex((i) => Math.min(last, Math.max(0, i + delta)));
    },
    [last, showFinal],
  );

  useEffect(() => {
    if (trace === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || isTypingTarget(event.target)) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setPlaying(false);
        step(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setPlaying(false);
        step(-1);
      } else if (event.key === "Home") {
        event.preventDefault();
        setPlaying(false);
        setShowFinal(false);
        setIndex(0);
      } else if (event.key === "End") {
        event.preventDefault();
        setPlaying(false);
        setShowFinal(false);
        setIndex(last);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [trace, step, last]);

  useEffect(() => {
    if (!playing) return;
    if (index >= last) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setIndex((i) => Math.min(last, i + 1)), PLAY_MS);
    return () => window.clearTimeout(timer);
  }, [playing, index, last]);

  /**
   * The frame controls and the board for the current frame. It reads the trace's frames, states and
   * tool calls, so it runs inside a ReplayRenderGuard: what it throws on a trace of an unexpected
   * shape is caught there (see the render below).
   */
  const renderBoard = (current: SanitizedTrace): ReactNode => {
    const frame = frameCount > 0 ? (current.frames[Math.min(index, last)] ?? null) : null;
    const state = showFinal ? current.final_state : frame !== null ? rehydrateState(current, frame.state) : null;
    const tz = state?.timezone ?? "UTC";
    const callsSoFar =
      showFinal || frame === null
        ? current.tool_calls
        : current.tool_calls.filter((c) => c.revision_after === null || c.revision_after <= frame.revision);
    const controls = (
      <Section id="replay-controls" title="Frames" className="replay-controls">
        <div className="button-row">
          <button type="button" className="button" onClick={() => step(-1)} disabled={!showFinal && index === 0}>
            <span aria-hidden="true">◀ </span>Previous
          </button>
          <button
            type="button"
            className="button"
            onClick={() => {
              if (index >= last) setIndex(0);
              setShowFinal(false);
              setPlaying(!playing);
            }}
            disabled={frameCount <= 1}
            aria-pressed={playing}
          >
            {playing ? "Pause" : "Play"}
          </button>
          <button type="button" className="button" onClick={() => step(1)} disabled={!showFinal && index >= last}>
            Next<span aria-hidden="true"> ▶</span>
          </button>
          <button
            type="button"
            className="button secondary"
            aria-pressed={showFinal}
            onClick={() => {
              setPlaying(false);
              setShowFinal(!showFinal);
            }}
          >
            {showFinal ? "Back to frames" : "Final recorded state"}
          </button>
        </div>
        {frameCount > 0 ? (
          <label className="field">
            <span>
              Frame {Math.min(index, last) + 1} of {frameCount}
            </span>
            <input
              type="range"
              min={0}
              max={last}
              value={Math.min(index, last)}
              onChange={(e) => {
                setPlaying(false);
                setShowFinal(false);
                setIndex(Number(e.target.value));
              }}
            />
          </label>
        ) : (
          <Empty>This trace has no frames.</Empty>
        )}
        <p className="small muted">Keyboard: ← and → step, Home and End jump.</p>
        {showFinal ? (
          <p className="frame-info" aria-live="polite">
            Showing the final recorded state (revision {current.final_state.revision}).
          </p>
        ) : frame !== null ? (
          <p className="frame-info" aria-live="polite">
            Frame {frame.seq}: revision {frame.revision} at{" "}
            <When iso={frame.scenario_time} text={fmtTime(frame.scenario_time, tz)} /> ·{" "}
            <span className="muted">{frame.cause_kind}</span> {frame.summary}
          </p>
        ) : null}
        <details className="inline-details">
          <summary>Recorded tool calls up to this point ({callsSoFar.length})</summary>
          <RecordedToolCalls calls={callsSoFar} tz={tz} />
        </details>
      </Section>
    );
    if (state === null) return controls;
    return (
      <ReplayBoardFrame failed={integrity !== null && integrityState(integrity) === "failed"}>
        <BoardView view={state} mode="replay" beforeGrid={controls} />
      </ReplayBoardFrame>
    );
  };

  // A render failure counts as a failed check: the banner says so, and a notice replaces the board.
  const bannerIntegrity = loaded === null ? null : renderError !== null ? renderFailureReport(renderError) : integrity;
  return (
    <main id="main" className="page replay">
      <ReplayBanner integrity={bannerIntegrity} />
      <Section id="replay-source" title="Trace">
        <div className="replay-source">
          <div>
            <h3 className="list-heading">Saved on the server</h3>
            {listError !== null ? (
              <p className="notice tone-bad">Could not list replays: {listError}</p>
            ) : names === null ? (
              <p className="muted">Loading the list…</p>
            ) : names.length === 0 ? (
              <Empty>No traces have been exported yet.</Empty>
            ) : (
              <ul className="replay-names">
                {names.map((name) => (
                  <li key={name}>
                    <button
                      type="button"
                      className="link-button"
                      disabled={loading}
                      aria-current={loaded?.origin === `server: ${name}` ? "true" : undefined}
                      onClick={() => void loadName(name)}
                    >
                      {name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="list-heading">From this computer</h3>
            <label className="field">
              <span>Open a trace JSON file</span>
              <input type="file" accept="application/json,.json" onChange={(e) => void onFile(e)} />
            </label>
          </div>
        </div>
        {loadError !== null ? (
          <p className="notice tone-bad" role="alert">
            {loadError}{" "}
            <button type="button" className="link-button" onClick={() => setLoadError(null)}>
              Dismiss
            </button>
          </p>
        ) : null}
        {loaded !== null && trace !== null ? (
          <>
            <ReplayRenderGuard key={`summary-${loadId}`} onError={renderFailed} fallback={() => null}>
              {() => (
                <p className="small">
                  Loaded <strong>{loaded.origin}</strong> · trace {trace.trace_version}, runtime {trace.runtime_version}{" "}
                  · episode <Code>{trace.source.episode_id}</Code> · scenario <Code>{trace.source.scenario_id}</Code> ·
                  policy <Code>{trace.source.policy_id ?? "none recorded"}</Code> · {frameCount} frames,{" "}
                  {trace.tool_calls.length} tool calls, {trace.receipts.length} receipts
                </p>
              )}
            </ReplayRenderGuard>
            {integrity !== null ? <IntegrityPanel report={integrity} /> : null}
          </>
        ) : null}
      </Section>
      {trace === null ? null : renderError !== null ? (
        <UnrenderableNotice message={renderError} />
      ) : (
        <ReplayRenderGuard
          key={`board-${loadId}`}
          onError={renderFailed}
          fallback={(message) => <UnrenderableNotice message={message} />}
        >
          {() => renderBoard(trace)}
        </ReplayRenderGuard>
      )}
    </main>
  );
}
