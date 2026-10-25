"""Live model-driven coordinator (Wave 2, W2.1): provider, interpretation and bounded loop.

``config`` reads the non-secret endpoint configuration, ``provider`` is the standard-library
chat-completions client with its spend guard, ``interpret`` turns notices into planning
``change_spec`` records, ``menu`` builds the closed action menu, ``attention`` is the shared
rule for when a model call is warranted (and the shared wake schedule and server narration),
``orchestrator`` is the ``live/1.2.0`` policy and ``gate`` runs the G-LLM gate. ``policies``
names the evaluation plan's model-driven comparison policies: P1 ``tool_use``
(``tool-use/1.2.0``), P2 ``selective`` (the ``live/1.2.0`` policy) and P3 ``verify_all``
(``verify-all/1.2.0``). Every policy sees only tool envelopes through a ``ToolClient``; every
effect goes through the shared executor.
"""
