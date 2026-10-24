import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, DEFAULT_SCENARIO_ID, DETERMINISTIC_POLICY_ID, NoResponseError, moderatorApi } from "../api";
import type { StoredSession } from "../api";
import { EvidenceCard } from "../components/EvidenceCard";
import { loadServerReplay } from "../replay/loader";
import { Code, Empty, Section, StatusBadge, Tag } from "../components/ui";
import { DECISION_LABEL, fmtWall } from "../format";
import type {
  ClockAdvanceResult,
  EventStateView,
  ExportResult,
  IssuedSession,
  PolicyRunResult,
  RunMinutesResult,
} from "../types";
import {
  actionHeadline,
  clockOutcome,
  isEarlierResult,
  knownActiveEpisode,
  policyOutcome,
  resetNeedsConfirmation,
} from "./moderatorState";
import type { ActionStamp, CurrentEpisode, Stamped } from "./moderatorState";

const FALLBACK_PRINCIPALS = [
  { id: "organizer_demo", label: "Event organizer" },
  { id: "participant_facilitator", label: "Skills facilitator" },
  { id: "participant_presenter", label: "Demonstration lead" },
  { id: "participant_host", label: "Event host" },
];

interface ErrorNote {
  readonly id: number;
  readonly text: string;
}

function joinUrl(code: string): string {
  return `${window.location.origin}${window.location.pathname}#/join/${encodeURIComponent(code)}`;
}

function EarlierNote({ revision, view }: { revision: number | undefined; view: EventStateView | null }) {
  if (!isEarlierResult(revision, view) || view === null) return null;
  return <p className="muted small">Earlier result: the board now shows revision {view.revision}.</p>;
}

