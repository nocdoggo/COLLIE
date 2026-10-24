import { useCallback, useEffect, useState } from "react";

import { clearSession, loadSession } from "./api";
import type { StoredSession } from "./api";
import { ReplayView } from "./replay/ReplayView";
import { EventBoard } from "./views/EventBoard";
import { JoinView, SignIn } from "./views/SignIn";

type Route =
  | { readonly name: "board" }
  | { readonly name: "join"; readonly code: string }
  | { readonly name: "replay"; readonly replay: string | null }
  | { readonly name: "not_found"; readonly hash: string };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "");
  if (path === "" || path === "/") return { name: "board" };
  const join = /^\/join\/([^/?#]+)\/?$/.exec(path);
  if (join?.[1] !== undefined) return { name: "join", code: decodeURIComponent(join[1]) };
  if (path === "/replay" || path === "/replay/") return { name: "replay", replay: null };
  const replay = /^\/replay\/([^/?#]+)\/?$/.exec(path);
  if (replay?.[1] !== undefined) return { name: "replay", replay: decodeURIComponent(replay[1]) };
  return { name: "not_found", hash };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function App() {
  const route = useRoute();
  const [session, setSession] = useState<StoredSession | null>(() => loadSession());
  const [notice, setNotice] = useState<string | null>(null);
  // Increments on every sign-in so a new session always mounts a fresh board.
  const [epoch, setEpoch] = useState(0);

  const signedIn = useCallback((next: StoredSession) => {
    setNotice(null);
    setSession(next);
    setEpoch((n) => n + 1);
    // Leave the one-time code out of the address bar and history.
    if (window.location.hash !== "#/") window.history.replaceState(null, "", "#/");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const sessionEnded = useCallback((message: string) => {
    clearSession();
    setSession(null);
    setNotice(message);
  }, []);

  let content;
  if (route.name === "replay") {
    content = <ReplayView key={route.replay ?? ""} initialName={route.replay} />;
  } else if (route.name === "join") {
    content = <JoinView code={route.code} onSignedIn={signedIn} />;
  } else if (route.name === "not_found") {
    content = (
      <main id="main" className="page">
        <p className="notice tone-warn">
          There is no page at {route.hash}. <a href="#/">Go to the board</a> or{" "}
          <a href="#/replay">open a recorded replay</a>.
        </p>
      </main>
    );
  } else if (session === null) {
    content = <SignIn notice={notice} onDismissNotice={() => setNotice(null)} onSignedIn={signedIn} />;
  } else {
    content = (
      <EventBoard
        key={epoch}
        session={session}
        onSessionEnded={sessionEnded}
        onSignOut={signOut}
      />
    );
  }

  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          // A plain #main navigation would be read by the hash router as a route.
          e.preventDefault();
          const main = document.getElementById("main");
          main?.setAttribute("tabindex", "-1");
          main?.focus();
        }}
      >
        Skip to content
      </a>
      {content}
    </>
  );
}
