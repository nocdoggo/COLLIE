// Keyboard reach of the board (W3.3): the section links name the current plan, the evidence,
// the latest decision and the action status (and the pantry quantities when there is stock),
// and every board section can take focus from them. tests/e2e/keyboard.py drives the same links
// in a browser.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { BoardJumps, BoardView } from "../src/board/BoardView.tsx";
import { makeView } from "./support/view.ts";
import { makePantryView } from "./support/wave2.ts";

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
