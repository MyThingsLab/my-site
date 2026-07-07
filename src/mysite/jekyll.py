from __future__ import annotations

# Hand-rolled front-matter + navigation.yml handling: front matter here is
# always flat key:value pairs, and navigation.yml only needs "find the right
# top-level section and insert an entry" -- both stay well within what a small
# line-based parser can do without pulling in pyyaml (harness default: stay
# dependency-free).

_FENCE = "---"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FENCE)
    except StopIteration:
        return {}, text

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = _unquote(value.strip())

    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return fields, body


def render_front_matter(fields: dict[str, str], body: str) -> str:
    lines = [_FENCE]
    for key, value in fields.items():
        lines.append(f"{key}: {_quote_if_needed(value)}")
    lines.append(_FENCE)
    lines.append("")
    header = "\n".join(lines)
    return f"{header}\n{body.strip()}\n" if body.strip() else f"{header}\n"


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _quote_if_needed(value: str) -> str:
    if not value:
        return '""'
    if any(ch in value for ch in ":#\"'") or value != value.strip():
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _entry_lines(entry: dict[str, str]) -> list[str]:
    title = entry.get("title", "")
    lines = [f'  - title: "{title}"']
    for key, value in entry.items():
        if key == "title":
            continue
        lines.append(f"    {key}: {value}")
    return lines


def find_nav_section(nav_text: str, section: str) -> list[str]:
    lines = nav_text.splitlines()
    header = f"{section}:"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return []
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace():
            end = i
            break
    return lines[start:end]


def patch_nav_section(nav_text: str, section: str, entry: dict[str, str]) -> str:
    lines = nav_text.splitlines()
    header = f"{section}:"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        # Unknown section: append a new top-level block at the end of the file.
        block = [header, *_entry_lines(entry), ""]
        prefix = nav_text if nav_text.endswith("\n") else nav_text + "\n"
        return prefix + "\n".join(block) + "\n"

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace():
            end = i
            break
    # Insert before the trailing blank lines that separate this section from
    # the next, so the new entry lands with the rest of the section's items.
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1

    new_lines = [*lines[:insert_at], "", *_entry_lines(entry), *lines[insert_at:end], *lines[end:]]
    return "\n".join(new_lines) + ("\n" if nav_text.endswith("\n") else "")
