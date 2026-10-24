// The live board. It reads GET /api/state every 1.5 s (paused while any request of this tab is
// in flight), so a second tab sees persisted changes, and it shows the signed-in role's panel.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, NoResponseError, readState, sessionEndMessage } from "../api";
import type { StoredSession, ToolBinding } from "../api";
import { BoardView } from "../board/BoardView";
import { BoardHeader, PRODUCT_NAME, SANDBOX_NOTICE } from "../components/BoardHeader";
import { ROLE_LABEL } from "../format";
import { ModeratorPanel } from "../panels/ModeratorPanel";
import { OrganizerPanel } from "../panels/OrganizerPanel";
import { ParticipantPanel } from "../panels/ParticipantPanel";
import { useMutationTracker } from "../panels/useMutations";
import type { EventStateView } from "../types";

const POLL_MS = 1500;

type LoadProblem =
  | { readonly kind: "no_episode"; readonly message: string }
  | { readonly kind: "unreachable"; readonly message: string }
  | { readonly kind: "refused"; readonly message: string };

export function EventBoard({
  session,
  onSessionEnded,
  onSignOut,
}: {
  session: StoredSession;
  onSessionEnded: (message: string) => void;
  onSignOut: () => void;
}) {
  const [view, setView] = useState<EventStateView | null>(null);
  const [problem, setProblem] = useState<LoadProblem | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const inFlight = useRef(0);
  const lastText = useRef("");
  const knownReceipts = useRef<Set<string> | null>(null);
  const endedRef = useRef(onSessionEnded);
  endedRef.current = onSessionEnded;

  const announce = useCallback((text: string) => {
    // Clear first so an identical message is announced again.
    setAnnouncement("");
    window.setTimeout(() => setAnnouncement(text), 50);
  }, []);

  const track = useCallback(async <T,>(run: () => Promise<T>): Promise<T> => {
    inFlight.current += 1;
    try {
      return await run();
    } finally {
      inFlight.current -= 1;
    }
  }, []);

  const refresh = useCallback(async (): Promise<EventStateView | null> => {
    try {
      const read = await readState(session);
      setProblem(null);
      if (read.text !== lastText.current) {
        lastText.current = read.text;
        // Announce receipts that other actors (for example, the policy) produced since last read.
        const ids = new Set(read.view.receipts.map((r) => r.receipt_id));
        const previous = knownReceipts.current;
        if (previous !== null) {
          const fresh = read.view.receipts.filter((r) => !previous.has(r.receipt_id));
          if (fresh.length > 0) {
            announce(
              fresh
                .slice(-3)
                .map((r) => `New receipt: ${r.tool} ${r.status}. ${r.summary}`)
                .join(" "),
            );
          }
        }
        knownReceipts.current = ids;
        setView(read.view);
      }
      return read.view;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) {
          endedRef.current(sessionEndMessage(error.code, error.message));
        } else if (error.status === 409 || error.status === 404) {
          setView(null);
          lastText.current = "";
          knownReceipts.current = null;
          setProblem({ kind: "no_episode", message: error.message });
        } else {
          setProblem({ kind: "refused", message: `HTTP ${error.status}: ${error.message}` });
        }
      } else if (error instanceof NoResponseError) {
        setProblem({ kind: "unreachable", message: error.message });
      } else {
        setProblem({ kind: "unreachable", message: error instanceof Error ? error.message : String(error) });
      }
      return null;
    }
  }, [session, announce]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      if (cancelled) return;
      if (inFlight.current === 0) await refresh();
      if (!cancelled) timer = window.setTimeout(() => void tick(), POLL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [refresh]);

  const binding: ToolBinding | null = useMemo(() => {
    const eventId = session.event_id ?? view?.event_id ?? null;
    if (eventId === null) return null;
    return { event_id: eventId, grant_id: session.grant_id ?? view?.viewer.grant_id ?? null };
  }, [session, view?.event_id, view?.viewer.grant_id]);

  const tracker = useMutationTracker({ session, binding, refresh, announce, track });

  const signOut = (
    <button type="button" className="button secondary small" onClick={onSignOut}>
      Sign out of this tab
    </button>
  );

  const role = view?.viewer.role ?? session.role;
  let sidePanel = null;
  if (view !== null && binding !== null && view.viewer.role === "participant") {
    sidePanel = <ParticipantPanel view={view} binding={binding} tracker={tracker} />;
  } else if (view !== null && binding !== null && view.viewer.role === "organizer") {
    sidePanel = (
      <OrganizerPanel
        view={view}
        session={session}
        binding={binding}
        tracker={tracker}
        track={track}
        refresh={refresh}
      />
    );
  }

  // Children are keyed so the moderator deck keeps its state when the first state read arrives.
  return (
    <main id="main" className="page">
      <div key="live" className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      {view !== null ? (
        <BoardHeader key="header" view={view} mode="live" actions={signOut} />
      ) : (
        <header key="header-pending" className="board-header">
          <div className="brand-row">
            <p className="product-name">{PRODUCT_NAME}</p>
            <p className="sandbox-label">
              <span aria-hidden="true">⚠ </span>
              {SANDBOX_NOTICE}
            </p>
            <p className="mode-label mode-live">Deterministic policy</p>
            <p className="viewer-label">
              Signed in as {ROLE_LABEL[session.role] ?? session.role} ·{" "}
              <code className="code">{session.principal_id}</code>
            </p>
            {signOut}
          </div>
        </header>
      )}
      {view === null && problem === null ? (
        <p key="loading" className="notice tone-info">
          Reading the event state…
        </p>
      ) : null}
      {view === null && problem?.kind === "no_episode" ? (
        <p key="no-episode" className="notice tone-warn">
          No active episode ({problem.message}).
          {role === "moderator" ? " Load one with the moderator controls." : ""}
        </p>
      ) : null}
      {problem !== null && problem.kind !== "no_episode" ? (
        <p key="problem" className="notice tone-bad sticky-notice" role="alert">
          {view !== null
            ? `The latest state read failed (${problem.message}). The board shows the last successful read at revision ${view.revision}; `
            : `Could not read the event state (${problem.message}); `}
          retrying every {POLL_MS / 1000} s.
        </p>
      ) : null}
      {view !== null && view.episode_status === "closed" ? (
        <p key="closed" className="notice tone-warn">
          This episode is closed. Its records are read-only.
        </p>
      ) : null}
      {role === "moderator" ? (
        <div key="moderator-deck" className="control-deck">
          <ModeratorPanel session={session} view={view} track={track} refresh={refresh} announce={announce} />
        </div>
      ) : null}
      {view !== null ? (
        <BoardView key="board" view={view} mode="live" showHeader={false} panel={sidePanel} />
      ) : null}
    </main>
  );
}
