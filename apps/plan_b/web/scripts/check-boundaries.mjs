// Boundary lint: project invariants that TypeScript cannot check. Exits non-zero on any violation.
//
// What it is: a static guard against *accidental* use of the network, storage or mutating code
// from the read-only replay and board. It is not a sandbox. The enforcement is at run time: the
// browser walkthrough fails on any non-GET request the replay page sends (tests/e2e/walkthrough.py),
// and test_replay_endpoints_perform_no_writes (tests/test_runner_isolation.py) checks that the
// replay endpoints write nothing. The lint reads the files under src (and dist/ for rule 6) and
// nothing else: index.html, vite.config.ts, package.json and tsconfig.json are build
// configuration, trusted and reviewed by hand. Code written to evade the lint still can. Known
// evasions, each of which tests/boundaries.test.ts checks still passes, so that this list stays
// accurate:
// - an aliased global object or prototype, such as the round-1 case
//   `const g = globalThis as unknown as Record<...>; g["fe" + "tch"](...)` or
//   `const p = Object.prototype; p.body = ...`, or one passed through a function, an array or an
//   object (`[window][0][k]`, `e.view[k]`);
// - `Reflect.get(window, name)`, or any helper handed a global object, with a computed name;
// - a mutator (defineProperty, assign, set, ...) called other than by its own name: through
//   `.call` (`Object.defineProperty.call(null, Object.prototype, ...)`), held in a variable of
//   another name (`const dp = Object.defineProperty; dp(Object.prototype, ...)`), or through
//   `Reflect.apply(Object.defineProperty, null, [Object.prototype, ...])`;
// - a name assembled from strings outside an index on a global object, navigator or document;
// - a string of code handed to setTimeout or setInterval;
// - the Function constructor reached through a variable or one of its methods
//   (`const F = f.constructor; F("...")`, `f.constructor.call(0, "...")`, `new f.constructor("...")`,
//   `Reflect.construct(f.constructor, [...])`);
// - a tag name or javascript: URL built at run time (`"fo" + "rm"`, a value read from a trace);
// - a global name (top, parent, frames, navigator, document, Object, ...) in a module that
//   declares a binding of that name anywhere, an ambient `declare const navigator` or a
//   parameter named document included: the lint then reads every use of the name in that
//   module as the local binding;
// - web APIs this list does not name (document.write, DOMParser, WebTransport, window.open,
//   location.assign of a same-origin blob: HTML document, ...).
// The loader does not depend on the prototype rules: its fetch options have no prototype, so no
// inherited key reaches its requests, whatever another module does (rule 2).
//
// How it reads code: every source is parsed with the TypeScript compiler API (ts.createSourceFile)
// and the checks inspect the syntax tree. Comments are not inspected (rule 6 aside), so a
// comment that names an API is fine. Names are compared after the parser decodes them, so a
// unicode-escaped identifier (\u0066etch) or an escaped string ("\u0066etch") counts as the name
// it spells; a JSX attribute string also has its numeric character references (&#111;) decoded.
// Type positions (annotations, interfaces, type aliases, `import type`) are skipped: they are
// erased at build time.
//
// The sources are every script file under src: .ts, .tsx, .mts, .cts, .js, .jsx, .mjs and .cjs,
// the extension compared ignoring case (x.JS is a source; Vite bundles it as JavaScript). Every
// source's module references are resolved: import declarations, `export ... from`,
// `import x = require(...)`, dynamic import() and `new URL("...", import.meta.url)`. A relative
// or root-absolute ("/src/...") specifier names every file it could resolve to, all of which
// are checked: the file itself, its .ts (.tsx, .mts, .cts) counterpart for a .js (.jsx, .mjs,
// .cjs) one, the specifier with each of Vite's extensions (.mjs, .js, .mts, .ts, .jsx, .tsx,
// .json) added, and the index files of a directory. Its "?query" or "#hash" suffix is kept
// apart. Rule 3 keeps every file named this way under src; a script one is followed, and a leaf
// (an allowed asset or style file) is neither followed nor scanned. Bare package specifiers
// (react) resolve into web/node_modules and are not followed.
// A read-only module is any source under src/replay, src/board or src/components, src/format.ts,
// src/types.ts, and every script module those reach.
//
// Terms used below. "The value of x" is x with parentheses, `!`, `as`, `satisfies` and `<T>`
// dropped, `(0, x)` read as x, and also either operand of `a || b`, `a && b` and `a ?? b`, either
// branch of `c ? a : b`, and the right side of `x = y`. A member is `.name` or a literal key
// `["name"]`. A global object is the value globalThis, window, self, a bare top, parent or
// frames, document.defaultView, or a globalThis, window, self, top, parent or frames member of a
// global object (`window["top"]`, `globalThis.window`). A global binding is an identifier the
// module does not declare (Object, document, location).
//
// 1. No read-only module reaches src/api.ts, src/panels/ or src/views/, directly or transitively.
//    `import type` and `export type` are not followed; `import { type X }` is, because
//    verbatimModuleSyntax keeps it as a side-effect import.
// 2. A read-only module may not use, as an identifier, a property name, a JSX attribute or a
//    string literal spelling exactly the name: fetch, XMLHttpRequest, sendBeacon, WebSocket,
//    EventSource, RTCPeerConnection, Request (so no `new Request`, `const R = Request` or
//    `Reflect.construct(Request, ...)`), sessionStorage, indexedDB, caches, cookie, cookieStore,
//    serviceWorker, Worker, SharedWorker, eval, Function, innerHTML, outerHTML,
//    insertAdjacentHTML, ping, __proto__, __defineGetter__, __defineSetter__, __lookupGetter__,
//    __lookupSetter__. It may not use a string that is exactly form, iframe or script in any
//    case (so no `as="form"`, `const Tag = "iframe"` or `createElement("SCRIPT")`); render a
//    <form>, <iframe> or <script> in JSX; call document.createElement with a computed tag; use a
//    javascript: URL string; index with a computed key, or destructure a computed key from
//    (`const { [k]: f } = globalThis`), a global object, navigator or document (a bare one, a
//    member of a global object, or any `x.ownerDocument`); reach the Function constructor through
//    `.constructor.constructor` or the `.constructor` of a function or class expression, or call
//    any `x.constructor(...)`; use import.meta other than import.meta.env and import.meta.url (so
//    no import.meta.glob); or import a module with a Vite "?worker" suffix.
//    Nor may it change a shared object. It may not write (assign with any operator, ++, --,
//    delete, or a destructuring or for-in/of target) X.prototype for any X; a member of a
//    prototype (X.prototype, Object.getPrototypeOf(...)), of a global object, of a global binding
//    (`Object.freeze = ...`, `document.title = ...`) or of a member of a global object
//    (`window.Object.freeze = ...`); or a global binding itself (`name = ...`). It may not call
//    defineProperty, defineProperties, setPrototypeOf, assign, set or deleteProperty (on Object,
//    Reflect or any other receiver) with one of those as the first argument. This fails closed
//    on purpose: a read-only module writes no global at all, so `location.hash = ...`,
//    `document.title = ...` and `new WeakMap().set(window, 1)` fail too. Navigation and title
//    code belongs in a trusted module (src/App.tsx owns the route and passes it down as a prop);
//    a read-only module navigates with a plain `<a href="#/...">` link or a callback it is given.
//    The one exception is fetch in src/replay/loader.ts. There every `fetch` must be the callee
//    of a direct call `fetch(url, OPTIONS)` with exactly two arguments, OPTIONS an identifier the
//    loader declares once, as a top-level
//    `const OPTIONS = Object.freeze(Object.assign(Object.create(null), { ... }))` built with the
//    real Object (the loader may not declare its own). The browser reads every RequestInit key
//    from the options, inherited ones included, so a `body` or `headers` key, or a getter that
//    rewrites `method`, that any module put on Object.prototype would reach the request. Options
//    with no prototype have only their own keys, and frozen, none can be added or changed. The
//    `{ ... }` literal's keys must be plain identifiers or strings (no computed key, no spread,
//    no method or accessor), each one of method, credentials, cache, signal, redirect, mode,
//    referrer, referrerPolicy, integrity and priority (so no headers, no body and no __proto__).
//    It must state the method as a string literal equal to "GET" ignoring case ("GET" + x
//    fails): the options' method overrides a Request input's, and a GET with a body is a
//    TypeError, so a Request input cannot turn it into a POST. It must set credentials to the
//    string "omit".
// 3. Every module a source references is known statically and lies under src, so that rules 1
//    to 6 read every module the bundle takes from there. In any source:
//    - every dynamic import() takes exactly one quoted string literal, and every
//      `new URL(..., import.meta.url)` a quoted string as its first argument (a backtick or
//      computed specifier fails); no source uses import.meta.glob;
//    - no specifier is a URL: one that starts with a scheme (data:, blob:, http:, https:, file:,
//      ...) or with //. Vite would inline a data: module's code into the bundle and keep a remote
//      import, and rule 1 can follow neither;
//    - every file a relative or root-absolute specifier names is under src: `../../shared/x.js`
//      or `/vite.config.ts` fails;
//    - every such file is a script, or a leaf: a file whose extension, in lower case exactly, is
//      .css, .json, .svg, .png, .jpg, .jpeg, .gif, .webp, .avif, .ico, .woff, .woff2, .ttf, .otf
//      or .txt, imported with no suffix or with ?url or ?raw. Anything else fails: an
//      extensionless file, a .md, an upper-case x.CSS or x.JSON (Vite bundles all of these as
//      JavaScript), or a leaf with ?worker or any other suffix (with ?worker Vite runs even a
//      CSS file as a worker's code);
//    - no specifier names a directory that holds a package.json (Vite would load the entry it
//      names, not an index file), and a package specifier neither starts with # nor holds a "."
//      or ".." segment (which could climb out of node_modules);
//    - src holds no symbolic link (Vite resolves one to the file it points to, wherever that is),
//      no node_modules folder (a package specifier could resolve into it), no package.json (Vite
//      applies its browser field to the imports of the files beside it), and no tsconfig.json or
//      jsconfig.json (esbuild applies its compiler options, such as jsxImportSource, to them);
//    - no source holds a JSX pragma comment (@jsx, @jsxFrag, @jsxImportSource, @jsxRuntime),
//      which changes what esbuild emits for every element in the file.
// 4. No source uses dangerouslySetInnerHTML.
// 5. No source uses localStorage (session tokens stay per tab in sessionStorage), and no source
//    other than src/api.ts sets an authorization header: an "Authorization" object key or
//    assigned property, an "authorization" string (any case), or a string starting "Bearer ".
// 6. No private runner vocabulary in the raw text of any file under src or of the built dist/
//    bundle (this one is textual on purpose, comments included).
// Every source must also parse; a syntax error is reported rather than skipped.
//
// tests/boundaries.test.ts plants each violation in a copy of src/ and asserts that this lint
// reports it. Usage: node scripts/check-boundaries.mjs [web root]; the default is this script's
// parent directory.

