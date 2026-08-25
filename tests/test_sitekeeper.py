from __future__ import annotations

import json
from pathlib import Path

from mythings.ledger import Ledger

from conftest import ScriptedEngine, branch_file, fake_gh, make_site
from mysite.sitekeeper import SiteKeeper

_DRAFT_REPLY = json.dumps(
    {
        "files": {
            "_notes/kernel-methods.md": (
                '---\ntitle: "Kernel Methods"\ncollection: notes\n---\n\n'
                "# Kernel Methods\nDrafted body about kernel methods.\n"
            )
        },
        "nav_patch": [
            {
                "section": "main",
                "entry": {"title": "Kernel Methods", "url": "/notes/kernel-methods/"},
            }
        ],
    }
)

_FENCED_REPLY = json.dumps(
    {
        "files": {
            "_notes/kernel-methods.md": "---\ntitle: Kernel Methods\n---\n\nDrafted note body.\n",
            "_config.yml": "theme: evil-hijack\n",
            "_includes/head.html": "<script>evil</script>",
        },
        "nav_patch": [
            {
                "section": "main",
                "entry": {"title": "Kernel Methods", "url": "/notes/kernel-methods/"},
            }
        ],
    }
)


def _keeper(repo: Path, tmp_path: Path, fake: fake_gh, **kw) -> tuple[SiteKeeper, Ledger]:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    k = SiteKeeper(repo_root=repo, repo="owner/site", ledger=ledger, runner=fake, **kw)
    return k, ledger


