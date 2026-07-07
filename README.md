# my-site

[![CI](https://github.com/MyThingsLab/my-site/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-site/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/MyThingsLab/my-site/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-site)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![MIT](https://img.shields.io/badge/license-MIT-green)

A [MyThingsLab](../mythings-core) `My[X]` tool: drafts Jekyll content for a
personal site from a content-change issue. Given an issue (label `my-site`)
on a Jekyll repo — default `lorenzoliuzzo/lorenzoliuzzo.github.io` — it infers
the requested `kind` (project / note / page), gathers the relevant
`_data/navigation.yml` section plus one existing page of the same kind as a
style anchor, makes **one** Engine call to draft the new page(s) and nav
entries, and opens a PR.

MySite is the fleet's first tool whose target repo lives outside the
MyThingsLab org — every tool's target repo is already configurable at run
time, just not exercised until now. It edits *content* only, never the Ruby
toolchain or theme choice — a `Gemfile`/`_config.yml` change stays a human,
out-of-band step.

## Usage

```bash
# Draft content for issue #12 on the default site repo, open a PR.
mysite draft --issue 12 --engine claude-cli

# Point at a different repo / local checkout, skip opening a PR:
mysite draft --issue 12 --repo owner/site --repo-root ~/site --no-pr
```

Each invocation makes **at most one** Engine call. If the requested slug
already exists, the run skips before ever calling the Engine. Against the
default `--engine noop` (zero tokens), the draft degrades to a minimal stub
page — front matter inferred from `kind` plus the issue body verbatim — an
honest degrade, never fabricated prose.

## Structural fence

The Engine may only write files under `_pages/`, `_notes/`, or
`assets/<kind>/`. This is enforced by the writer, not trusted from the
Engine's reply: any file path outside the allowlist is dropped and the run
still succeeds rather than failing outright.

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../mythings-core -e ../my-guard -e ".[dev]"
pytest
```

See [`CLAUDE.md`](CLAUDE.md) for the tool's seams and [`HARNESS.md`](HARNESS.md)
for the inherited build rules.

## License

MIT — see [`LICENSE`](LICENSE).