import { existsSync, lstatSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

/** A script file, its extension in any case: Vite bundles x.JS as JavaScript. */
const SCRIPT = /\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs)$/i;
/** Vite's default resolve.extensions, tried in turn for a specifier without an extension. */
const RESOLVE_EXTENSIONS = [".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json"];
/**
 * Files an import may name that carry no code: neither followed nor scanned. Matched in lower
 * case exactly, because Vite recognizes .css and .json only in lower case and bundles x.CSS or
 * x.JSON as JavaScript. Anything else that is not a script (.md, no extension) fails.
 */
const LEAF_EXTENSIONS = new Set([
  ".css",
  ".json",
  ".svg",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".avif",
  ".ico",
  ".woff",
  ".woff2",
  ".ttf",
  ".otf",
  ".txt",
]);
/** The only suffixes a leaf import may carry. With ?worker (and the like) Vite runs it as code. */
const LEAF_SUFFIXES = new Set(["", "?url", "?raw"]);
const LOADER = "src/replay/loader.ts";
/** A module specifier that is a URL: a scheme (data:, blob:, http:, https:, file:, ...) or "//". */
const URL_SPECIFIER = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;
/** The only keys the loader's fetch options may use. `headers` and `body` are not among them. */
const LOADER_INIT_KEYS = new Set([
  "method",
  "credentials",
  "cache",
  "signal",
  "redirect",
  "mode",
  "referrer",
  "referrerPolicy",
  "integrity",
  "priority",
]);

