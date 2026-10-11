## What this changes

<!-- One or two sentences. For a new adapter, name the API and its tools. -->

Closes #

## Checklist

- [ ] I linked the issue this pull request closes, and I had claimed it
- [ ] `make test` passes on my machine
- [ ] `make benchmark` passes: benchmark scores did not go down (if I added an adapter, I ran `make benchmark-baseline` and committed `benchmarks/baseline.json`; if a drop is intended, I explained it below)
- [ ] Cassettes are recorded and committed (`make record ADAPTER=<name>`), and I read them before committing
- [ ] `make adapters-md` was run and `ADAPTERS.md` is part of this pull request
- [ ] `make lint` passes
- [ ] Every tool and parameter has a description, and there is a test for an error path
- [ ] There are no API keys, tokens or personal data in the code, cassettes or tests
- [ ] I read the API's terms of use and the API works without a key

## Notes for the reviewer

<!-- Rate limits, quirks, anything you were unsure about. -->
