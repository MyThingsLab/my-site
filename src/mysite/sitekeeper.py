from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from myguard import Guard
from mythings.engine import Engine, EngineRequest, NoopEngine
from mythings.github import GitHub, GitHubError, PullRequest, Runner, _gh, _pr_number
from mythings.isolation import Workspace, in_github_actions
from mythings.ledger import Ledger
from mythings.policy import Action, Decision, Policy

from mysite.jekyll import find_nav_section, patch_nav_section, render_front_matter

LABEL = "my-site"

_KIND_DIRS = {"project": "_projects", "note": "_notes", "page": "_pages"}
_KIND_KEYWORDS = {
    "project": {"project", "projects"},
    "note": {"note", "notes"},
    "page": {"page", "pages"},
}

_SYSTEM = (
    "You draft Jekyll content for a personal site, matching its existing "
    "structure and style. You may only write files under _pages/, _notes/, or "
    "assets/<kind>/. Never touch _config.yml, _includes/, assets/css/, or any "
    "Ruby file. Reply with a single JSON object and nothing else."
)

# Notes are exam study material read back under time pressure, not general content
# pages -- held to a higher bar than the shared _SYSTEM prompt above.
_NOTE_SYSTEM = _SYSTEM + (
    "\n\nThis request is for a study note. Hold to a higher bar:\n"
    "- Use inline LaTeX as $...$ and display equations as $$...$$.\n"
    '- Start the body with a single "# Title" heading matching the note\'s title, '
    'then "##" for sections.\n'
    "- If source material was given in the request body, draft primarily from it: "
    "organize and clarify, never contradict it or add claims it does not support.\n"
    "- If no source material was given, write a correct, exam-ready explanation from "
    "your own knowledge, but where a claim is genuinely contested or you are not "
    "confident, say so in the text rather than stating it flatly.\n"
    "- Do not invent figures, tables, or {% include %} tags -- there is no source "
    "asset to point them at."
)


class PolicyDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class Result:
    outcome: str  # success | skipped | failure
    slug: str | None
    kind: str | None
    pr: int | None
    detail: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Issue:
    number: int
    title: str
    body: str
    labels: list[str]


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    word: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def _slug(text: str) -> str:
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")[:60] or "page"


def _extract_path(body: str, directory: str) -> str | None:
    # An enqueuer that already knows the site's folder convention (e.g. tag-nested
    # _notes/<topic>/<subtopic>/) can pin the exact write target with a "Path:" line
    # in the issue body, instead of falling back to a flat slug-of-the-title.
    for line in body.splitlines():
        line = line.strip()
        if line.lower().startswith("path:"):
            value = line.split(":", 1)[1].strip()
            value = value.removeprefix(f"{directory}/")
            if not value or ".." in value.split("/"):
                return None
            return value if value.endswith(".md") else f"{value}.md"
    return None


def _infer_kind(issue: _Issue) -> str:
    for label in issue.labels:
        if label in _KIND_DIRS:
            return label
    tokens = set(_tokenize(issue.title) + _tokenize(issue.body))
    for kind, keywords in _KIND_KEYWORDS.items():
        if tokens & keywords:
            return kind
    return "page"


def _is_allowed_path(path: str) -> bool:
    return path.startswith(("_pages/", "_notes/", "assets/"))


