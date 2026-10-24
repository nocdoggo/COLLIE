import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, EPISODE_RESET_MESSAGE, NoResponseError, exchangeJoinCode, signInModerator } from "../api";
import type { StoredSession } from "../api";
import { PRODUCT_NAME, SANDBOX_NOTICE } from "../components/BoardHeader";

function message(error: unknown): string {
  if (error instanceof ApiError && error.code === "EPISODE_CLOSED") return EPISODE_RESET_MESSAGE;
  if (error instanceof ApiError) return `Refused (HTTP ${error.status}): ${error.message}`;
  if (error instanceof NoResponseError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function codeFromInput(value: string): string {
  // Accept a pasted join link as well as the bare code.
  const match = /#\/join\/([^/?#\s]+)/.exec(value);
  return (match?.[1] !== undefined ? decodeURIComponent(match[1]) : value).trim();
}

export function SignIn({
  notice,
  onDismissNotice,
  onSignedIn,
}: {
  notice: string | null;
  onDismissNotice: () => void;
  onSignedIn: (session: StoredSession) => void;
}) {
  const [moderatorCode, setModeratorCode] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState<"moderator" | "join" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submitModerator = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("moderator");
    setError(null);
    try {
      onSignedIn(await signInModerator(moderatorCode.trim()));
    } catch (e) {
      setError(`Moderator sign-in failed. ${message(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const submitJoin = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("join");
    setError(null);
    try {
      onSignedIn(await exchangeJoinCode(codeFromInput(joinCode)));
    } catch (e) {
      setError(`Joining failed. ${message(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <main id="main" className="page signin">
      <header className="board-header">
        <div className="brand-row">
          <h1 className="product-name">{PRODUCT_NAME}</h1>
          <p className="sandbox-label">
            <span aria-hidden="true">⚠ </span>
            {SANDBOX_NOTICE}
          </p>
        </div>
      </header>
      {notice !== null ? (
        <p className="notice tone-warn" role="alert">
          {notice}{" "}
          <button type="button" className="link-button" onClick={onDismissNotice}>
            Dismiss
          </button>
        </p>
      ) : null}
      {error !== null ? (
        <p className="notice tone-bad" role="alert">
          {error}{" "}
          <button type="button" className="link-button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      ) : null}
      <div className="signin-grid">
        <form className="card form" onSubmit={(e) => void submitModerator(e)}>
          <h2 className="card-title">Moderator</h2>
          <p className="small muted">
            For the person running the sandbox. The code is printed by the server at startup.
          </p>
          <label className="field">
            <span>Moderator code</span>
            <input
              type="password"
              autoComplete="off"
              value={moderatorCode}
              onChange={(e) => setModeratorCode(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="button" disabled={busy !== null || moderatorCode.trim() === ""}>
            {busy === "moderator" ? "Signing in…" : "Sign in as moderator"}
          </button>
        </form>
        <form className="card form" onSubmit={(e) => void submitJoin(e)}>
          <h2 className="card-title">Join a role</h2>
          <p className="small muted">
            Paste the one-time join code or link the moderator gave you. This tab then acts only as
            that sandbox role.
          </p>
          <label className="field">
            <span>Join code or link</span>
            <input autoComplete="off" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} required />
          </label>
          <button type="submit" className="button" disabled={busy !== null || joinCode.trim() === ""}>
            {busy === "join" ? "Joining…" : "Join"}
          </button>
        </form>
        <div className="card">
          <h2 className="card-title">Recorded replay</h2>
          <p className="small muted">Watch a saved run. No sign-in needed; nothing is executed.</p>
          <a className="button secondary" href="#/replay">
            Open recorded replay
          </a>
        </div>
      </div>
    </main>
  );
}

// One exchange per code per page load: React StrictMode runs effects twice in development,
// and a one-time code must not be redeemed twice.
const exchanges = new Map<string, Promise<StoredSession>>();

export function JoinView({
  code,
  onSignedIn,
}: {
  code: string;
  onSignedIn: (session: StoredSession) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const done = useRef(onSignedIn);
  done.current = onSignedIn;

  useEffect(() => {
    let active = true;
    let pending = exchanges.get(code);
    if (pending === undefined) {
      pending = exchangeJoinCode(code);
      exchanges.set(code, pending);
    }
    pending.then(
      (session) => {
        if (active) done.current(session);
      },
      (e: unknown) => {
        if (active) setError(message(e));
      },
    );
    return () => {
      active = false;
    };
  }, [code]);

  return (
    <main id="main" className="page signin">
      <header className="board-header">
        <div className="brand-row">
          <h1 className="product-name">{PRODUCT_NAME}</h1>
          <p className="sandbox-label">
            <span aria-hidden="true">⚠ </span>
            {SANDBOX_NOTICE}
          </p>
        </div>
      </header>
      {error === null ? (
        <p className="notice tone-info" role="status">
          Joining with a one-time code…
        </p>
      ) : (
        <div className="notice tone-bad" role="alert">
          <p>This join code could not be used. {error}</p>
          <p>
            Ask the moderator for a new link, or <a href="#/">go to sign-in</a>.
          </p>
        </div>
      )}
    </main>
  );
}
