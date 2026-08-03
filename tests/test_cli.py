from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import fake_gh, make_site
from mysite import cli


def test_cli_draft_noop_degrades_and_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_site(tmp_path)

    # Patch the `gh` boundary at the CLI's SiteKeeper construction.
    fake = fake_gh()
    real_make = cli._make

    def _make(args):  # noqa: ANN001
        k = real_make(args)
        k.runner = fake
        k.github._run = fake
        return k

    monkeypatch.setattr(cli, "_make", _make)

    code = cli.main(
        [
            "draft",
            "--issue",
            "5",
            "--repo",
            "owner/site",
            "--repo-root",
            str(repo),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "success:" in out


def test_cli_drain_drafts_every_open_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_site(tmp_path)

    _issues = {
        11: {"number": 11, "title": "Add a note on Boolean Logic", "body": "", "labels": []},
        12: {"number": 12, "title": "Add a note on Fuzzy Logic", "body": "", "labels": []},
    }

    fake = fake_gh()
    fake.responses[("issue", "list")] = json.dumps(
        [{**obj, "url": f"https://github.com/owner/site/issues/{n}"} for n, obj in _issues.items()]
    )
    # Two draft() calls in one drain, each for a different real issue number --
    # the view response must vary by argv, not return the same canned issue twice.
    fake.responses[("issue", "view")] = lambda argv: json.dumps(_issues[int(argv[2])])
    real_make = cli._make

    def _make(args):  # noqa: ANN001
        k = real_make(args)
        k.runner = fake
        k.github._run = fake
        return k

    monkeypatch.setattr(cli, "_make", _make)

    code = cli.main(
        [
            "drain",
            "--repo",
            "owner/site",
            "--repo-root",
            str(repo),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "#11:" in out
    assert "#12:" in out


def test_cli_drain_no_open_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_site(tmp_path)

    fake = fake_gh()
    fake.responses[("issue", "list")] = json.dumps([])
    real_make = cli._make

    def _make(args):  # noqa: ANN001
        k = real_make(args)
        k.runner = fake
        k.github._run = fake
        return k

    monkeypatch.setattr(cli, "_make", _make)

    code = cli.main(
        [
            "drain",
            "--repo",
            "owner/site",
            "--repo-root",
            str(repo),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "no open" in out


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_draft_requires_issue_flag() -> None:
    with pytest.raises(SystemExit):
        cli.main(["draft"])