/** Rule 2 names, with how the report spells each. */
const FORBIDDEN_NAMES = new Map([
  ["fetch", "fetch"],
  ["XMLHttpRequest", "XMLHttpRequest"],
  ["sendBeacon", "sendBeacon"],
  ["WebSocket", "WebSocket"],
  ["EventSource", "EventSource"],
  ["RTCPeerConnection", "RTCPeerConnection"],
  ["Request", "the Request constructor"],
  ["sessionStorage", "sessionStorage"],
  ["indexedDB", "indexedDB"],
  ["caches", "caches"],
  ["cookie", "cookie"],
  ["cookieStore", "cookieStore"],
  ["serviceWorker", "serviceWorker"],
  ["Worker", "Worker"],
  ["SharedWorker", "SharedWorker"],
  ["eval", "eval"],
  ["Function", "the Function constructor"],
  ["innerHTML", "innerHTML"],
  ["outerHTML", "outerHTML"],
  ["insertAdjacentHTML", "insertAdjacentHTML"],
  ["ping", "a ping attribute"],
  // Prototype access: `{ __proto__: p }` and `x.__proto__ = p` set a prototype, and the legacy
  // accessors define or find getters on one (Object.prototype.__defineGetter__("body", ...)).
  ["__proto__", "__proto__"],
  ["__defineGetter__", "__defineGetter__"],
  ["__defineSetter__", "__defineSetter__"],
  ["__lookupGetter__", "__lookupGetter__"],
  ["__lookupSetter__", "__lookupSetter__"],
]);
/** Calls that write to their first argument: Object.defineProperty(Object.prototype, ...), ... */
const MUTATORS = new Set(["defineProperty", "defineProperties", "setPrototypeOf", "assign", "set", "deleteProperty"]);
const FORBIDDEN_TAGS = new Set(["form", "iframe", "script"]);
const GLOBAL_OBJECTS = new Set(["globalThis", "window", "self"]);
/** Bare names of another window (window.top, ...), unless the module declares its own binding. */
const WINDOW_NAMES = new Set(["top", "parent", "frames"]);
/** Properties of a global object that are the global object (or another window) again. */
const GLOBAL_ALIASES = new Set([...GLOBAL_OBJECTS, ...WINDOW_NAMES]);
/** Host objects that a computed key may not index either. */
const HOST_OBJECTS = new Set(["navigator", "document"]);
const ELEMENT_FACTORIES = new Set(["createElement", "jsx", "jsxs", "jsxDEV"]);
const PRIVATE_MARKERS = [
  "never_expose_to_agent",
  "status_model",
  "world_events",
  "outcome_predicates",
  "actor_scripts",
  "ground_truth",
  "plan_b.private_case",
  "PLAN_B_MODERATOR_CODE",
];

/**
 * Every file under `dir`, with the entries rule 3 refuses there: a symbolic link (not followed),
 * a node_modules folder (walked like any other), and a package.json, tsconfig or jsconfig file.
 */
function walk(dir, found = { files: [], refused: [] }) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = lstatSync(path);
    if (stat.isSymbolicLink()) {
      found.refused.push([path, "is a symbolic link, which Vite resolves to the file it points to"]);
    } else if (stat.isDirectory()) {
      if (name === "node_modules") found.refused.push([path, "is a node_modules folder"]);
      walk(path, found);
    } else {
      if (name === "package.json") {
        found.refused.push([path, "is a package.json, whose browser field Vite applies to the imports beside it"]);
      } else if (/^[tj]sconfig(?:\..*)?\.json$/i.test(name)) {
        found.refused.push([path, "is a tsconfig or jsconfig file, whose compiler options esbuild applies beside it"]);
      }
      found.files.push(path);
    }
  }
  return found;
}

function scriptKind(path) {
  const ext = extname(path).toLowerCase();
  if (ext === ".tsx") return ts.ScriptKind.TSX;
  if (ext === ".jsx") return ts.ScriptKind.JSX;
  if (ext === ".js" || ext === ".mjs" || ext === ".cjs") return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

/** A string-valued literal whose text the parser has decoded. */
const isStringish = (node) => ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node);

/** The text of a property name that is a plain identifier or string, otherwise null. */
function plainName(name) {
  if (name === undefined) return null;
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNoSubstitutionTemplateLiteral(name)) {
    return name.text;
  }
  return null;
}

/** A literal key, which the name rule already reads: a string or a number. */
const isLiteralKey = (node) => isStringish(node) || ts.isNumericLiteral(node);

/**
 * The expression a value comes from: parentheses, `!`, `as`, `satisfies`, `<T>x`, an
 * instantiation expression `x<T>` and `(0, x)` dropped.
 */
function unwrap(node) {
  let n = node;
  for (;;) {
    if (
      ts.isParenthesizedExpression(n) ||
      ts.isNonNullExpression(n) ||
      ts.isAsExpression(n) ||
      ts.isSatisfiesExpression(n) ||
      ts.isTypeAssertionExpression(n) ||
      ts.isExpressionWithTypeArguments(n)
    ) {
      n = n.expression;
    } else if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.CommaToken) {
      n = n.right;
    } else {
      return n;
    }
  }
}

const LOGICAL_OPERATORS = new Set([
  ts.SyntaxKind.BarBarToken,
  ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.QuestionQuestionToken,
  ts.SyntaxKind.BarBarEqualsToken,
  ts.SyntaxKind.AmpersandAmpersandEqualsToken,
  ts.SyntaxKind.QuestionQuestionEqualsToken,
]);

/**
 * Every expression the value of `node` can come from, each unwrapped: both operands of
 * `a || b`, `a && b` and `a ?? b` (and of their assignment forms), both branches of `c ? a : b`,
 * and the right side of `x = y`.
 */
function valueSources(node) {
  const n = unwrap(node);
  if (ts.isBinaryExpression(n)) {
    if (LOGICAL_OPERATORS.has(n.operatorToken.kind)) return [...valueSources(n.left), ...valueSources(n.right)];
    if (n.operatorToken.kind === ts.SyntaxKind.EqualsToken) return valueSources(n.right);
  }
  if (ts.isConditionalExpression(n)) return [...valueSources(n.whenTrue), ...valueSources(n.whenFalse)];
  return [n];
}

/** The name of a member access `x.name` or `x["name"]` (a literal key), otherwise null. */
function memberName(node) {
  if (ts.isPropertyAccessExpression(node)) return node.name.text;
  if (ts.isElementAccessExpression(node) && isLiteralKey(node.argumentExpression)) return node.argumentExpression.text;
  return null;
}