class SiteKeeper:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        repo: str | None = None,
        ledger: Ledger,
        base: str = "main",
        engine: Engine | None = None,
        policy: Policy | None = None,
        runner: Runner = _gh,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repo = repo
        self.ledger = ledger
        self.base = base
        self.engine: Engine = engine or NoopEngine()
        self.policy: Policy = policy or Guard()
        self.runner = runner
        self.github = GitHub(repo, runner=runner)

    # ---- draft --------------------------------------------------------

    def draft(self, issue: int, *, no_pr: bool = False) -> Result:
        try:
            topic = self._fetch_issue(issue)
        except GitHubError as err:
            return self._fail(None, None, f"could not read issue #{issue}: {err}")

        kind = _infer_kind(topic)
        directory = _KIND_DIRS[kind]
        path_directive = _extract_path(topic.body, directory)
        slug = Path(path_directive).stem if path_directive else _slug(topic.title)
        rel_path = f"{directory}/{path_directive}" if path_directive else f"{directory}/{slug}.md"

        if (self.repo_root / rel_path).exists():
            detail = f"a page already exists at {rel_path}"
            self._comment(
                issue,
                f"_{detail} — close this issue or file a follow-up to edit it instead._",
            )
            self._record("skipped", slug, kind, None, detail, ())
            return self._skip(slug, kind, detail)

        nav_text = self._read_nav()
        anchor_path, anchor_text = self._anchor(directory)

        reply = self.engine.run(
            EngineRequest(
                system=_NOTE_SYSTEM if kind == "note" else _SYSTEM,
                prompt=self._prompt(topic, kind, nav_text, anchor_path, anchor_text, rel_path),
                context={"issue": issue, "kind": kind, "anchor_path": anchor_path or ""},
            )
        )
        files, nav_patch = self._parse_reply(reply.text, topic, kind, slug, rel_path)

        pr = None
        if not no_pr and files:
            try:
                pr = self._open_pr(topic, slug, kind, files, nav_patch)
            except PolicyDenied as denied:
                return self._fail(slug, kind, str(denied))

        detail = f"draft for {slug} ({kind})"
        self._record(
            "success",
            slug,
            kind,
            pr.number if pr else None,
            detail,
            tuple(sorted(files)),
        )
        return Result(
            "success", slug, kind, pr.number if pr else None, detail, tuple(sorted(files))
        )

    # ---- deterministic pre-work ---------------------------------------

    def _fetch_issue(self, number: int) -> _Issue:
        argv = ["issue", "view", str(number), "--json", "number,title,body,labels"]
        if self.repo:
            argv += ["--repo", self.repo]
        obj = json.loads(self.runner(argv))
        labels = [lbl["name"] if isinstance(lbl, dict) else lbl for lbl in obj.get("labels", [])]
        return _Issue(
            number=obj["number"], title=obj["title"], body=obj.get("body") or "", labels=labels
        )

    def _read_nav(self) -> str:
        nav_path = self.repo_root / "_data" / "navigation.yml"
        return nav_path.read_text(encoding="utf-8") if nav_path.exists() else ""

    def _anchor(self, directory: str) -> tuple[str | None, str]:
        kind_dir = self.repo_root / directory
        if not kind_dir.is_dir():
            return None, ""
        for path in sorted(kind_dir.rglob("*.md")):
            return str(path.relative_to(self.repo_root)), path.read_text(encoding="utf-8")
        return None, ""

    def _prompt(
        self,
        topic: _Issue,
        kind: str,
        nav_text: str,
        anchor_path: str | None,
        anchor_text: str,
        rel_path: str,
    ) -> str:
        section = _guess_nav_section(nav_text, kind)
        nav_block = "\n".join(find_nav_section(nav_text, section)) if section else ""
        lines = [
            f"Issue #{topic.number}: {topic.title}",
            f"Kind: {kind}",
            f"\nRequest body:\n{topic.body.strip()}",
            f'\nWrite the file at exactly this path: "{rel_path}" — use it verbatim as the '
            "key in the files object.",
        ]
        if anchor_path:
            lines.append(f"\nStyle anchor ({anchor_path}):\n{anchor_text}")
        if nav_block:
            lines.append(f"\nExisting nav section ({section}):\n{nav_block}")
        lines.append(
            "\nReturn JSON with keys: "
            '"files" (object mapping relative path -> full file content, front '
            "matter included; only under _pages/, _notes/, or assets/<kind>/), "
            '"nav_patch" (array of {"section","entry":{"title","url"}}).'
        )
        return "\n".join(lines)

    # ---- engine reply parsing / structural fence -----------------------

    def _parse_reply(
        self, text: str, topic: _Issue, kind: str, slug: str, rel_path: str
    ) -> tuple[dict[str, str], list[dict[str, object]]]:
        obj = _parse_json_object(text)
        if obj is None:
            return self._raw_stub(topic, kind, slug, rel_path)

        raw_files = obj.get("files")
        files: dict[str, str] = {}
        if isinstance(raw_files, dict):
            for path, content in raw_files.items():
                path = str(path)
                if not _is_allowed_path(path):  # structural fence: drop, don't fail
                    continue
                files[path] = str(content)

        nav_patch: list[dict[str, object]] = []
        for item in obj.get("nav_patch") or []:
            if not isinstance(item, dict):
                continue
            entry = item.get("entry")
            section = item.get("section")
            if isinstance(section, str) and isinstance(entry, dict):
                nav_patch.append({"section": section, "entry": entry})

        if not files:
            return self._raw_stub(topic, kind, slug, rel_path)
        return files, nav_patch

    def _raw_stub(
        self, topic: _Issue, kind: str, slug: str, rel_path: str
    ) -> tuple[dict[str, str], list[dict[str, object]]]:
        # Honest degrade against NoopEngine (or an unparsable reply): a minimal
        # stub page, not fabricated prose.
        directory = _KIND_DIRS[kind]
        fields = {"title": topic.title, "layout": "single" if kind == "page" else kind}
        permalink = f"/{directory.lstrip('_')}/{slug}/"
        fields["permalink"] = permalink
        body = topic.body.strip() or f"Draft placeholder for {topic.title}."
        content = render_front_matter(fields, body)
        nav_patch = [{"section": "main", "entry": {"title": topic.title, "url": permalink}}]
        return {rel_path: content}, nav_patch

    # ---- github / git helpers ------------------------------------------

    def _open_pr(
        self,
        topic: _Issue,
        slug: str,
        kind: str,
        files: dict[str, str],
        nav_patch: list[dict[str, object]],
    ) -> PullRequest:
        branch = f"{LABEL}/{topic.number}"
        existing = self._existing_pr(branch)
        with Workspace(self.repo_root, self.base) as tree:
            self._git(tree, ["checkout", "-B", branch])
            for path, content in files.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                self._git(tree, ["add", path])

            nav_path = tree / "_data" / "navigation.yml"
            if nav_patch and nav_path.exists():
                nav_text = nav_path.read_text(encoding="utf-8")
                for patch in nav_patch:
                    entry = {str(k): str(v) for k, v in patch["entry"].items()}  # type: ignore[union-attr]
                    nav_text = patch_nav_section(nav_text, str(patch["section"]), entry)
                nav_path.write_text(nav_text, encoding="utf-8")
                self._git(tree, ["add", "_data/navigation.yml"])

            self._git(tree, ["commit", "-m", f"site: draft {slug} ({kind})"])
            if existing is None:
                self._git(tree, ["push", "-u", "origin", branch])
            else:
                self._git(tree, ["push", "origin", branch])
        if existing is not None:
            return existing
        self._guard(f"gh pr create --head {branch} --base {self.base}")
        return self.github.open_pr(
            title=f"site: {topic.title}",
            body=f"Drafted `{slug}` ({kind}) content.\n\nCloses #{topic.number}.",
            base=self.base,
            head=branch,
        )

    def _existing_pr(self, branch: str) -> PullRequest | None:
        argv = ["pr", "list", "--head", branch, "--state", "open", "--json", "number,url"]
        if self.repo:
            argv += ["--repo", self.repo]
        rows = json.loads(self.runner(argv))
        if not rows:
            return None
        row = rows[0]
        return PullRequest(number=row.get("number") or _pr_number(row["url"]), url=row["url"])

    def _comment(self, issue: int, body: str) -> str | None:
        if self.repo is None:
            return None
        argv = ["issue", "comment", str(issue), "--repo", self.repo, "--body", body]
        action = Action(kind="bash", payload={"command": f"gh issue comment {issue}"})
        if self.policy.evaluate(action).under(unattended=in_github_actions()) is not Decision.ALLOW:
            return None
        return self.runner(argv).strip() or None

    def _git(self, tree: Path, argv: list[str]) -> None:
        self._guard("git " + " ".join(argv))
        proc = subprocess.run(["git", "-C", str(tree), *argv], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(argv)} failed: {proc.stderr.strip()}")

    def _guard(self, command: str) -> None:
        action = Action(kind="fs-write", payload={"command": command})
        result = self.policy.evaluate(action)
        if result.under(unattended=in_github_actions()) is not Decision.ALLOW:
            raise PolicyDenied(f"policy blocked: {command} ({result.reason or result.decision})")

    # ---- ledger / results ----------------------------------------------

    def _record(
        self,
        outcome: str,
        slug: str | None,
        kind: str | None,
        pr: int | None,
        detail: str,
        files: tuple[str, ...],
    ) -> None:
        self.ledger.record(
            tool="mysite",
            kind="site_change",
            outcome=outcome,
            detail=detail,
            slug=slug,
            page_kind=kind,
            repo=self.repo,
            files_written=list(files),
            nav_updated=bool(files),
            pr=pr,
        )

    def _skip(self, slug: str | None, kind: str | None, detail: str) -> Result:
        return Result("skipped", slug, kind, None, detail)

    def _fail(self, slug: str | None, kind: str | None, detail: str) -> Result:
        self.ledger.record(
            tool="mysite",
            kind="site_change",
            outcome="failure",
            detail=detail,
            slug=slug,
            page_kind=kind,
        )
        return Result("failure", slug, kind, None, detail)


def _guess_nav_section(nav_text: str, kind: str) -> str | None:
    keywords = _KIND_KEYWORDS.get(kind, set())
    for line in nav_text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            section = line.rstrip()[:-1]
            if set(_tokenize(section)) & keywords:
                return section
    return "main" if "main:" in nav_text else None


def _parse_json_object(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines).strip()
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None
