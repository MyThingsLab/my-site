from __future__ import annotations

import json
from pathlib import Path

import pytest

# Shared fakes come from mythings.testing (plain imports; aliased fixture
# re-export + getfixturevalue wrapper per core docs/CONVENTIONS.md).
from mythings.testing import FakeGh, GitRepo, ScriptedEngine, make_git_repo
from mythings.testing import clean_git_env as _shared_clean_git_env  # noqa: F401

__all__ = ["ScriptedEngine"]


@pytest.fixture(autouse=True)
def _clean_git_env(request: pytest.FixtureRequest) -> None:
    # Real git worktrees in every test; hook-launched pytest (pre-commit)
    # must not leak GIT_* into them.
    request.getfixturevalue("_shared_clean_git_env")


def fake_gh(
    *,
    number: int = 5,
    title: str = "Add a note on Kernel Methods",
    body: str = "Write a note about kernel methods for SVMs.",
    labels: list[str] | None = None,
    existing_pr: dict | None = None,
) -> FakeGh:
    issue = {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": lbl} for lbl in (labels or [])],
    }
    return FakeGh(
        {
            ("issue", "view"): json.dumps(issue),
            ("pr", "list"): json.dumps([existing_pr] if existing_pr else []),
            ("pr", "create"): "https://github.com/owner/site/pull/7\n",
            ("issue", "comment"): "https://github.com/owner/site/issues/5#issuecomment-1\n",
        }
    )


_NAV = """main:
  - title: "About Me"
    url: /about/

  - title: "Projects"
    url: /projects/

  - title: "Notes"
    url: /notes/
"""

_EXISTING_NOTE = """---
collection: notes
title: "Friedman Test"
excerpt: "A statistical comparison of classifiers"
tags:
  - Supervised Learning
---

# A Statistical Comparison of Classifiers
Existing note body.
"""


def make_site(tmp_path: Path) -> Path:
    repo = make_git_repo(
        tmp_path,
        files={
            "README.md": "# site\n",
            "_data/navigation.yml": _NAV,
            "_notes/supervised-learning/friedman-test.md": _EXISTING_NOTE,
        },
    ).path
    # Present in the original fixture's worktree, empty so never committed.
    (repo / "_pages").mkdir()
    return repo


def branch_file(repo: Path, branch: str, path: str) -> str:
    return GitRepo(path=repo, origin=repo.parent / "origin.git").read_committed(branch, path)
