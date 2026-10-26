// Keyboard reach of the board (W3.3): the section links name the current plan, the evidence,
// the latest decision and the action status (and the pantry quantities when there is stock),
// and every board section can take focus from them. tests/e2e/keyboard.py drives the same links
// in a browser.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { BoardJumps, BoardView } from "../src/board/BoardView.tsx";
import { local, makeView, textOf } from "./support/view.ts";
import { liveDecision, makePantryView } from "./support/wave2.ts";

function jumps(html: string): string[] {
  const nav = /<nav class="board-jumps" aria-label="Board sections">(.*?)<\/nav>/s.exec(html);
  assert.ok(nav, "the board renders its section links");
  return [...(nav[1] ?? "").matchAll(/<button[^>]*>(.*?)<\/button>/g)].map((m) => m[1] ?? "");
}

test("the campus board links to the plan, evidence, latest decision and action status", () => {
  const html = renderToStaticMarkup(createElement(BoardView, { view: makeView(), mode: "live" }));
  assert.deepEqual(jumps(html), ["Current plan", "Evidence", "Latest decision", "Action status"]);
  for (const id of ["schedule", "status-checks", "what-changed", "action-history"]) {
    assert.match(html, new RegExp(`<section id="${id}" aria-labelledby="${id}-title" class="card[^"]*" tabindex="-1"`), id);
  }
});

test("the pantry board also links to its stock and service quantities", () => {
  const html = renderToStaticMarkup(createElement(BoardView, { view: makePantryView("committed"), mode: "replay" }));
  assert.deepEqual(jumps(html), ["Current plan", "Stock and service", "Evidence", "Latest decision", "Action status"]);
  assert.match(html, /<section id="pantry-board" aria-labelledby="pantry-board-title" class="card[^"]*" tabindex="-1"/);
});

test("the section links are buttons, so they work with Tab and Enter without a route change", () => {
  const html = renderToStaticMarkup(createElement(BoardJumps, { view: makeView() }));
  assert.equal((html.match(/<button type="button" class="link-button">/g) ?? []).length, 4);
  assert.ok(!html.includes("href="));
});

// tests/e2e/keyboard.py checks the next wake only when the API reports one, and the
// deterministic policy sets none, so the board's wake text is checked here.
test("the latest decision names its next wake on the board", () => {
  const view = makeView({
    decisions: [liveDecision({ kind: "wait", summary: "Waiting for the projector's ETA.", wait_until: local("17:25") })],
  });
  const text = textOf(renderToStaticMarkup(createElement(BoardView, { view, mode: "live" })));
  assert.ok(text.includes("waiting until 17:25"), text);
});
