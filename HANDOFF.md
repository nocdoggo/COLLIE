# Handoff — next agent entry point (9 November 2026)

The complete handoff lives in the study's private records directory (this repo does not
carry private records; the path below is absolute on the study machine):

```
/data/noctis/GitHub-Data/COLLIE/owner_review/14_2026-10-29_execution/HANDOFF_2026-11-09/
```

Read, in this order:

1. `NEXT_AGENT_PROMPT.md` — the full prompt for a fresh session: hard constraints, current
   state, the ordered task list (T1–T9), reference values, and the amendment-cycle recipe.
2. `MAIN_HANDOFF.md` — the same content organized as a state snapshot plus the task list
   and key reference values (HEAD `5356928…` = A18; 8 of 17 batch runs complete).
3. `ITEM58_CAPTURE_COMMAND.py` — ready-to-execute diagnosis of the current batch blocker
   (item 58 of `e3-a.s7.dk`); its header comment carries the exact command. Run it first.
4. `CONTINUATION_HANDOFF_2026-11-05.md` — the prior handoff; its §7 (closeout) and §9
   (failure handling) still govern.

Start at T1 (the item-58 diagnosis), then finish the batch under amendment A19, close out,
repair and apply the scorer (A20), pool the completed condition, and take the paper through
its checklist. Every rule that binds execution is in the prompt, not here.
