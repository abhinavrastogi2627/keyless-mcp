# Launch checklist

Work through this top to bottom. Items marked TODO are things the build left for you. The
workflow files have their own setup notes in their header comments, and the relevant ones are
repeated here so you do not have to hunt for them.

## 1. Before the first push

- [ ] The `finance`, `reference` and `fun` toolsets are already in the code (they have no adapters yet, so ADAPTERS.md lists them as waiting). Run `make test`, `make lint` and `uv run python scripts/gen_adapters_md.py --check` once more before you push.
- [ ] Read `README.md` once more on GitHub's renderer after the push. Its links are absolute and only work once the repository exists at `github.com/sineframe/keyless-mcp`.
- [ ] TODO (optional): record a short screen capture of an agent using a tool. The README uses a text transcript instead of a GIF, so nothing links to `docs/demo.gif` yet. If you record one, add it to the README and commit it.
- [ ] Check that no file contains a key, a token or a personal path: `git grep -nE "(sk-|ghp_|AKIA)" -- . ":!docs/launch/checklist.md"` should print nothing.

## 2. Create the repository

- [ ] Create `github.com/sineframe/keyless-mcp` as a public repository and push `main`.
- [ ] Description: "One MCP server wrapping free, no-auth public APIs. Tested with M3."
- [ ] Topics: `hacktoberfest`, `mcp`, `mcp-server`, `model-context-protocol`, plus `python`, `ai-agents` and `no-api-key` if you like.
- [ ] Enable Discussions. The issue template config links to it.
- [ ] Enable private vulnerability reporting, which SECURITY.md mentions.
- [ ] Install the [all-contributors bot](https://allcontributors.org/docs/en/bot/installation) on the repository. The README's contributors section tells people to comment `@all-contributors please add @handle for code`, which only works once the bot is there.
- [ ] Branch protection on `main`: require the `Lint and generated files`, `M3 tests (offline replay)` and `Container image builds and starts` checks from `ci.yml`.
- [ ] Confirm CI is green on the first push, and that the CI badge in the README turns green.

## 3. Release setup (maintainer steps from the workflow headers)

PyPI (`release.yml`):

- [ ] Add a trusted publisher for the project on PyPI: owner `sineframe`, repository `keyless-mcp`, workflow `release.yml`, environment `pypi`. For the first release use a pending publisher, since the project does not exist on PyPI yet.
- [ ] In GitHub, create the `pypi` environment. Add required reviewers if you want a manual gate before publishing.
- [ ] After the first image push, make the `ghcr.io/sineframe/keyless-mcp` package public.

Agent lane (`nightly.yml`), optional and costs tokens:

- [ ] Repository secret `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`) for Claude Code.
- [ ] Repository secret `OPENAI_API_KEY` for Codex.
- [ ] Optional repository variables `AGENT_MODEL_CLAUDE` and `AGENT_MODEL_CODEX` to choose the models. A lane whose secret is missing is skipped with a notice.
- [ ] After a nightly run, refresh the pass rates by hand: download the `agent-results-<harness>` artifact, copy the JSON into `docs/results/`, run `make adapters-md`, and commit both. Nothing in CI commits to `main`.

MCP Registry (`release.yml`, last job):

- [ ] The registry verifies ownership of `io.github.sineframe/keyless-mcp` through the marker `<!-- mcp-name: io.github.sineframe/keyless-mcp -->` in the README (shown on PyPI) and the matching label in the Dockerfile. Both are in place. The `verify` job fails before anything is published if the marker or the `readme` field goes missing.
- [ ] Publishing uses GitHub OIDC, so there is no token to store. The `sineframe` organization needs to own the repository.

## 4. First release

