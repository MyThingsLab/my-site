from __future__ import annotations

import json
from pathlib import Path

from mythings.ledger import Ledger

from conftest import FakeRunner, ScriptedEngine, SpyEngine, branch_file, make_site
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


def _keeper(repo: Path, tmp_path: Path, fake: FakeRunner, **kw) -> tuple[SiteKeeper, Ledger]:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    k = SiteKeeper(repo_root=repo, repo="owner/site", ledger=ledger, runner=fake, **kw)
    return k, ledger


def test_draft_happy_path_opens_pr_and_records_ledger(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = FakeRunner()
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

    fake = FakeRunner(title="Friedman Test", body="revisit this note")
    spy = SpyEngine()
    k, ledger = _keeper(repo, tmp_path, fake, engine=spy)

    result = k.draft(issue=5)

    assert result.outcome == "skipped"
    assert spy.calls == []  # Engine never called on slug collision
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)  # no PR
    assert any(c[:2] == ["issue", "comment"] for c in fake.calls)
    assert list(ledger)[0].outcome == "skipped"


def test_draft_drops_files_outside_allowlist_but_still_succeeds(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = FakeRunner()
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
    fake = FakeRunner()
    k, _ = _keeper(repo, tmp_path, fake, engine=ScriptedEngine(_DRAFT_REPLY))

    result = k.draft(issue=5, no_pr=True)

    assert result.outcome == "success"
    assert result.pr is None
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)


def test_draft_against_noop_engine_degrades_to_stub_page(tmp_path: Path) -> None:
    repo = make_site(tmp_path)
    fake = FakeRunner(title="Add a project page for RayTracer", body="A ray tracing engine.")
    k, ledger = _keeper(repo, tmp_path, fake)  # default NoopEngine

    result = k.draft(issue=5)

    assert result.outcome == "success"
    assert result.kind == "project"
    assert result.files == ("_projects/add-a-project-page-for-raytracer.md",)

    committed = branch_file(
        repo, "my-site/5", "_projects/add-a-project-page-for-raytracer.md"
    )
    assert "Add a project page for RayTracer" in committed
    assert "A ray tracing engine." in committed
    assert list(ledger)[0].outcome == "success"
