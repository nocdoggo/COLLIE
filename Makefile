# COLLIE — Cost-aware OR-LLM Liaison for Inventory Exceptions
#
# The InventoryBench submodule at third_party/ is READ-ONLY. No target here may
# write to it. Only collie/adapter/ may import from it.

SHELL := /bin/bash
BENCH := third_party/InventoryBench
UV    := uv
TABLE_RECORDS ?= reports/dev_records.jsonl
TABLE_OUT ?= reports/eval

.DEFAULT_GOAL := help
.PHONY: help setup lfs-size lint fmt test test-fast equivalence equivalence-set arm1 bench-or audit freeze-contracts check-freeze freeze table-main artifact clean gate1

help:  ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## verify host tooling, init the pinned submodule, fetch LFS objects, sync the env
	@command -v git-lfs >/dev/null 2>&1 || { \
	  echo "ERROR: git-lfs is not installed."; \
	  echo "  All 1,320 benchmark CSVs are LFS-tracked (see $(BENCH)/.gitattributes),"; \
	  echo "  so without git-lfs you get pointer files and the audit cannot parse them."; \
	  echo "  Install:  sudo apt-get install git-lfs && git lfs install"; \
	  exit 1; }
	@command -v $(UV) >/dev/null 2>&1 || { echo "ERROR: uv is not installed. See https://docs.astral.sh/uv/"; exit 1; }
	git submodule update --init --recursive
	@$(MAKE) --no-print-directory lfs-size
	cd $(BENCH) && git lfs pull
	$(UV) sync --all-extras
	@echo "setup complete. try: make test && make bench-or"

lfs-size:  ## report the LFS payload size before fetching it (disk is tight)
	@echo "LFS payload pending in $(BENCH):"
	@cd $(BENCH) && git lfs ls-files -s 2>/dev/null \
	  | sed 's/.* - .* (\(.*\))/\1/' \
	  | awk '{ if ($$2=="KB") s+=$$1*1024; else if ($$2=="MB") s+=$$1*1048576; else if ($$2=="GB") s+=$$1*1073741824; else s+=$$1 } \
	         END { printf "  %.1f MB across %d files\n", s/1048576, NR }'
	@echo "free space on this filesystem:"
	@df -h . | tail -1 | awk '{printf "  %s free of %s (%s used)\n", $$4, $$2, $$5}'

lint:  ## ruff check + format check (never touches third_party/)
	$(UV) run ruff check collie tests tools
	$(UV) run ruff format --check collie tests tools

fmt:  ## apply ruff formatting
	$(UV) run ruff format collie tests tools
	$(UV) run ruff check --fix collie tests tools

test:  ## full test suite with coverage
	$(UV) run pytest --cov=collie --cov-report=term-missing

test-fast:  ## skip slow and benchmark-dependent tests
	$(UV) run pytest -m "not slow and not needs_benchmark and not needs_llm and not equivalence"

equivalence:  ## Task 4: differential accounting equivalence vs the official pipeline
	@# The instance list is committed, so a stale list is an error rather than a silent
	@# re-selection: the equivalence claim has to refer to a fixed set of instances.
	$(UV) run python -m tools.select_equivalence_set --check
	$(UV) run pytest -m equivalence -q
	@echo "report: reports/equivalence_report.md"

equivalence-set:  ## regenerate manifests/equivalence_instances.txt (deliberate act; commit the diff)
	$(UV) run python -m tools.select_equivalence_set

INSTANCE ?= $(BENCH)/benchmark/synthetic_trajectory/lead_time_0/p01_stationary_iid/v1_normal_100_25/r1_med

bench-or:  ## Task 1 demo: run the official OR agent on one synthetic instance
	@# The submodule stays read-only: we import it via PYTHONPATH from OUR venv,
	@# never `uv run --project third_party/...` (that would write a .venv into it).
	PYTHONPATH=$(BENCH) $(UV) run python $(BENCH)/scripts/run_or.py \
	  --demand-file $(INSTANCE)/test.csv \
	  --real-instance-train $(INSTANCE)/train.csv \
	  --promised-lead-time 0

arm1:  ## Task 5: run arm 1 over all 1,320 instances under both harnesses and compare to published OR
	$(UV) run python -m tools.run_arm1 --harness both --report
	@echo "report: reports/arm1_or_baseline.md"

audit:  ## Task 2: regenerate manifests/benchmark_v1.json and docs/env_contract.md inputs
	$(UV) run python -m tools.audit_benchmark --out manifests/benchmark_v1.json

freeze-contracts:  ## Gate 1: record the hash of collie/contracts.py in prereg/contract_freeze.json
	$(UV) run python -m tools.freeze_contracts

check-freeze:  ## Gate 1 guard: fail if a frozen contract changed without a declared deviation
	$(UV) run python -m tools.freeze_contracts --check

freeze:  ## Task 19: hash every registered method file
	$(UV) run python -m tools.freeze

table-main:  ## Task 24: render the main table and Pareto frontiers
	$(UV) run python -m collie.eval.report --table main --records $(TABLE_RECORDS) --out-dir $(TABLE_OUT)

artifact:  ## Task 32: build the release bundle and reproducibility audit log
	$(UV) run python -m tools.package_artifact

gate1:  ## verify every Gate 1 condition in one command
	@echo "== lint =="            && $(MAKE) --no-print-directory lint
	@echo "== contract freeze ==" && $(MAKE) --no-print-directory check-freeze
	@echo "== audit manifest ==" \
	  && $(UV) run python -m tools.audit_benchmark --out /tmp/collie_audit_check.json --quiet \
	  && diff -q manifests/benchmark_v1.json /tmp/collie_audit_check.json \
	  && echo "manifest current"
	@echo "== equivalence =="     && $(MAKE) --no-print-directory equivalence
	@echo "== full suite =="      && $(UV) run pytest -q
	@echo
	@echo "GATE 1 conditions verified. Remaining manual step: commit and tag."

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find collie tests tools -name __pycache__ -type d -prune -exec rm -rf {} +