- [ ] From `main`: `git tag v0.1.0 && git push origin v0.1.0`. The tag must equal the version in `pyproject.toml` and `server.json`, or the `verify` job fails.
- [ ] Watch the jobs in order: verify, docker, pypi, mcp-registry. PyPI publishes only after the image has built and passed its smoke test.
- [ ] On a clean machine, run `uvx keyless-mcp --list-tools` and `docker run -i --rm ghcr.io/sineframe/keyless-mcp --version`. Nobody has built the Docker image yet, so this is its first real test.
- [ ] Check that the PyPI page shows the README with working links and badges.
- [ ] Put the PyPI version badge back in the README, next to the CI badge: `[![PyPI](https://img.shields.io/pypi/v/keyless-mcp)](https://pypi.org/project/keyless-mcp/)`. It was swapped for a Python version badge because it shows "package or version not found" until the first release.
- [ ] Flip the README quick start to the released form. Until the first release it leads with `uvx --from git+https://github.com/sineframe/keyless-mcp keyless-mcp` in every client config. After PyPI has the package: make `uvx keyless-mcp` (and `"args": ["keyless-mcp"]`) the main command in the Claude Code, Claude Desktop, Cursor, VS Code, Codex and "Choosing toolsets" examples, delete the "not on PyPI yet" paragraph, and turn the "After the first release" section into a short "Run from GitHub or a clone" note. Remove the Docker note about the first release too.
- [ ] Re-read the README parts about toolsets without adapters: the table row for `finance`, `reference` and `fun`, the sentence after it that starts "Until an adapter lands", and the adapter list under "What it is". Update them as adapters land. ADAPTERS.md keeps its own "no adapters yet" line current automatically.
- [ ] Look the server up in the MCP Registry and confirm the listing.

## 5. Issues

- [ ] `DRY_RUN=1 docs/launch/create_issues.sh` shows what it would do and changes nothing.
- [ ] Optionally rehearse on a scratch repository: `docs/launch/create_issues.sh <you>/keyless-mcp-scratch`.
- [ ] Run it for real. It creates the labels and 50 issues: 40 adapter issues labeled `good first issue`, and 10 labeled `help wanted`. Re-running skips titles that exist.
- [ ] Spot-check three issues on GitHub: labels, rendering and links.
- [ ] Pin one or two of the easiest adapter issues (`xkcd`, `pokeapi`, `datamuse`) so newcomers see a gentle start.

## 6. Registries and directories

Each of these has its own form or process, and requirements change, so read the current instructions when you get there.

- [ ] MCP Registry: the release workflow publishes it. Nothing to submit by hand.
- [ ] [Glama](https://glama.ai/mcp/servers)
- [ ] [Smithery](https://smithery.ai)
- [ ] [mcp.so](https://mcp.so)
- [ ] [PulseMCP](https://www.pulsemcp.com)
- [ ] A pull request to [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers). Follow its contribution guide for the entry format and category.

## 7. Announcements

Dates are for 2026. The DEV dates are the weekly Open-Source AI Challenge windows (UTC) as reported on DEV, so check the official challenge pages for the deadline that counts, and read each prompt before you write to it.

- [ ] r/mcp post once the release is live. Lead with what it does, the one-line config and the 40 open adapter issues. Read the subreddit's rules on self-promotion first.
- [ ] Oct 19 (Week 3 starts): DEV challenge entry. Start from [dev-post-draft.md](dev-post-draft.md) and tailor it to the prompt.
- [ ] Oct 26 (Week 4 starts): second DEV challenge entry, with something new to report such as merged adapters, the first outside contributor or updated pass rates.
- [ ] Oct 26 to 28: Show HN. A title like "Show HN: keyless-mcp, an MCP server for public APIs that need no key" works. Be around for the first few hours to answer questions, and read the Show HN guidelines first.

## 8. After launch

- [ ] Answer every issue and pull request within two days. CONTRIBUTING.md promises this.
- [ ] Add contributors with the all-contributors bot as pull requests merge, and name them in the release notes.
- [ ] Watch for the `upstream-drift` issue that the nightly live job opens. It means an upstream API changed or went down.
- [ ] Describe the agent pass rate as what it is: one model, one day, a handful of prompts.