def test_draft_happy_path_opens_pr_and_records_ledger(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh()
    k, ledger = _keeper(repo, tmp_path, fake, engine=ScriptedEngine(_DRAFT_REPLY))

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.pr == 7
    assert result.slug == "add-a-note-on-kernel-methods"
    assert result.files == ("_notes/kernel-methods.md",)
    assert any(c[:2] == ["pr", "create"] for c in fake.calls)

    committed = branch_file(repo, "my-site/5", "_notes/kernel-methods.md")
    assert "Kernel Methods" in committed

    nav = branch_file(repo, "my-site/5", "_data/navigation.yml")
    assert '- title: "Kernel Methods"' in nav
    assert "url: /notes/kernel-methods/" in nav

    entry = list(ledger)[0]
    assert entry.kind == "site_change"
    assert entry.outcome == "success"
    assert entry.data["pr"] == 7
    assert entry.data["files_written"] == ["_notes/kernel-methods.md"]


def test_draft_skips_when_slug_already_exists(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    # The fixture repo already has _notes/supervised-learning/friedman-test.md;
    # request the exact top-level slug that collides.
    (repo / "_notes" / "friedman-test.md").write_text("---\ntitle: X\n---\n\nexisting\n")

    fake = fake_gh(title="Friedman Test", body="revisit this note")
    spy = ScriptedEngine()
    k, ledger = _keeper(repo, tmp_path, fake, engine=spy)

    result = k.draft(issue=5)

    assert result.outcome == "skipped"
    assert spy.calls == []  # Engine never called on slug collision
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)  # no PR
    assert any(c[:2] == ["issue", "comment"] for c in fake.calls)
    assert list(ledger)[0].outcome == "skipped"


def test_draft_drops_files_outside_allowlist_but_still_succeeds(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh()
    k, ledger = _keeper(repo, tmp_path, fake, engine=ScriptedEngine(_FENCED_REPLY))

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.files == ("_notes/kernel-methods.md",)  # over-scoped files dropped

    committed = branch_file(repo, "my-site/5", "_notes/kernel-methods.md")
    assert "Kernel Methods" in committed

    # Neither fenced path was ever pushed to the branch.
    assert branch_file(repo, "my-site/5", "_config.yml") == ""
    assert branch_file(repo, "my-site/5", "_includes/head.html") == ""

    assert list(ledger)[0].data["files_written"] == ["_notes/kernel-methods.md"]


def test_draft_no_pr_skips_pr_creation(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh()
    k, _ = _keeper(repo, tmp_path, fake, engine=ScriptedEngine(_DRAFT_REPLY))

    result = k.draft(issue=5, no_pr=True)

    assert result.outcome == "success"
    assert result.pr is None
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)


def test_draft_honors_path_directive_for_nested_notes(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh(
        title="Spin",
        body="Path: physics/quantum-mechanics/spin.md\nTags: Physics, Quantum Mechanics\n"
        "Source material: none",
        labels=["note"],
    )
    reply = json.dumps(
        {
            "files": {
                "_notes/physics/quantum-mechanics/spin.md": (
                    '---\ntitle: "Spin"\ncollection: notes\ntags:\n  - Physics\n  '
                    "- Quantum Mechanics\n---\n\n# Spin\nDrafted body.\n"
                )
            },
            "nav_patch": [],
        }
    )
    k, ledger = _keeper(repo, tmp_path, fake, engine=ScriptedEngine(reply))

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.files == ("_notes/physics/quantum-mechanics/spin.md",)
    committed = branch_file(repo, "my-site/5", "_notes/physics/quantum-mechanics/spin.md")
    assert "Drafted body." in committed

    # The provenance stamp is line-surgical: it must not disturb the tags list
    # sitting in the same front matter block.
    assert "ai_generated: true" in committed
    assert "tags:\n  - Physics\n  - Quantum Mechanics" in committed


def test_draft_skips_when_nested_path_directive_already_exists(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    nested = repo / "_notes" / "physics" / "quantum-mechanics" / "spin.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("---\ntitle: Spin\n---\n\nexisting\n")

    fake = fake_gh(title="Spin", body="Path: physics/quantum-mechanics/spin.md", labels=["note"])
    spy = ScriptedEngine()
    k, ledger = _keeper(repo, tmp_path, fake, engine=spy)

    result = k.draft(issue=5)

    assert result.outcome == "skipped"
    assert spy.calls == []
    assert list(ledger)[0].outcome == "skipped"


def test_draft_note_kind_uses_note_system_prompt(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh(title="Add a note on Kernel Methods")
    spy = ScriptedEngine(_DRAFT_REPLY)
    k, _ = _keeper(repo, tmp_path, fake, engine=spy)

    k.draft(issue=5)

    assert len(spy.calls) == 1
    assert "study note" in spy.calls[0].system
    assert "$...$" in spy.calls[0].system


def test_draft_project_kind_does_not_use_note_system_prompt(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh(title="Add a project page for RayTracer", body="A ray tracing engine.")
    spy = ScriptedEngine(
        json.dumps(
            {"files": {"_projects/raytracer.md": "---\ntitle: X\n---\n\nbody\n"}},
        )
    )
    k, _ = _keeper(repo, tmp_path, fake, engine=spy)

    k.draft(issue=5)

    assert len(spy.calls) == 1
    assert "study note" not in spy.calls[0].system


def test_draft_against_noop_engine_degrades_to_stub_page(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh(title="Add a project page for RayTracer", body="A ray tracing engine.")
    k, ledger = _keeper(repo, tmp_path, fake)  # default NoopEngine

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.kind == "project"
    assert result.files == ("_projects/add-a-project-page-for-raytracer.md",)

    committed = branch_file(repo, "my-site/5", "_projects/add-a-project-page-for-raytracer.md")
    assert "Add a project page for RayTracer" in committed

    # No `layout` key: "project" is not a layout any theme defines, and a wrong
    # override used to fail silently -- a build warning buried in deprecation
    # noise, exit 0, and a chrome-less page. The target site's own collection
    # defaults set the real layout; the stub must not override it.
    assert "layout:" not in committed
    assert "ai_generated: true" in committed


def test_draft_stub_note_permalink_follows_nested_path_not_a_flat_slug(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = fake_gh(
        title="Spin",
        body="Path: physics/quantum-mechanics/spin.md",
        labels=["note"],
    )
    k, ledger = _keeper(repo, tmp_path, fake)  # default NoopEngine

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.files == ("_notes/physics/quantum-mechanics/spin.md",)

    committed = branch_file(repo, "my-site/5", "_notes/physics/quantum-mechanics/spin.md")
    # A collection publishes at /:collection/:path/ derived from where the file
    # sits, so the stub must not pin a flat permalink -- that would publish the
    # note outside its section (breadcrumbs, nested archive) even though the file
    # itself is correctly nested.
    assert "permalink:" not in committed

    nav = branch_file(repo, "my-site/5", "_data/navigation.yml")
    assert "url: /notes/physics/quantum-mechanics/spin/" in nav


def test_draft_stub_page_kind_still_writes_a_permalink(tmp_path: Path) -> None:
    # _pages has no /:collection/:path/ pattern to fall back on -- unlike notes,
    # library entries, or projects, a page's URL has to come from somewhere.
    repo = make_site(tmp_path)
    fake = fake_gh(title="Colophon", body="About this site.", labels=["page"])
    k, ledger = _keeper(repo, tmp_path, fake)  # default NoopEngine

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.files == ("_pages/colophon.md",)

    committed = branch_file(repo, "my-site/5", "_pages/colophon.md")
    assert "permalink: /pages/colophon/" in committed
    assert "layout:" not in committed
    assert list(ledger)[0].outcome == "success"
