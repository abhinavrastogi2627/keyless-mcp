# keyless-mcp developer commands. Run `make` to list them.
# Needs uv (https://docs.astral.sh/uv/). Everything else is installed by `make setup`.

export PATH := $(HOME)/.local/bin:$(PATH)
PY := .venv/bin/python
M3 := scripts/m3
TOOLSET ?= dev
HARNESS ?= claude
MODEL ?= sonnet
TRIALS ?= 1
BENCH_ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help setup test benchmark benchmark-baseline test-live agent record new-adapter adapters-md lint fmt ui run tools

help: ## List the available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-18s %s\n", $$1, $$2}'

setup: ## Install everything (Python 3.12 venv, dependencies, M3 SDK) and check it works
	uv sync --locked
	$(M3) setup --python $(PY)
	$(M3) doctor

test: ## Run all tests offline (replays cassettes; no network, no API keys)
	KEYLESS_MCP_HTTP_MODE=replay $(M3) test --python $(PY) -- m3_tests -m "not live and not agent" -q
	@echo "tip: run 'make benchmark' to check that the M3 benchmark scores did not go down (CI does)."

benchmark: ## Check the last M3 run against the baseline: benchmark scores must not go down
	uv run python scripts/benchmark.py --check $(BENCH_ARGS)

benchmark-baseline: ## Save the last M3 run as benchmarks/baseline.json to lock in a higher score
	uv run python scripts/benchmark.py --update $(BENCH_ARGS)

test-live: ## Run the live smoke tests against the real APIs (needs network)
	KEYLESS_MCP_HTTP_MODE=live $(M3) test --python $(PY) -- m3_tests -m "live and not agent" -q

agent: ## Real-agent tool-selection tests (costs tokens): make agent HARNESS=codex MODEL=<id> TRIALS=3 [K=osv M3_ARGS=...]
	@# Needs a harness CLI plus credentials; see docs/agent-testing.md and .env.example.
	KEYLESS_MCP_HTTP_MODE=live $(M3) test --python $(PY) --harness $(HARNESS)=$(MODEL) --trials $(TRIALS) $(M3_ARGS) -- m3_tests/agent -m agent $(if $(K),-k "$(K)") -q -rs

record: ## Re-record an adapter's cassettes from the real API and replay-check them: make record ADAPTER=arxiv
	@test -n "$(ADAPTER)" || { echo "usage: make record ADAPTER=<name>"; exit 1; }
	@test -d m3_tests/adapters/$(ADAPTER) || { echo "no such adapter: $(ADAPTER)"; exit 1; }
	@# Record into a temp dir; the committed cassettes are replaced only if every test passed, then replayed once to check.
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	if KEYLESS_MCP_HTTP_MODE=record KEYLESS_MCP_RECORD_ROOT="$$tmp" $(M3) test --python $(PY) -- m3_tests/adapters/$(ADAPTER) -m "not live and not agent" -q; then \
	  ls "$$tmp/$(ADAPTER)"/*.json >/dev/null 2>&1 || { echo "record: no requests were recorded; existing cassettes kept"; exit 1; }; \
	  mkdir -p m3_tests/adapters/$(ADAPTER)/cassettes && \
	  rm -f m3_tests/adapters/$(ADAPTER)/cassettes/*.json && \
	  cp "$$tmp/$(ADAPTER)"/*.json m3_tests/adapters/$(ADAPTER)/cassettes/ && \
	  echo "record: wrote $$(ls m3_tests/adapters/$(ADAPTER)/cassettes/*.json | wc -l | tr -d ' ') cassette(s) to m3_tests/adapters/$(ADAPTER)/cassettes"; \
	  echo "record: replaying the new cassettes offline to check them"; \
	  KEYLESS_MCP_HTTP_MODE=replay $(M3) test --python $(PY) -- m3_tests/adapters/$(ADAPTER) -m "not live and not agent" -q || { \
	    echo "record: the new cassettes are in place but a replay test failed, so it pins a value that moves upstream."; \
	    echo "record: fix that test: read the expected value from the cassette (m3_tests/_support/cassettes.py, 'Frozen in replay, shape in live' in docs/adapter-contract.md)."; \
	    echo "record: or restore the old cassettes with: git checkout m3_tests/adapters/$(ADAPTER)/cassettes"; \
	    exit 1; }; \
	else \
	  echo "record: tests failed against the live API; existing cassettes were left untouched"; exit 1; \
	fi

new-adapter: ## Scaffold an adapter: make new-adapter NAME=open_meteo TOOLSET=geo
	@test -n "$(NAME)" || { echo "usage: make new-adapter NAME=<name> [TOOLSET=science|dev|geo|news|finance|reference|fun]"; exit 1; }
	uv run python scripts/new_adapter.py $(NAME) --toolset $(TOOLSET)

adapters-md: ## Regenerate ADAPTERS.md from the adapters and docs/results/agent-*-latest.json
	uv run python scripts/gen_adapters_md.py

lint: ## Check code style (ruff check + ruff format --check)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .

ui: ## Open the M3 results viewer for saved runs
	$(M3) ui

run: ## Start the server on stdio
	uv run keyless-mcp

tools: ## List every registered tool with its toolset
	uv run keyless-mcp --list-tools