/** One policy run; `headline` (the stamped action) replaces the plain status line. */
function PolicyRunSummary({ run, tz, headline }: { run: PolicyRunResult; tz: string | null; headline?: string }) {
  return (
    <div className="result">
      <p>
        {headline !== undefined ? <strong>{headline}</strong> : null}
        {headline !== undefined ? " · policy " : "Policy "}
        <Code>{run.policy_id}</Code>
        {headline !== undefined ? "." : `: ${policyOutcome(run, tz)}.`}
        {run.note ? ` ${run.note}` : ""}
      </p>
      {run.decisions.length > 0 ? (
        <ol className="small">
          {run.decisions.map((d) => (
            <li key={d.decision_id}>
              <StatusBadge label={DECISION_LABEL[d.kind]} /> {d.summary}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export function ModeratorPanel({
  session,
  view,
  track,
  refresh,
  announce,
}: {
  session: StoredSession;
  view: EventStateView | null;
  track: <T>(run: () => Promise<T>) => Promise<T>;
  refresh: () => Promise<EventStateView | null>;
  announce: (text: string) => void;
}) {
  const [cases, setCases] = useState<string[] | null>(null);
  const [caseRef, setCaseRef] = useState("");
  const [current, setCurrent] = useState<CurrentEpisode>(undefined);
  const [currentFailure, setCurrentFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmLoad, setConfirmLoad] = useState(false);
  const [errors, setErrors] = useState<ErrorNote[]>([]);
  const [clockResult, setClockResult] = useState<Stamped<ClockAdvanceResult> | null>(null);
  const [policyResult, setPolicyResult] = useState<Stamped<PolicyRunResult> | null>(null);
  const [runResult, setRunResult] = useState<Stamped<RunMinutesResult> | null>(null);
  const [exported, setExported] = useState<Stamped<ExportResult> | null>(null);
  const [issued, setIssued] = useState<Record<string, IssuedSession>>({});
  const [minutes, setMinutes] = useState(5);
  const errorCounter = useRef(0);
  const tz = view?.timezone ?? null;

  const addError = useCallback((text: string) => {
    errorCounter.current += 1;
    const id = errorCounter.current;
    setErrors((list) => [{ id, text }, ...list]);
  }, []);

  const refreshCurrent = useCallback(async () => {
    try {
      const res = await moderatorApi.current(session);
      setCurrent(res?.episode_id ?? null);
      setCurrentFailure(null);
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      setCurrent(undefined);
      setCurrentFailure(text);
      addError(`Could not read the current episode: ${text}`);
    }
  }, [session, addError]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await moderatorApi.cases(session);
        if (cancelled) return;
        const refs = list.map((c) => c.case_ref);
        setCases(refs);
        setCaseRef((prev) => (prev !== "" ? prev : refs[0] ?? ""));
      } catch (error) {
        if (!cancelled) addError(`Could not list cases: ${error instanceof Error ? error.message : String(error)}`);
      }
    })();
    void refreshCurrent();
    return () => {
      cancelled = true;
    };
  }, [session, refreshCurrent, addError]);

  const act = async <T,>(label: string, run: () => Promise<T>, onDone: (result: T) => void) => {
    setBusy(label);
    try {
      const result = await track(run);
      onDone(result);
      announce(`${label}: done.`);
    } catch (error) {
      let text: string;
      if (error instanceof NoResponseError) {
        text = `${label}: no response (${error.message}). The server may or may not have done this; it was not retried. The board shows the current state.`;
      } else if (error instanceof ApiError) {
        text = `${label} was refused (HTTP ${error.status}): ${error.message}`;
      } else {
        text = `${label} failed: ${error instanceof Error ? error.message : String(error)}`;
      }
      addError(text);
      announce(text);
    } finally {
      setBusy(null);
      await track(() => refresh());
      await refreshCurrent();
    }
  };

  // Controls that act on the episode need one; the reset asks first whenever one might exist.
  const activeEpisode = knownActiveEpisode(current, view);
  const hasEpisode = activeEpisode !== null;
  const confirmReset = resetNeedsConfirmation(current, view);
  /** The action and the scenario time it ran, so its result is never read as current state. */
  const stamp = (action: string): ActionStamp => ({ action, ranAt: view?.clock ?? null });
  const principals =
    view !== null
      ? view.grants
          .filter((g) => g.grant.principal_role !== "coordinator_agent")
          .map((g) => ({ id: g.grant.principal_id, label: g.grant.principal_role }))
      : FALLBACK_PRINCIPALS;
  const principalList = principals.length > 0 ? principals : FALLBACK_PRINCIPALS;

  const loadEpisode = () =>
    void act(
      "Load clean episode",
      () => moderatorApi.loadEpisode(session, DEFAULT_SCENARIO_ID, caseRef),
      (loaded) => {
        setCurrent(loaded.episode_id);
        setConfirmLoad(false);
        setIssued({});
        setClockResult(null);
        setPolicyResult(null);
        setRunResult(null);
        setExported(null);
      },
    );

  const downloadTrace = (name: string) =>
    void act("Download trace", () => loadServerReplay(name), (loaded) => {
      // The server's exact bytes: re-serializing in JS could alter numbers and break the hashes.
      const blob = new Blob([loaded.text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

  return (
    <Section
      id="moderator-panel"
      title="Moderator controls"
      className="panel"
      subtitle="Sandbox operator: episodes, the scenario clock, the deterministic policy, role links and traces."
    >
      {errors.length > 0 ? (
        <div className="error-list" role="alert">
          {errors.map((e) => (
            <p key={e.id} className="notice tone-bad">
              <span aria-hidden="true">✖ </span>
              {e.text}{" "}
              <button
                type="button"
                className="link-button"
                onClick={() => setErrors((list) => list.filter((x) => x.id !== e.id))}
              >
                Dismiss
              </button>
            </p>
          ))}
        </div>
      ) : null}

      <div className="form">
        <h3 className="list-heading">Episode</h3>
        <p className="small">
          {typeof current === "string" ? (
            <>
              Active episode <Code>{current}</Code> of scenario <Code>{DEFAULT_SCENARIO_ID}</Code>.
            </>
          ) : current === null && activeEpisode === null ? (
            "No active episode. Load one to begin."
          ) : (
            <>
              {current === null
                ? "The server reports no active episode, but this board's last state read shows one"
                : currentFailure !== null
                  ? `Could not confirm whether an episode is active (${currentFailure})`
                  : "Checking for an active episode…"}
              {activeEpisode !== null ? (
                <>
                  {" "}
                  (the board shows <Code>{activeEpisode}</Code> as active)
                </>
              ) : null}
              . Loading a case will ask for confirmation first.
              {currentFailure !== null ? (
                <>
                  {" "}
                  <button type="button" className="link-button" onClick={() => void refreshCurrent()}>
                    Check again
                  </button>
                </>
              ) : null}
            </>
          )}
        </p>
        <label className="field">
          <span>Case</span>
          <select value={caseRef} onChange={(e) => setCaseRef(e.target.value)} disabled={cases === null}>
            {cases === null ? <option value="">Loading cases…</option> : null}
            {cases?.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        {confirmLoad ? (
          <div className="confirm">
            <p className="consequence">
              <strong>Load a clean episode?</strong>{" "}
              {activeEpisode !== null ? (
                <>
                  This closes episode <Code>{activeEpisode}</Code> and signs out every role tab of it.
                </>
              ) : (
                <>
                  An episode may be active (it could not be confirmed). Loading closes it and signs out
                  every role tab of it.
                </>
              )}{" "}
              Export its trace first if you need it.
            </p>
            <div className="button-row">
              <button type="button" className="button danger" disabled={busy !== null || caseRef === ""} onClick={loadEpisode}>
                Close it and load case {caseRef}
              </button>
              <button type="button" className="button secondary" onClick={() => setConfirmLoad(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="button"
            disabled={busy !== null || caseRef === ""}
            onClick={() => (confirmReset ? setConfirmLoad(true) : loadEpisode())}
          >
            {confirmReset ? "Reset: load a clean episode…" : "Load episode"}
          </button>
        )}
      </div>

      <div className="form">
        <h3 className="list-heading">Scenario clock</h3>
        <div className="button-row">
          {[1, 5, 10].map((n) => (
            <button
              key={n}
              type="button"
              className="button"
              disabled={busy !== null || !hasEpisode}
              onClick={() => {
                const ran = stamp(`+${n} min`);
                void act(`Advance the clock ${n} min`, () => moderatorApi.advanceClock(session, n), (result) =>
                  setClockResult({ ...ran, result }),
                );
              }}
            >
              +{n} min
            </button>
          ))}
        </div>
        {clockResult !== null ? (
          <div className="result small">
            <p>
              <strong>
                {actionHeadline(
                  clockResult,
                  clockOutcome(clockResult.result.clock, clockResult.result.revision, tz),
                  tz,
                )}
              </strong>
              . {clockResult.result.transitions.length} event(s) processed.
            </p>
            <EarlierNote revision={clockResult.result.revision} view={view} />
            {clockResult.result.transitions.length > 0 ? (
              <ul>
                {clockResult.result.transitions.map((t) => (
                  <li key={`${t.revision}-${t.cause_kind}`}>
                    r{t.revision}: {t.summary}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="form">
        <h3 className="list-heading">Deterministic policy</h3>
        <p className="small muted">
          Runs <Code>{DETERMINISTIC_POLICY_ID}</Code> once until it waits. It acts only through the
          coordinator&apos;s own grant.
        </p>
        <button
          type="button"
          className="button"
          disabled={busy !== null || !hasEpisode}
          onClick={() => {
            const ran = stamp("Policy run");
            void act("Run deterministic policy", () => moderatorApi.runPolicy(session), (result) =>
              setPolicyResult({ ...ran, result }),
            );
          }}
        >
          {busy === "Run deterministic policy" ? "Running policy…" : "Run deterministic policy"}
        </button>
        {policyResult !== null ? (
          <PolicyRunSummary
            run={policyResult.result}
            tz={tz}
            headline={actionHeadline(policyResult, policyOutcome(policyResult.result, tz), tz)}
          />
        ) : null}
        <div className="inline-field">
          <label className="field">
            <span>Minutes</span>
            <input
              type="number"
              min={1}
              max={240}
              value={minutes}
              onChange={(e) => setMinutes(Math.max(1, Math.min(240, Math.round(Number(e.target.value) || 1))))}
            />
          </label>
          <button
            type="button"
            className="button"
            disabled={busy !== null || !hasEpisode}
            onClick={() => {
              const ran = stamp(`Run ${minutes} min with policy`);
              void act(
                `Run ${minutes} minutes with policy`,
                () => moderatorApi.runMinutes(session, minutes, true),
                (result) => setRunResult({ ...ran, result }),
              );
            }}
          >
            Run {minutes} minutes with policy
          </button>
        </div>
        {runResult !== null ? (
          <div className="result small">
            <p>
              <strong>
                {actionHeadline(runResult, clockOutcome(runResult.result.clock, runResult.result.revision, tz), tz)}
              </strong>
              .{" "}
              {runResult.result.policy_runs !== undefined
                ? `${runResult.result.policy_runs.length} policy run(s).`
                : ""}
            </p>
            <EarlierNote revision={runResult.result.revision} view={view} />
            {runResult.result.policy_runs?.map((r, i) => (
              <PolicyRunSummary key={`${r.policy_id}-${i}`} run={r} tz={tz} />
            ))}
            <EvidenceCard title="Run result (JSON)" value={runResult.result} />
          </div>
        ) : null}
      </div>

      <div className="form">
        <h3 className="list-heading">Role sessions</h3>
        <p className="small muted">
          Each link carries a one-time join code for one sandbox role. Open it in a new tab; each tab
          keeps its own session.
        </p>
        {!hasEpisode ? (
          <Empty>Load an episode first.</Empty>
        ) : (
          <ul className="session-list">
            {principalList.map((p) => {
              const s = issued[p.id];
              const url = s !== undefined ? joinUrl(s.join_code) : null;
              return (
                <li key={p.id}>
                  <p>
                    <Code>{p.id}</Code> <span className="muted small">({p.label.replace(/_/g, " ")})</span>
                  </p>
                  <div className="button-row">
                    <button
                      type="button"
                      className="button secondary"
                      disabled={busy !== null}
                      onClick={() =>
                        void act(`Issue a join code for ${p.id}`, () => moderatorApi.issueSession(session, p.id), (res) =>
                          setIssued((prev) => ({ ...prev, [p.id]: res })),
                        )
                      }
                    >
                      {s !== undefined ? "Issue a new code" : "Issue join code"}
                    </button>
                    {url !== null ? (
                      <button
                        type="button"
                        className="button"
                        onClick={() => window.open(url, "_blank", "noopener,noreferrer")}
                      >
                        Open in new tab
                      </button>
                    ) : null}
                  </div>
                  {s !== undefined && url !== null ? (
                    <p className="small">
                      Join link:{" "}
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        #/join/{s.join_code}
                      </a>
                      {s.expires_wall !== undefined ? ` · expires ${fmtWall(s.expires_wall)} (wall clock)` : " · one-time code"}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="form">
        <h3 className="list-heading">Trace</h3>
        <div className="button-row">
          <button
            type="button"
            className="button"
            disabled={busy !== null || !hasEpisode}
            onClick={() => {
              const ran = stamp("Export");
              void act("Export trace", () => moderatorApi.exportTrace(session), (result) =>
                setExported({ ...ran, result }),
              );
            }}
          >
            Export trace
          </button>
          <a className="button secondary" href="#/replay">
            Open replay
          </a>
        </div>
        {exported !== null ? (
          <div className="result small">
            <p>
              <Tag tone="ok" icon="✔">
                Exported
              </Tag>{" "}
              <strong>
                {actionHeadline(
                  exported,
                  exported.result.trace !== undefined
                    ? `revision ${exported.result.trace.final_state.revision}, ` +
                        `${exported.result.trace.frames.length} frames`
                    : "trace written",
                  tz,
                )}
              </strong>
              {exported.result.name !== undefined ? (
                <>
                  {" "}
                  · <Code>{exported.result.name}</Code>
                </>
              ) : null}
            </p>
            <div className="button-row">
              {exported.result.name !== undefined ? (
                <a className="button" href={`#/replay/${encodeURIComponent(exported.result.name)}`}>
                  Replay this trace
                </a>
              ) : null}
              {exported.result.name !== undefined ? (
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy !== null}
                  onClick={() => downloadTrace(exported.result.name as string)}
                >
                  Download JSON
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </Section>
  );
}
