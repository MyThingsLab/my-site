from __future__ import annotations

import json
from pathlib import Path

import pytest

from mysite.syllabus import EnqueueError, Topic, build_issue, enqueue_syllabus, load_topics


def _write(tmp_path: Path, obj: object) -> Path:
    path = tmp_path / "syllabus.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_load_topics_parses_valid_entries(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "path": "physics/quantum-mechanics/spin.md",
                "title": "Spin",
                "tags": ["Physics", "Quantum Mechanics"],
                "source": "lecture slides excerpt",
            },
            {"path": "logic/boolean.md", "title": "Boolean Logic", "tags": ["Logic"]},
        ],
    )

    topics = load_topics(path)

    assert topics == [
        Topic(
            path="physics/quantum-mechanics/spin.md",
            title="Spin",
            tags=("Physics", "Quantum Mechanics"),
            source="lecture slides excerpt",
        ),
        Topic(path="logic/boolean.md", title="Boolean Logic", tags=("Logic",), source=None),
    ]


def test_load_topics_rejects_non_array(tmp_path: Path) -> None:
    path = _write(tmp_path, {"not": "a list"})
    with pytest.raises(ValueError, match="JSON array"):
        load_topics(path)


def test_load_topics_rejects_missing_fields(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"path": "x.md", "title": "X"}])  # no tags
    with pytest.raises(ValueError, match="path, title, and tags"):
        load_topics(path)


def test_build_issue_with_source() -> None:
    topic = Topic(path="a/b.md", title="B", tags=("A", "B"), source="excerpt text")
    title, body = build_issue(topic)

    assert title == "note: B"
    assert "Path: a/b.md" in body
    assert "Tags: A, B" in body
    assert "excerpt text" in body


def test_build_issue_without_source() -> None:
    topic = Topic(path="a/b.md", title="B", tags=("A",), source=None)
    _, body = build_issue(topic)

    assert "none — draft from general knowledge." in body


def test_enqueue_syllabus_posts_one_request_per_topic() -> None:
    topics = [
        Topic(path="a.md", title="A", tags=("X",)),
        Topic(path="b.md", title="B", tags=("X",)),
    ]
    calls = []

    def fake_post(url: str, data: bytes, headers: dict[str, str]) -> bytes:
        calls.append((url, json.loads(data), headers))
        n = len(calls)
        return json.dumps(
            {"tool": "my-site", "repo": "o/r", "issue": n, "url": f"https://x/{n}"}
        ).encode()

    results = enqueue_syllabus(topics, server="http://h:1", token="tok", repo="o/r", post=fake_post)

    assert len(calls) == 2
    assert calls[0][0] == "http://h:1/tools/my-site/issues"
    assert calls[0][2]["authorization"] == "Bearer tok"
    assert calls[0][1] == {"repo": "o/r", "title": "note: A", "body": build_issue(topics[0])[1]}
    assert [r.issue for r in results] == [1, 2]
    assert [r.url for r in results] == ["https://x/1", "https://x/2"]


def test_enqueue_syllabus_propagates_post_failure() -> None:
    def failing_post(url: str, data: bytes, headers: dict[str, str]) -> bytes:
        raise EnqueueError("boom")

    with pytest.raises(EnqueueError):
        enqueue_syllabus(
            [Topic(path="a.md", title="A", tags=("X",))],
            server="http://h:1",
            token="tok",
            repo="o/r",
            post=failing_post,
        )
