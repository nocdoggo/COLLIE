# Data the app's tests and demo read

- `planning/examples/` and `planning/schemas/`: the planning examples and the planning schema
  that the contract tests check the runtime models against (copied from the planning bundle).
- `recorded/`: recorded traces of real runs. The demo's offline replay (`scripts/demo_prep.py`)
  serves them, and the release tests check that they replay offline. `recorded/wave_1/` holds
  one deterministic trace that a pantry test reads. Traces are never edited.
