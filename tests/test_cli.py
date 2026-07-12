from __future__ import annotations

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
            "--issue", "5",
            "--repo", "owner/site",
            "--repo-root", str(repo),
            "--ledger", str(tmp_path / "ledger.jsonl"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "success:" in out


def test_cli_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_draft_requires_issue_flag() -> None:
    with pytest.raises(SystemExit):
        cli.main(["draft"])
