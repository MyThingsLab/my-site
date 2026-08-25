from __future__ import annotations

import argparse
import os
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine, NoopEngine
from mythings.ledger import Ledger

from mysite.sitekeeper import LABEL, Result, SiteKeeper
from mysite.syllabus import EnqueueError, enqueue_syllabus, load_topics


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


def _cmd_draft(args: argparse.Namespace) -> int:
    keeper = _make(args)
    result = keeper.draft(args.issue, no_pr=args.no_pr)
    print(_render(result))
    return 1 if result.outcome == "failure" else 0


def _cmd_drain(args: argparse.Namespace) -> int:
    # The unattended path: draft every open my-site issue in one pass instead of
    # one at a time, for a daily/timer-driven run. draft() already skips any
    # issue whose target file exists, so re-running this on a schedule is safe.
    keeper = _make(args)
    issues = keeper.github.list_issues(labels=[LABEL], limit=args.limit)
    if not issues:
        print(f"no open {LABEL} issues")
        return 0

    exit_code = 0
    for issue in issues:
        result = keeper.draft(issue.number, no_pr=args.no_pr)
        print(f"#{issue.number}: {_render(result)}")
        if result.outcome == "failure":
            exit_code = 1
    return exit_code


def _cmd_enqueue_syllabus(args: argparse.Namespace) -> int:
    token = args.token or os.environ.get("MYSERVER_TOKEN")
    if not token:
        print("error: --token or $MYSERVER_TOKEN is required to enqueue")
        return 1

    topics = load_topics(args.syllabus)
    try:
        results = enqueue_syllabus(topics, server=args.server, token=token, repo=args.repo)
    except EnqueueError as err:
        print(f"error: {err}")
        return 1

    for result in results:
        print(f"#{result.issue}: {result.topic.path} — {result.url}")
    print(f"\n{len(results)} topic(s) enqueued.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mysite",
        description="Draft Jekyll content (page, front matter, nav entry) from a content issue.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    draft = sub.add_parser("draft", help="draft content for one issue")
    _add_common(draft)
    draft.add_argument("--issue", type=int, required=True, help="the content-change issue")

    drain = sub.add_parser("drain", help=f"draft every open {LABEL} issue")
    _add_common(drain)
    drain.add_argument("--limit", type=int, default=100, help="max open issues to fetch")

    enqueue = sub.add_parser(
        "enqueue-syllabus", help="file one my-site issue per topic in a syllabus"
    )
    enqueue.add_argument("syllabus", type=Path, help="JSON array of {path, title, tags, source}")
    enqueue.add_argument(
        "--repo",
        default="lorenzoliuzzo/lorenzoliuzzo.github.io",
        help="GitHub slug owner/name (default: lorenzoliuzzo/lorenzoliuzzo.github.io)",
    )
    enqueue.add_argument("--server", default="http://127.0.0.1:8787", help="my-server base URL")
    enqueue.add_argument(
        "--token", help="my-server enqueue bearer token (default: $MYSERVER_TOKEN)"
    )

    args = parser.parse_args(argv)
    if args.cmd == "draft":
        return _cmd_draft(args)
    if args.cmd == "drain":
        return _cmd_drain(args)
    return _cmd_enqueue_syllabus(args)


if __name__ == "__main__":
    raise SystemExit(main())