/** The first non-null result of `pick` over the value sources of `node`. */
function firstSource(node, pick) {
  for (const source of valueSources(node)) {
    const found = pick(source);
    if (found !== null) return found;
  }
  return null;
}

/**
 * The global object an expression names (globalThis, window, self, window.top, window["top"], a
 * bare top, document.defaultView, ...), or null. `local` holds the names the module declares
 * itself, so a local `frames` is not the global one.
 */
function globalObjectName(node, local) {
  return firstSource(node, (n) => {
    if (ts.isIdentifier(n)) {
      return GLOBAL_OBJECTS.has(n.text) || (WINDOW_NAMES.has(n.text) && !local.has(n.text)) ? n.text : null;
    }
    const name = memberName(n);
    if (name === "defaultView" && isDocumentExpression(n.expression)) return "document.defaultView";
    if (name !== null && GLOBAL_ALIASES.has(name)) {
      const base = globalObjectName(n.expression, local);
      return base !== null ? `${base}.${name}` : null;
    }
    return null;
  });
}

/** An object a computed key may not index: a global object, navigator or document (el.ownerDocument too). */
function indexedObjectName(node, local) {
  const global = globalObjectName(node, local);
  if (global !== null) return global;
  return firstSource(node, (n) => {
    if (ts.isIdentifier(n)) return HOST_OBJECTS.has(n.text) && !local.has(n.text) ? n.text : null;
    const name = memberName(n);
    if (name === "ownerDocument") return describe(n);
    if (name !== null && HOST_OBJECTS.has(name)) {
      const base = globalObjectName(n.expression, local);
      return base !== null ? `${base}.${name}` : null;
    }
    return null;
  });
}

/** A short spelling of an expression for a report: Object.prototype, Object.getPrototypeOf(...). */
function describe(node) {
  const n = unwrap(node);
  if (ts.isIdentifier(n)) return n.text;
  if (n.kind === ts.SyntaxKind.ThisKeyword) return "this";
  const name = memberName(n);
  if (name !== null) return `${describe(n.expression)}.${name}`;
  if (ts.isCallExpression(n)) return `${describe(n.expression)}(...)`;
  return "(...)";
}

/** A prototype an expression names: X.prototype or X["prototype"] for any X, or a getPrototypeOf(...) call. */
function prototypeName(node) {
  return firstSource(node, (n) => {
    if (memberName(n) === "prototype") return describe(n);
    if (ts.isCallExpression(n) && calleeName(n.expression) === "getPrototypeOf") return describe(n);
    return null;
  });
}

/**
 * A shared object whose members a read-only module may not write, or null: a prototype, a global
 * object, a global binding (an identifier the module does not declare: Object, document), or a
 * member of a global object (window.Object).
 */
function sharedObjectName(node, local) {
  const named = prototypeName(node) ?? globalObjectName(node, local);
  if (named !== null) return named;
  return firstSource(node, (n) => {
    if (ts.isIdentifier(n)) return isGlobalBinding(n, local) ? n.text : null;
    const name = memberName(n);
    if (name === null) return null;
    const base = globalObjectName(n.expression, local);
    return base !== null ? `${base}.${name}` : null;
  });
}

/** Identifiers that are not global bindings although no module declares them. */
const NOT_BINDINGS = new Set(["undefined", "NaN", "Infinity", "arguments"]);
const isGlobalBinding = (identifier, local) => !local.has(identifier.text) && !NOT_BINDINGS.has(identifier.text);

const WRAPPERS = (node) =>
  ts.isParenthesizedExpression(node) ||
  ts.isNonNullExpression(node) ||
  ts.isAsExpression(node) ||
  ts.isSatisfiesExpression(node) ||
  ts.isTypeAssertionExpression(node) ||
  ts.isExpressionWithTypeArguments(node);

const isAssignment = (kind) => kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment;

/**
 * Whether an expression is written: the left side of an assignment with any operator, the operand
 * of ++, -- or delete, the head of for-in or for-of, or a target inside a destructuring assignment
 * (`[x.a] = v`, `({ k: x.a } = v)`, `({ name } = v)`).
 */
function isWriteTarget(node) {
  let n = node;
  while (WRAPPERS(n.parent)) n = n.parent;
  const p = n.parent;
  if (ts.isBinaryExpression(p)) return p.left === n && isAssignment(p.operatorToken.kind);
  if (ts.isPrefixUnaryExpression(p) || ts.isPostfixUnaryExpression(p)) {
    return p.operator === ts.SyntaxKind.PlusPlusToken || p.operator === ts.SyntaxKind.MinusMinusToken;
  }
  if (ts.isDeleteExpression(p)) return true;
  if (ts.isForInStatement(p) || ts.isForOfStatement(p)) return p.initializer === n;
  // Destructuring: the literal holding the element is itself the target.
  if (ts.isArrayLiteralExpression(p)) return isWriteTarget(p);
  if (ts.isSpreadElement(p)) return ts.isArrayLiteralExpression(p.parent) && isWriteTarget(p.parent);
  if (ts.isSpreadAssignment(p)) return isWriteTarget(p.parent);
  if (ts.isPropertyAssignment(p)) return p.initializer === n && isWriteTarget(p.parent);
  if (ts.isShorthandPropertyAssignment(p)) return p.name === n && isWriteTarget(p.parent);
  return false;
}

