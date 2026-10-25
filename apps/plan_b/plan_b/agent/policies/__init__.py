"""The model-driven comparison policies of the evaluation plan (``08_evaluation.md``).

* P1 ``tool_use``: ``tool-use/1.0.0``, an ordinary tool-using model baseline that chooses tools
  and arguments itself from the coordinator grant's tools;
* P2 ``selective``: ``live/1.0.0``, the selective verify/prepare/commit controller;
* P3 ``verify_all``: ``verify-all/1.0.0``, P2's downstream logic with every relevant status
  check requested first.

P0 is the deterministic baseline of each profile (``evaluation/policies/rules.py`` and
``pantry_rules.py``). Every policy reaches the event only through a ``ToolClient`` and the
shared executor, under the same grants, candidates, tools and per-episode caps.
"""
