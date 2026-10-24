// Project invariants that TypeScript cannot check. Exits non-zero on any violation.
//
// 1. Read-only modules (src/replay, src/board, src/components, src/format.ts, src/types.ts)
//    never import, directly or transitively, src/api.ts, src/panels/ or src/views/: the replay
//    renders the board and must not be able to reach a tool or moderator call.
// 2. No dangerouslySetInnerHTML anywhere: user text is rendered as text.
// 3. Session tokens live in sessionStorage only: no localStorage, no Authorization header
//    outside src/api.ts.
// 4. No private runner vocabulary in sources or the built bundle.

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "src");
const problems = [];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else out.push(path);
  }
  return out;
}

const sources = walk(src).filter((p) => /\.(ts|tsx)$/.test(p));
const rel = (p) => relative(root, p).replaceAll("\\", "/");

const IMPORT_RE = /(?:import|export)\s+(?:type\s+)?(?:[^"'`;]*?\s+from\s+)?["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g;

function importsOf(file) {
  const text = readFileSync(file, "utf-8");
  const specs = [];
  for (const m of text.matchAll(IMPORT_RE)) {
    const spec = m[1] ?? m[2];
    // Type-only imports are erased at build time and cannot reach runtime code.
    if (/^import\s+type\s/.test(m[0]) || /^export\s+type\s/.test(m[0])) continue;
    specs.push(spec);
  }
  return specs;
}

function resolveSpec(from, spec) {
  if (!spec.startsWith(".")) return null;
  const base = resolve(dirname(from), spec);
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx")]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  problems.push(`${rel(from)}: cannot resolve import "${spec}"`);
  return null;
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

for (const start of readOnlyRoots) {
  const seen = new Set();
  const stack = [[start, [start]]];
  while (stack.length > 0) {
    const [file, chain] = stack.pop();
    if (seen.has(file)) continue;
    seen.add(file);
    for (const spec of importsOf(file)) {
      const target = resolveSpec(file, spec);
      if (target === null) continue;
      const next = [...chain, target];
      if (forbidden(target)) {
        problems.push(`read-only module reaches a mutating module: ${next.map(rel).join(" -> ")}`);
        continue;
      }
      stack.push([target, next]);
    }
  }
}

for (const file of sources) {
  const text = readFileSync(file, "utf-8");
  if (text.includes("dangerouslySetInnerHTML")) problems.push(`${rel(file)}: uses dangerouslySetInnerHTML`);
  if (/\blocalStorage\b/.test(text)) problems.push(`${rel(file)}: uses localStorage (tokens must stay per tab)`);
  if (rel(file) !== "src/api.ts" && /\.Authorization\s*=|["']Authorization["']\s*:|[`"']Bearer /.test(text)) {
    problems.push(`${rel(file)}: sets authorization outside src/api.ts`);
  }
  if (rel(file).startsWith("src/replay/") && /method:\s*["'](POST|PUT|PATCH|DELETE)["']/.test(text)) {
    problems.push(`${rel(file)}: replay code issues a non-GET request`);
  }
}

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
const dist = join(root, "dist");
const scanned = [...sources, ...(existsSync(dist) ? walk(dist) : [])];
for (const file of scanned) {
  const text = readFileSync(file, "utf-8");
  for (const marker of PRIVATE_MARKERS) {
    if (text.includes(marker)) problems.push(`${rel(file)}: contains private marker "${marker}"`);
  }
}

if (problems.length > 0) {
  console.error(`Boundary check failed (${problems.length}):`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(
  `Boundary check passed: ${readOnlyRoots.length} read-only modules, ${sources.length} sources` +
    `${existsSync(dist) ? ", dist bundle" : ""} scanned.`,
);