/** Every name the module binds itself (variables, parameters, functions, classes, imports), with its declarations. */
function declarations(sf) {
  const names = new Map();
  const visit = (node) => {
    if (
      (ts.isVariableDeclaration(node) ||
        ts.isParameter(node) ||
        ts.isBindingElement(node) ||
        ts.isFunctionDeclaration(node) ||
        ts.isFunctionExpression(node) ||
        ts.isClassDeclaration(node) ||
        ts.isClassExpression(node) ||
        ts.isEnumDeclaration(node) ||
        ts.isModuleDeclaration(node) ||
        ts.isImportClause(node) ||
        ts.isImportSpecifier(node) ||
        ts.isNamespaceImport(node) ||
        ts.isImportEqualsDeclaration(node)) &&
      node.name !== undefined &&
      ts.isIdentifier(node.name)
    ) {
      if (!names.has(node.name.text)) names.set(node.name.text, []);
      names.get(node.name.text).push(node);
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return names;
}

/** A JSX attribute string as the JSX transform delivers it: numeric character references decoded. */
function jsxAttributeValue(text) {
  return text.replace(/&#(?:x([0-9a-f]+)|([0-9]+));?/gi, (whole, hex, dec) => {
    const code = Number.parseInt(hex ?? dec, hex !== undefined ? 16 : 10);
    return code <= 0x10ffff ? String.fromCodePoint(code) : whole;
  });
}

/** A javascript: URL as a browser's URL parser reads it (leading controls, tabs and newlines dropped). */
const isJavascriptUrl = (text) =>
  text
    .replace(/^[\x00-\x20]+/, "")
    .replace(/[\t\n\r]/g, "")
    .toLowerCase()
    .startsWith("javascript:");

const isFunctionLike = (node) =>
  ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isClassExpression(node);

/** A computed property name whose key is not a literal: `{ [k]: f }`. */
const isComputedKey = (name) => name !== undefined && ts.isComputedPropertyName(name) && !isLiteralKey(name.expression);

/** The last name of a callee or constructor expression: foo, a.b.foo, a["foo"]. */
function calleeName(node) {
  const n = unwrap(node);
  if (ts.isIdentifier(n)) return n.text;
  if (ts.isPropertyAccessExpression(n)) return n.name.text;
  if (ts.isElementAccessExpression(n) && isStringish(n.argumentExpression)) return n.argumentExpression.text;
  return null;
}

/** `import.meta.url`, possibly in parentheses. */
const isImportMetaUrl = (node) => {
  const n = node !== undefined ? unwrap(node) : undefined;
  return (
    n !== undefined &&
    ts.isPropertyAccessExpression(n) &&
    ts.isMetaProperty(n.expression) &&
    n.expression.keywordToken === ts.SyntaxKind.ImportKeyword &&
    n.name.text === "url"
  );
};

const isDocumentExpression = (node) =>
  valueSources(node).some(
    (n) => (ts.isIdentifier(n) && n.text === "document") || ["document", "ownerDocument"].includes(memberName(n)),
  );

/** Type syntax, which the build erases. A class's `extends X` is a value and is kept. */
function isErased(node) {
  if (ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node)) return true;
  if (ts.isImportDeclaration(node)) return node.importClause?.isTypeOnly === true;
  if (ts.isExportDeclaration(node)) return node.isTypeOnly;
  if (ts.isImportSpecifier(node) || ts.isExportSpecifier(node)) return node.isTypeOnly;
  if (ts.isImportEqualsDeclaration(node)) return node.isTypeOnly;
  if (ts.isExpressionWithTypeArguments(node)) {
    // Only an interface's extends and a class's implements are type syntax. A class's extends
    // and an instantiation expression `(expr)<T>` keep their expression in the emitted code.
    const clause = node.parent;
    if (!ts.isHeritageClause(clause)) return false;
    return !(clause.token === ts.SyntaxKind.ExtendsKeyword && ts.isClassLike(clause.parent));
  }
  return ts.isTypeNode(node);
}

