// Recorded replay. Reads a sanitized trace (server list or local file), verifies its hashes in
// the browser, and steps through its frames rendering the same board read-only. Nothing here
// imports src/api.ts or the role panels: a replay cannot issue a tool or moderator call.

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { BoardView } from "../board/BoardView";
import { PRODUCT_NAME, SANDBOX_NOTICE } from "../components/BoardHeader";
import { EvidenceCard } from "../components/EvidenceCard";
import { Code, Empty, Section, Tag, When } from "../components/ui";
import { fmtTime } from "../format";
import type { CompactedStateView, EventStateView, SanitizedTrace, ToolCallRecord } from "../types";

/** Restore a frame's latest_evaluation from the trace's evaluations map (traces store each
 * evaluation once). A missing reference shows no evaluation rather than a guessed one. */
function rehydrateState(trace: SanitizedTrace, state: CompactedStateView): EventStateView {
  const latest = state.latest_evaluation;
  if (latest !== null && "evaluation_ref" in latest) {
    return { ...state, latest_evaluation: trace.evaluations?.[latest.evaluation_ref] ?? null };
  }
  return { ...state, latest_evaluation: latest };
}
import { CHAIN_FOLD_DESCRIPTION, verifyTraceText } from "./integrity";
import type { IntegrityReport } from "./integrity";
import { listReplays, loadLocalReplay, loadServerReplay } from "./loader";
import type { LoadedTrace } from "./loader";

const PLAY_MS = 1500;

function IntegrityPanel({ report }: { report: IntegrityReport | "checking" }) {
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
      <p className="notice tone-bad">
        <span aria-hidden="true">✖ </span>
        <strong>Integrity check failed:</strong> {report.reason}
      </p>
    );
  }
  const failedFrames = report.frames.filter((f) => !f.ok);
  return (
    <div className={`notice ${report.ok ? "tone-ok" : "tone-bad"}`}>
      <p>
        <span aria-hidden="true">{report.ok ? "✔ " : "✖ "}</span>
        <strong>{report.ok ? "Integrity check passed." : "Integrity check failed."}</strong> Hashes were
        recomputed in this browser (SHA-256 of canonical JSON).
      </p>
      <ul className="small">
        <li>
          {report.algorithmOk ? "✓" : "✖"} Algorithm: {report.algorithm ?? "missing"}
        </li>
        <li>
          {report.framesOk ? "✓" : "✖"} Frame hashes: {report.frameCount - failedFrames.length} of {report.frameCount}{" "}
          match
          {report.listedFrameHashes !== report.frameCount
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
      </ul>
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
              Recorded at {at !== null ? <When iso={at} text={fmtTime(at, tz)} /> : "an unrecorded time"} — not re-queried
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
  const loadSeq = useRef(0);

  const accept = useCallback((trace: LoadedTrace) => {
    loadSeq.current += 1;
    const seq = loadSeq.current;
    setLoaded(trace);
    setLoadError(null);
    setIndex(0);
    setShowFinal(false);
    setPlaying(false);
    setIntegrity("checking");
    void verifyTraceText(trace.text).then((report) => {
      if (loadSeq.current === seq) setIntegrity(report);
    });
  }, []);

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

  const frame = trace !== null && frameCount > 0 ? trace.frames[Math.min(index, last)] ?? null : null;
  const state =
    trace === null ? null : showFinal ? trace.final_state : frame !== null ? rehydrateState(trace, frame.state) : null;
  const tz = state?.timezone ?? "UTC";
  const callsSoFar =
    trace === null
      ? []
      : showFinal || frame === null
        ? trace.tool_calls
        : trace.tool_calls.filter((c) => c.revision_after === null || c.revision_after <= frame.revision);

  const controls =
    trace !== null ? (
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
            Showing the final recorded state (revision {trace.final_state.revision}).
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
    ) : null;

  return (
    <main id="main" className="page replay">
      <div className="replay-banner" role="status">
        <span className="replay-banner-title">
          <span aria-hidden="true">▸ </span>Recorded replay
        </span>
        <span>
          Not live. This page plays back a saved trace and never calls tools. {PRODUCT_NAME} · {SANDBOX_NOTICE}
        </span>
        <a className="button secondary small" href="#/">
          Leave replay
        </a>
      </div>
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
            <p className="small">
              Loaded <strong>{loaded.origin}</strong> · trace {trace.trace_version}, runtime {trace.runtime_version} ·
              episode <Code>{trace.source.episode_id}</Code> · scenario <Code>{trace.source.scenario_id}</Code> ·
              policy <Code>{trace.source.policy_id ?? "none recorded"}</Code> · {frameCount} frames,{" "}
              {trace.tool_calls.length} tool calls, {trace.receipts.length} receipts
            </p>
            {integrity !== null ? <IntegrityPanel report={integrity} /> : null}
          </>
        ) : null}
      </Section>
      {state !== null ? (
        <BoardView view={state} mode="replay" beforeGrid={controls} />
      ) : trace !== null ? (
        controls
      ) : null}
    </main>
  );
}
