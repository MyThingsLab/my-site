from __future__ import annotations

import argparse
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine, NoopEngine
from mythings.ledger import Ledger

from mysite.sitekeeper import Result, SiteKeeper


def build_engine(name: str, *, model: str | None = None) -> Engine:
    if name == "claude-cli":
        return ClaudeCLIEngine(model=model)
    return NoopEngine()


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default="lorenzoliuzzo/lorenzoliuzzo.github.io",
        help="GitHub slug owner/name (default: lorenzoliuzzo/lorenzoliuzzo.github.io)",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="local git repo")
    parser.add_argument("--base", default="main", help="base branch for the PR")
    parser.add_argument("--ledger", type=Path, default=Path(".mythings/ledger.jsonl"))
    parser.add_argument("--no-pr", action="store_true", help="skip opening the drafted content PR")
    parser.add_argument(
        "--engine",
        choices=("noop", "claude-cli"),
        default="noop",
        help="Engine backend for drafting (default: noop — emits a minimal stub page)",
    )
    parser.add_argument("--engine-model", help="model for --engine claude-cli")


def _render(result: Result) -> str:
    line = f"{result.outcome}: {result.detail}"
    if result.pr is not None:
        line += f" — PR #{result.pr}"
    if result.files:
        line += f" [{', '.join(result.files)}]"
    return line


def _make(args: argparse.Namespace) -> SiteKeeper:
    return SiteKeeper(
        repo_root=args.repo_root,
        repo=args.repo,
        ledger=Ledger(args.ledger),
        base=args.base,
        engine=build_engine(args.engine, model=args.engine_model),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mysite",
        description="Draft Jekyll content (page, front matter, nav entry) from a content issue.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    draft = sub.add_parser("draft", help="draft content for one issue")
    _add_common(draft)
    draft.add_argument("--issue", type=int, required=True, help="the content-change issue")

    args = parser.parse_args(argv)
    keeper = _make(args)

    result = keeper.draft(args.issue, no_pr=args.no_pr)

    print(_render(result))
    return 1 if result.outcome == "failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())