/** Everything the rules need from one parsed source. */
function analyze(path, text) {
  const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, scriptKind(path));
  const lineOf = (node) => sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
  const declared = declarations(sf);
  const local = new Set(declared.keys());
  const facts = {
    /** Name -> the nodes that declare it, for the loader's options rule. */
    declared,
    // Syntax errors only (parseDiagnostics is what ts.createSourceFile records; no type check).
    parseErrors: (sf.parseDiagnostics ?? []).map((d) => ts.flattenDiagnosticMessageText(d.messageText, " ")),
    /** Runtime module edges: [specifier, line]. */
    imports: [],
    /** `new URL("...", import.meta.url)` paths, which Vite resolves like imports: [path, line]. */
    urlRefs: [],
    /** Rule 3 failures, by line. */
    badDynamicImports: [],
    badUrlRefs: [],
    glob: null,
    /** Rule 2 findings for read-only modules: label -> first line. */
    readOnlyUses: new Map(),
    /** Every `fetch` occurrence: { direct, call, line }. */
    fetches: [],
    dangerous: null,
    localStorage: null,
    authorization: null,
    /** A JSX pragma comment, which the AST rules cannot see: its line, or null. */
    jsxPragma: null,
  };
  const pragma = /@jsx(?:Frag|ImportSource|Runtime)?\b/.exec(text);
  if (pragma !== null) facts.jsxPragma = sf.getLineAndCharacterOfPosition(pragma.index).line + 1;
  const use = (label, node) => {
    if (!facts.readOnlyUses.has(label)) facts.readOnlyUses.set(label, lineOf(node));
  };
  const once = (key, node) => {
    if (facts[key] === null) facts[key] = lineOf(node);
  };

  /** A name spelled by an identifier, property name, JSX attribute or string literal. */
  const name = (text, node) => {
    const label = FORBIDDEN_NAMES.get(text);
    if (label !== undefined) use(label, node);
    if (text === "dangerouslySetInnerHTML") once("dangerous", node);
    if (text === "localStorage") once("localStorage", node);
  };

  const visit = (node) => {
    if (isErased(node)) return;

    if (ts.isIdentifier(node)) {
      name(node.text, node);
      if (node.text === "fetch") {
        const parent = node.parent;
        const direct = ts.isCallExpression(parent) && parent.expression === node;
        facts.fetches.push({ direct, call: direct ? parent : null, line: lineOf(node) });
      }
    } else if (isStringish(node)) {
      name(node.text, node);
      if (node.text === "fetch") facts.fetches.push({ direct: false, call: null, line: lineOf(node) });
      if (node.text.toLowerCase() === "authorization" || node.text.startsWith("Bearer ")) {
        once("authorization", node);
      }
      // A tag name in any string: as="form", const Tag = "iframe", createElement("script").
      const value = ts.isJsxAttribute(node.parent) ? jsxAttributeValue(node.text) : node.text;
      if (FORBIDDEN_TAGS.has(value.toLowerCase())) use(`<${value.toLowerCase()}>`, node);
      if (isJavascriptUrl(value)) use("a javascript: URL", node);
    } else if (ts.isTemplateHead(node)) {
      if (node.text.startsWith("Bearer ")) once("authorization", node);
      if (isJavascriptUrl(node.text)) use("a javascript: URL", node);
    }

    if (ts.isImportDeclaration(node) || (ts.isExportDeclaration(node) && node.moduleSpecifier !== undefined)) {
      if (ts.isStringLiteral(node.moduleSpecifier)) facts.imports.push([node.moduleSpecifier.text, lineOf(node)]);
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      const spec = node.moduleReference.expression;
      if (ts.isStringLiteral(spec)) facts.imports.push([spec.text, lineOf(node)]);
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      const [spec] = node.arguments;
      if (node.arguments.length === 1 && spec !== undefined && ts.isStringLiteral(spec)) {
        facts.imports.push([spec.text, lineOf(node)]);
      } else {
        facts.badDynamicImports.push(lineOf(node));
      }
    } else if (ts.isNewExpression(node) && calleeName(node.expression) === "URL" && node.arguments?.some(isImportMetaUrl)) {
      // Vite resolves and emits the file: an asset, or a worker's code inside new Worker(...).
      const [spec, base] = node.arguments;
      if (spec !== undefined && ts.isStringLiteral(spec) && isImportMetaUrl(base)) {
        facts.urlRefs.push([spec.text, lineOf(node)]);
      } else {
        facts.badUrlRefs.push(lineOf(node));
      }
    }

    if (ts.isMetaProperty(node) && node.keywordToken === ts.SyntaxKind.ImportKeyword) {
      const parent = node.parent;
      const member = ts.isPropertyAccessExpression(parent) && parent.expression === node ? parent.name.text : null;
      if (member !== "env" && member !== "url") use(`import.meta${member !== null ? `.${member}` : ""}`, node);
      if (member?.startsWith("glob")) once("glob", node);
    }

    if (ts.isElementAccessExpression(node)) {
      const target = indexedObjectName(node.expression, local);
      if (target !== null && !isLiteralKey(node.argumentExpression)) {
        use(`computed element access on ${target}`, node);
      }
    }

    // const { [k]: f } = globalThis, and ({ [k]: f } = window).
    if (
      ts.isObjectBindingPattern(node) &&
      (ts.isVariableDeclaration(node.parent) || ts.isParameter(node.parent)) &&
      node.parent.initializer !== undefined &&
      node.elements.some((element) => isComputedKey(element.propertyName))
    ) {
      const target = indexedObjectName(node.parent.initializer, local);
      if (target !== null) use(`computed destructuring of ${target}`, node);
    }
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isObjectLiteralExpression(unwrap(node.left)) &&
      unwrap(node.left).properties.some((prop) => isComputedKey(prop.name))
    ) {
      const target = indexedObjectName(node.right, local);
      if (target !== null) use(`computed destructuring of ${target}`, node);
    }

    // The Function constructor: x.constructor.constructor, (() => 0).constructor, and any
    // x.constructor(...) called as a function.
    if (
      (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) &&
      calleeName(node) === "constructor" &&
      (calleeName(node.expression) === "constructor" || isFunctionLike(unwrap(node.expression)))
    ) {
      use("the Function constructor", node);
    }
    if (ts.isCallExpression(node) && calleeName(node.expression) === "constructor") {
      use("a call of .constructor(...)", node);
    }

    // Writes to shared objects: X.prototype = v, Object.prototype.body = v, window.x = v,
    // Object.freeze = f, name = v, and Object.defineProperty(Object.prototype, ...) and the like.
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) && isWriteTarget(node)) {
      if (memberName(node) === "prototype") use(`a write to ${describe(node)}`, node);
      const target = sharedObjectName(node.expression, local);
      if (target !== null) use(`a write to a member of ${target}`, node);
    } else if (ts.isIdentifier(node) && isGlobalBinding(node, local) && isWriteTarget(node)) {
      use(`a write to the global ${node.text}`, node);
    }
    if (ts.isCallExpression(node) && MUTATORS.has(calleeName(node.expression)) && node.arguments.length > 0) {
      const target = sharedObjectName(node.arguments[0], local);
      if (target !== null) use(`${describe(node.expression)} on ${target}`, node);
    }

    if (ts.isCallExpression(node)) {
      const callee = calleeName(node.expression);
      if (callee !== null && (ELEMENT_FACTORIES.has(callee) || callee === "createElementNS")) {
        const tag = node.arguments[callee === "createElementNS" ? 1 : 0];
        const target = unwrap(node.expression);
        if (tag !== undefined && isStringish(tag)) {
          if (FORBIDDEN_TAGS.has(tag.text.toLowerCase())) use(`<${tag.text.toLowerCase()}>`, node);
        } else if (ts.isPropertyAccessExpression(target) && isDocumentExpression(target.expression)) {
          use("document.createElement with a computed tag", node);
        }
      }
    }

    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = ts.isIdentifier(node.tagName) ? node.tagName.text : null;
      if (tag !== null && FORBIDDEN_TAGS.has(tag)) use(`<${tag}>`, node);
    }

    if (
      (ts.isPropertyAssignment(node) || ts.isShorthandPropertyAssignment(node)) &&
      plainName(node.name)?.toLowerCase() === "authorization"
    ) {
      once("authorization", node);
    }
    if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isPropertyAccessExpression(unwrap(node.left)) &&
      unwrap(node.left).name.text.toLowerCase() === "authorization"
    ) {
      once("authorization", node);
    }

    ts.forEachChild(node, visit);
  };
  visit(sf);
  return facts;
}

/** Problems with one direct `fetch(url, OPTIONS)` call in the loader (rule 2). */
function loaderCallProblems(call, facts) {
  const options = call.arguments[1] !== undefined ? stripTypes(call.arguments[1]) : undefined;
  if (call.arguments.length !== 2 || options === undefined || !ts.isIdentifier(options)) {
    return [LOADER_CALL];
  }
  const name = options.text;
  const found = facts.declared.get(name) ?? [];
  if (found.length !== 1 || !isModuleConst(found[0])) {
    return [`${LOADER_CALL} (${name} is not declared once as a top-level const)`];
  }
  const literal = frozenWithoutPrototype(found[0].initializer, facts);
  return literal === null ? [LOADER_OPTIONS] : loaderInitProblems(literal);
}

const LOADER_CALL = "fetch must be called as fetch(url, OPTIONS), OPTIONS a top-level const of the loader";
const LOADER_OPTIONS =
  "fetch options must be built as Object.freeze(Object.assign(Object.create(null), { ... })): " +
  "with no prototype and frozen, so no inherited or added key reaches the request";

