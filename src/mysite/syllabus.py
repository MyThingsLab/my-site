from __future__ import annotations

import json
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mythings.http import http_get

# Bulk intake: turn a syllabus (a list of topics) into one my-site-labeled issue
# per topic via my-server's enqueue API, so the rest of the pipeline (draft/drain)
# never has to know about syllabi at all -- it only ever sees issues.

# A Poster takes (url, data, headers) and returns the raw response body. The
# default shells out to urllib; tests inject a fake -- same seam pattern as
# mythings.fetch.Getter and mythings.github.Runner.
Poster = Callable[[str, bytes, dict[str, str]], bytes]


class EnqueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class Topic:
    path: str  # relative to _notes/, e.g. "physics/quantum-mechanics/spin.md"
    title: str
    tags: tuple[str, ...]
    source: str | None = None


@dataclass(frozen=True)
class Enqueued:
    topic: Topic
    issue: int
    url: str


def load_topics(path: Path) -> list[Topic]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("syllabus must be a JSON array of topics")

    topics = []
    for entry in raw:
        if (
            not isinstance(entry, dict)
            or not entry.get("path")
            or not entry.get("title")
            or not entry.get("tags")
        ):
            raise ValueError(f"each topic needs path, title, and tags: {entry!r}")
        topics.append(
            Topic(
                path=str(entry["path"]),
                title=str(entry["title"]),
                tags=tuple(str(t) for t in entry["tags"]),
                source=str(entry["source"]) if entry.get("source") else None,
            )
        )
    return topics


def build_issue(topic: Topic) -> tuple[str, str]:
    # "note:" in the title satisfies _infer_kind's keyword match even when the
    # backlog issue carries no explicit "note" label.
    title = f"note: {topic.title}"
    lines = [
        f"Path: {topic.path}",
        f"Tags: {', '.join(topic.tags)}",
        "Source material:",
        topic.source.strip() if topic.source else "none — draft from general knowledge.",
    ]
    return title, "\n".join(lines)


def default_post(url: str, data: bytes, headers: dict[str, str]) -> bytes:
    try:
        return http_get(url, data=data, headers=headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise EnqueueError(f"enqueue failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise EnqueueError(f"could not reach {url}: {exc.reason}") from exc


def enqueue_syllabus(
    topics: list[Topic],
    *,
    server: str,
    token: str,
    repo: str,
    post: Poster = default_post,
) -> list[Enqueued]:
    url = f"{server.rstrip('/')}/tools/my-site/issues"
    headers = {"content-type": "application/json", "authorization": f"Bearer {token}"}

    results = []
    for topic in topics:
        title, body = build_issue(topic)
        data = json.dumps({"repo": repo, "title": title, "body": body}).encode()
        raw = post(url, data, headers)
        obj = json.loads(raw)
        results.append(Enqueued(topic=topic, issue=obj["issue"], url=obj["url"]))
    return results
