// Node module hooks for `npm test`: transpile the app's .ts/.tsx sources with the project's own
// TypeScript (JSX included) and resolve the extensionless relative imports Vite accepts, so
// tests can import components and render them with react-dom/server. Test-only; not bundled.

import { existsSync, statSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const SOURCE = /\.tsx?$/;

function isFile(url) {
  const path = fileURLToPath(url);
  return existsSync(path) && statSync(path).isFile();
}

export async function resolve(specifier, context, nextResolve) {
  const relative = specifier.startsWith("./") || specifier.startsWith("../");
  if (relative && context.parentURL?.startsWith("file:") && !/\.[cm]?[jt]sx?$|\.json$/.test(specifier)) {
    for (const ext of [".ts", ".tsx"]) {
      const url = new URL(specifier + ext, context.parentURL);
      if (isFile(url)) return { url: url.href, shortCircuit: true };
    }
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (!url.startsWith("file:") || !SOURCE.test(url) || url.includes("/node_modules/")) {
    return nextLoad(url, context);
  }
  const fileName = fileURLToPath(url);
  const output = ts.transpileModule(await readFile(fileName, "utf-8"), {
    fileName,
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      verbatimModuleSyntax: true,
      useDefineForClassFields: true,
      inlineSourceMap: true,
    },
  });
  return { format: "module", source: output.outputText, shortCircuit: true };
}