/** `const NAME = ...` directly in the module's top level (not ambient, not in a function or block). */
function isModuleConst(node) {
  if (!ts.isVariableDeclaration(node) || node.initializer === undefined || !ts.isIdentifier(node.name)) return false;
  const list = node.parent;
  const statement = list.parent;
  return (
    ts.isVariableDeclarationList(list) &&
    (list.flags & ts.NodeFlags.Const) !== 0 &&
    ts.isVariableStatement(statement) &&
    ts.isSourceFile(statement.parent) &&
    !(statement.modifiers ?? []).some((m) => m.kind === ts.SyntaxKind.DeclareKeyword)
  );
}

/** An expression with only parentheses, `!`, `as`, `satisfies` and `<T>` dropped (no comma). */
function stripTypes(node) {
  let n = node;
  while (WRAPPERS(n)) n = n.expression;
  return n;
}

/**
 * The `{ ... }` of `Object.freeze(Object.assign(Object.create(null), { ... }))`, each part possibly
 * wrapped in parentheses, `as` or `satisfies` (not in a comma), with Object the built-in one;
 * otherwise null.
 */
function frozenWithoutPrototype(node, facts) {
  if (facts.declared.has("Object")) return null;
  const objectCall = (n, method, arity) => {
    const call = stripTypes(n);
    const ok =
      ts.isCallExpression(call) &&
      ts.isPropertyAccessExpression(call.expression) &&
      ts.isIdentifier(call.expression.expression) &&
      call.expression.expression.text === "Object" &&
      call.expression.name.text === method &&
      call.arguments.length === arity;
    return ok ? call : null;
  };
  const freeze = objectCall(node, "freeze", 1);
  const assign = freeze !== null ? objectCall(freeze.arguments[0], "assign", 2) : null;
  const create = assign !== null ? objectCall(assign.arguments[0], "create", 1) : null;
  if (create === null || stripTypes(create.arguments[0]).kind !== ts.SyntaxKind.NullKeyword) return null;
  const literal = stripTypes(assign.arguments[1]);
  return ts.isObjectLiteralExpression(literal) ? literal : null;
}

/** Problems with the keys of the loader's options literal. */
function loaderInitProblems(init) {
  const out = [];
  let credentials = 0;
  let methods = 0;
  for (const prop of init.properties) {
    if (ts.isSpreadAssignment(prop)) {
      out.push("fetch options must not use a spread");
      continue;
    }
    const key = plainName(prop.name);
    if (key === null || !(ts.isPropertyAssignment(prop) || ts.isShorthandPropertyAssignment(prop))) {
      out.push("fetch options must be plain properties with identifier or string keys");
      continue;
    }
    const value = ts.isPropertyAssignment(prop) ? prop.initializer : prop.name;
    if (key === "body") {
      out.push("fetch options must not carry a body");
    } else if (!LOADER_INIT_KEYS.has(key)) {
      // __proto__ among them: `__proto__: { method: "POST" }` would be inherited by the init.
      out.push(`fetch options may only use the keys ${[...LOADER_INIT_KEYS].join(", ")} (not ${JSON.stringify(key)})`);
    }
    if (key === "method") {
      methods += 1;
      if (!(isStringish(value) && value.text.toUpperCase() === "GET")) {
        out.push('fetch method must be the string literal "GET" (any case)');
      }
    }
    if (key === "credentials") {
      credentials += 1;
      if (!(isStringish(value) && value.text === "omit")) credentials = Number.NEGATIVE_INFINITY;
    }
  }
  // Stated even though GET is the default: the init's method overrides a Request input's.
  if (methods < 1) out.push('fetch options must set method: "GET"');
  if (credentials < 1) out.push('fetch options must set credentials: "omit"');
  return out;
}

