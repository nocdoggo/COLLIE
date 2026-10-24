"""Live model-driven coordinator (Wave 2, W2.1): provider, interpretation and bounded loop.

``config`` reads the non-secret endpoint configuration, ``provider`` is the standard-library
chat-completions client with its spend guard, ``interpret`` turns notices into planning
``change_spec`` records, ``menu`` builds the closed action menu, ``orchestrator`` is the
``live/1.0.0`` policy and ``gate`` runs the G-LLM gate. The policy sees only tool envelopes
through a ``ToolClient``; every effect goes through the shared executor.
"""
