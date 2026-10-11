# Agent testing

keyless-mcp has two kinds of agent test. They answer different questions, so they run in
different places.

| Lane | File | Marker | Needs | Runs in |
|---|---|---|---|---|
| Scripted agent | `m3_tests/agent/test_fixture_agent.py` | `agent_fixture` | nothing | `make test`, PR CI |
| Real agent | `m3_tests/agent/test_tool_selection.py` | `agent` + `live` | an agent CLI, model access, network | `make agent` only |

## Lane 1: the scripted agent (offline, every PR)

A tiny deterministic ACP agent (`m3_tests/_support/scripted_acp_agent.py`) stands in for a coding
agent. There is no model. The prompt is a JSON script of tool calls, and the agent makes exactly
those calls against the keyless-mcp server that M3 hands it, then reports the results.

What it proves: M3 can launch an agent, give it the server, capture its tool calls off the wire
and assert on them with `expect(result).to_have_tool_call(...)`, with the server replaying
recorded cassettes (no network, no keys). If this lane breaks, the agent test machinery is broken,
not the model.

What it does not prove: that a real model picks the right tool. That is lane 2.

The lane is marked `agent_fixture`, not `agent`, so `make test` includes it. Its server is pinned
to replay mode, so it stays offline even if `KEYLESS_MCP_HTTP_MODE=live` is exported.

## Lane 2: a real agent picks the tool (costs tokens)

`test_tool_selection.py` is a table of plain-English prompts, at least one per adapter, for
example "Are there known security vulnerabilities in version 2.4.1 of the PyPI package jinja2?".
No prompt names a tool. The agent gets every keyless tool (`make tools` lists them) and the test asserts, from the call M3
recorded on the wire, that it called the right one (here `osv_query_package` with ecosystem PyPI,
name `jinja2`, version `2.4.1`) and that the call succeeded. Look-alike tools that would be the
wrong choice (`npm_get_package` for a PyPI question) are asserted not to be called.

The server runs live (real upstream APIs), so these tests need network and cost model tokens.

Run it:

```sh
make agent HARNESS=claude MODEL=sonnet                 # one trial of every prompt
make agent HARNESS=codex MODEL=<model id> TRIALS=5     # five trials of every prompt
make agent HARNESS=codex MODEL=<model id> K="osv-query or hackernews-top"   # a cheap subset
```

`K` filters prompts by id (see `CASES` in the test file), `TRIALS` sets repeats, and `M3_ARGS`
passes extra `m3 test` options such as `--credential-env`.

### What each harness needs

M3 starts every harness in an isolated home, so it does not see most of your local logins. Put
credentials in `.env` (see `.env.example`); `m3 test` loads it.

- **Claude Code** (`HARNESS=claude`): `ANTHROPIC_API_KEY`. Your own `claude` login is not used,
  because the isolated home hides it. A subscription token from `claude setup-token` also works
  when mapped with `M3_ARGS="--credential-env claude:CLAUDE_CODE_OAUTH_TOKEN=CLAUDE_CODE_OAUTH_TOKEN"`.
- **Codex** (`HARNESS=codex`): reuses your `codex login` automatically, or set `OPENAI_API_KEY`.
  Codex has its own web search and, left alone, answers from that instead of the server. So the
  test adds a short hint to each Codex prompt: use only the `keyless` MCP server's tools, do not
  browse the web. The hint names no tool. Hints live in `HARNESS_HINTS` in `test_tool_selection.py`,
  keyed by harness kind. A harness gets one only if it needs it. Claude Code gets none because M3
  turns its built-in tools off, and an unlisted harness gets the bare prompt. Add an entry if a
  harness turns out to bypass the server.
- **OpenCode / Pi**: `MODEL=provider/model` plus that provider's key.

If the CLI is missing or no credential is found, the tests skip with the reason printed. They
never pass without running. M3 treats a run where everything skipped as a failure, so
`make agent` exits non-zero in that case; that is deliberate, since nothing was tested. Without
`--harness`, as in `make test`, `test_tool_selection.py` is not collected at all.

## How pass rates work

Each prompt is one test. `--trials N` collects it N times, and each trial is a separate execution
with its own pass or fail; trials are repeats, not retries. A prompt's pass rate is
passed trials / N. M3 prints every trial and saves them under `.m3/` (`make ui` browses them).

Report every trial. Do not rerun only the failures and keep the best score. A handful of trials is
an observation about one model on one day, not a stable rate, and model behaviour changes between
versions, so compare runs with the same harness, model and trial count.

## Reading a failure

The assertion message lists the calls the agent actually made (`candidates=[...]`). Read it
against these cases:

- **No calls at all (`candidates=[]`).** The agent answered from memory, or from a built-in
  tool such as web search, and never used keyless-mcp. Check the final answer in the trace. Fix:
  sharpen the tool descriptions, or the server `instructions`, so the agent reaches for them.
- **A call to the wrong tool.** The agent used keyless-mcp but picked a neighbouring tool (for
  example `pypi_get_package` where `osv_query_package` was right) or filled arguments wrongly.
  Read the two tools' descriptions side by side and make them more distinct.
- **Right tool, status not `success`.** The tool returned an error. This is a server or upstream
  problem, not tool selection. Reproduce it with the adapter's own tests (`make test`) or by
  calling the tool directly with the arguments shown in the trace.
- **Skipped.** The harness is not installed or has no credential. Nothing was tested.

A single failure on a single trial can be the model having an off run. A prompt that fails across
several trials points at the descriptions.

## Latest results

`docs/results/agent-codex-latest.json` holds the most recent full run (Codex, 1 trial per prompt):
per prompt, the expected tool and passed/total trials. It is a snapshot of one model on one day.

The nightly agent job compares each prompt's pass rate with the committed file and fails if one has dropped (`scripts/benchmark.py --agent`). It does not commit anything: after a deliberate improvement, copy the new file from the `agent-results-<harness>` artifact into `docs/results/` and run `make adapters-md`. Pull requests never run this lane. Their benchmark is the offline one in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Adding a prompt

Add a `Case(...)` to `CASES` in `test_tool_selection.py`: an id, a plain-English prompt that does
not name a tool, the acceptable tool names, and a check on the key arguments. If a similar tool
could be picked by mistake, list it in `must_not_call`.