/** Run every rule over the web tree at `root`. Pure: nothing is printed or exited. */
export function checkBoundaries(webRoot) {
  const root = resolve(webRoot);
  const src = join(root, "src");
  const problems = [];
  const rel = (p) => relative(root, p).replaceAll("\\", "/");
  const tree = walk(src);
  for (const [path, why] of tree.refused) problems.push(`${rel(path)}: ${why}`);
  // Every script file: a .js, .jsx, .mjs or .cjs module is bundled as readily as a .ts one.
  const sources = tree.files.filter((p) => SCRIPT.test(p));
  const cache = new Map();
  const factsOf = (path) => {
    if (!cache.has(path)) cache.set(path, analyze(path, readFileSync(path, "utf-8")));
    return cache.get(path);
  };
  const isUnderSrc = (p) => p.startsWith(`${src}${sep}`);
  const shown = (spec) => (spec.length > 48 ? `${spec.slice(0, 45)}...` : spec);

  /**
   * Rule 3 for one specifier: every file it could name (see the header) is checked, and the
   * script ones under src are returned as { path, suffix } for rule 1 to follow.
   */
  const resolveSpec = (from, rawSpec, line) => {
    // A URL specifier is reported below (an import) or names no file (a new URL argument).
    if (URL_SPECIFIER.test(rawSpec)) return [];
    const at = `${rel(from)}: imports "${shown(rawSpec)}"`;
    // A bare specifier is a package in node_modules, not followed. "#x" is a package.json import
    // map entry, and a "." or ".." segment can climb out of the package.
    if (rawSpec.startsWith("#")) {
      problems.push(`${at}, which is not a plain package specifier (line ${line})`);
      return [];
    }
    // Vite splits a "?query" or "#hash" suffix off at the first ? or #.
    const cut = rawSpec.search(/[?#]/);
    const spec = cut < 0 ? rawSpec : rawSpec.slice(0, cut);
    const suffix = cut < 0 ? "" : rawSpec.slice(cut);
    if (!spec.startsWith(".") && !spec.startsWith("/")) {
      if (spec.split("/").some((segment) => segment === "." || segment === "..")) {
        problems.push(`${at}, which is not a plain package specifier (line ${line})`);
      }
      return [];
    }
    // Vite resolves "/src/..." against the project root.
    const base = spec.startsWith("/") ? join(root, spec) : resolve(dirname(from), spec);
    if (existsSync(join(base, "package.json"))) {
      problems.push(`${at}, a directory with a package.json (line ${line})`);
    }
    const counterpart = /\.(?:m|c)?jsx?$/.test(base)
      ? [base.replace(/\.(m|c)?js(x?)$/, ".$1ts$2"), base.replace(/\.js$/, ".tsx")]
      : [];
    const found = [
      ...new Set([
        base,
        ...counterpart,
        ...RESOLVE_EXTENSIONS.map((ext) => `${base}${ext}`),
        ...RESOLVE_EXTENSIONS.map((ext) => join(base, `index${ext}`)),
      ]),
    ].filter((candidate) => existsSync(candidate) && statSync(candidate).isFile());
    if (found.length === 0) problems.push(`${rel(from)}: cannot resolve import "${rawSpec}"`);
    const scripts = [];
    for (const path of found) {
      if (!isUnderSrc(path)) {
        problems.push(`${at}, which resolves outside src to ${rel(path)} (line ${line})`);
      } else if (SCRIPT.test(path)) {
        scripts.push({ path, suffix });
      } else if (!LEAF_EXTENSIONS.has(extname(path))) {
        problems.push(`${at}: ${rel(path)} is neither a script nor an allowed asset or style file (line ${line})`);
      } else if (!LEAF_SUFFIXES.has(suffix)) {
        problems.push(`${at}: an asset or style file may carry no suffix other than ?url or ?raw (line ${line})`);
      }
    }
    return scripts;
  };

  // Rule 3's resolution, for every source: file -> the script modules it references.
  const edges = new Map();
  for (const file of sources) {
    const facts = factsOf(file);
    const refs = [
      ...facts.imports,
      // A new URL path is relative to the module even without "./".
      ...facts.urlRefs.map(([path, line]) => [/^[./]/.test(path) || URL_SPECIFIER.test(path) ? path : `./${path}`, line]),
    ];
    edges.set(
      file,
      refs.flatMap(([spec, line]) => resolveSpec(file, spec, line).map((target) => ({ ...target, spec, line }))),
    );
  }

  const forbidden = (p) => {
    const r = rel(p);
    return r === "src/api.ts" || r.startsWith("src/panels/") || r.startsWith("src/views/");
  };

  const readOnlyRoots = sources.filter((p) => {
    const r = rel(p);
    return (
      r.startsWith("src/replay/") ||
      r.startsWith("src/board/") ||
      r.startsWith("src/components/") ||
      r === "src/format.ts" ||
      r === "src/types.ts"
    );
  });

  // Rule 1, collecting every script module a read-only root reaches. Rule 3 keeps them all under
  // src, so each is a source.
  const readOnly = new Set();
  const workerImports = [];
  for (const start of readOnlyRoots) {
    const seen = new Set();
    const stack = [[start, [start]]];
    while (stack.length > 0) {
      const [file, chain] = stack.pop();
      if (seen.has(file)) continue;
      seen.add(file);
      readOnly.add(file);
      for (const target of edges.get(file) ?? []) {
        if (/worker/i.test(target.suffix)) {
          workerImports.push(`${rel(file)}: read-only module imports "${target.spec}" as a worker (line ${target.line})`);
        }
        const next = [...chain, target.path];
        if (forbidden(target.path)) {
          problems.push(`read-only module reaches a mutating module: ${next.map(rel).join(" -> ")}`);
          continue;
        }
        stack.push([target.path, next]);
      }
    }
  }
  problems.push(...new Set(workerImports));

  // Rule 2.
  for (const file of readOnly) {
    const facts = factsOf(file);
    const isLoader = rel(file) === LOADER;
    for (const [label, line] of facts.readOnlyUses) {
      if (isLoader && label === "fetch") continue;
      problems.push(`${rel(file)}: read-only module uses ${label} (line ${line})`);
    }
    if (!isLoader) continue;
    for (const f of facts.fetches) {
      const found = f.direct
        ? loaderCallProblems(f.call, facts)
        : ["fetch is used other than as a direct call fetch(url, OPTIONS)"];
      for (const p of new Set(found)) problems.push(`${rel(file)}: ${p} (line ${f.line})`);
    }
  }

  // Rules 3 (with the resolution above) to 5, and parse errors.
  for (const file of sources) {
    const facts = factsOf(file);
    for (const message of facts.parseErrors) problems.push(`${rel(file)}: does not parse: ${message}`);
    for (const line of facts.badDynamicImports) {
      problems.push(`${rel(file)}: dynamic import() must take a quoted literal specifier (line ${line})`);
    }
    for (const line of facts.badUrlRefs) {
      problems.push(`${rel(file)}: new URL(..., import.meta.url) must take a quoted literal path (line ${line})`);
    }
    if (facts.glob !== null) problems.push(`${rel(file)}: uses import.meta.glob (line ${facts.glob})`);
    for (const [spec, line] of facts.imports) {
      if (URL_SPECIFIER.test(spec)) problems.push(`${rel(file)}: imports a URL module specifier "${shown(spec)}" (line ${line})`);
    }
    if (facts.dangerous !== null) problems.push(`${rel(file)}: uses dangerouslySetInnerHTML (line ${facts.dangerous})`);
    if (facts.jsxPragma !== null) {
      problems.push(`${rel(file)}: holds a JSX pragma comment, which changes what esbuild emits (line ${facts.jsxPragma})`);
    }
    if (facts.localStorage !== null) {
      problems.push(`${rel(file)}: uses localStorage (tokens must stay per tab) (line ${facts.localStorage})`);
    }
    if (rel(file) !== "src/api.ts" && facts.authorization !== null) {
      problems.push(`${rel(file)}: sets authorization outside src/api.ts (line ${facts.authorization})`);
    }
  }

  // Rule 6, over every file under src (a JSON or text leaf included) and the bundle.
  const dist = join(root, "dist");
  const distScanned = existsSync(dist);
  for (const file of [...tree.files, ...(distScanned ? walk(dist).files : [])]) {
    const text = readFileSync(file, "utf-8");
    for (const marker of PRIVATE_MARKERS) {
      if (text.includes(marker)) problems.push(`${rel(file)}: contains private marker "${marker}"`);
    }
  }

  return { problems: [...new Set(problems)], readOnlyModules: readOnly.size, sources: sources.length, distScanned };
}

if (process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), ".."));
  const result = checkBoundaries(root);
  if (result.problems.length > 0) {
    console.error(`Boundary check failed (${result.problems.length}):`);
    for (const p of result.problems) console.error(`  - ${p}`);
    process.exit(1);
  }
  console.log(
    `Boundary check passed: ${result.readOnlyModules} read-only modules, ${result.sources} sources` +
      `${result.distScanned ? ", dist bundle" : ""} scanned.`,
  );
}
