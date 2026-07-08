# my-site — agent instructions

You are developing **my-site**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** given a content or design-change issue (label `my-site`) on a
  configured Jekyll site repo — default `lorenzoliuzzo/lorenzoliuzzo.github.io`
  — drafts the page(s), front matter, and navigation entries needed, matching
  the site's existing structure and theme conventions, and opens a PR.
- **The single Engine call:** one per run — "given this content request and
  the site's existing structure, draft the Jekyll content." Input: the issue
  title + body, the relevant `_data/navigation.yml` section, and one existing
  page of the same `kind` as a style anchor. Output: `{"files": {path:
  content}, "nav_patch": [{"section", "entry"}]}`. Against `NoopEngine`,
  degrades to a single minimal stub page (front matter inferred from `kind`,
  issue body verbatim) plus one nav entry — honest degrade, never fabricated
  prose. Skipped entirely (no Engine call) if the requested slug already
  exists.
- **Invariants / rules:** the Engine may only write under `_pages/`,
  `_notes/`, or `assets/<kind>/` — a structural fence enforced by the writer,
  not an Engine-trusted claim; any file outside the allowlist is dropped and
  the run still succeeds. Never touches `_config.yml`, `_includes/`,
  `assets/css/`, or any Ruby file. One side effect, a committed PR via
  `Workspace`, routed through `Policy` (`Guard` default). **Never merges** —
  the site's own `jekyll.yml` workflow builds/deploys once a human merges.
  Ledger `kind=site_change`, `outcome=success|skipped`.
- **Backlog label:** `my-site`
