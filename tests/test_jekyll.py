from __future__ import annotations

from mysite.jekyll import (
    patch_nav_section,
    render_front_matter,
    split_front_matter,
)


def test_split_and_render_front_matter_roundtrip() -> None:
    text = '---\ntitle: "Hello"\nlayout: single\n---\n\nBody text here.\n'
    fields, body = split_front_matter(text)

    assert fields == {"title": "Hello", "layout": "single"}
    assert body.strip() == "Body text here."

    rendered = render_front_matter(fields, body)
    fields2, body2 = split_front_matter(rendered)
    assert fields2 == fields
    assert body2.strip() == body.strip()


def test_split_front_matter_missing_fence_returns_whole_body() -> None:
    text = "just markdown, no front matter\n"
    fields, body = split_front_matter(text)

    assert fields == {}
    assert body == text


def test_patch_nav_section_inserts_entry_under_matching_section() -> None:
    nav = 'main:\n  - title: "About Me"\n    url: /about/\n\n  - title: "Notes"\n    url: /notes/\n'

    patched = patch_nav_section(nav, "main", {"title": "New Note", "url": "/notes/new-note/"})

    assert '- title: "New Note"' in patched
    assert "url: /notes/new-note/" in patched
    # Original entries are preserved.
    assert '- title: "About Me"' in patched
    assert '- title: "Notes"' in patched


def test_patch_nav_section_unknown_section_appends_new_block() -> None:
    nav = 'main:\n  - title: "About Me"\n    url: /about/\n'

    patched = patch_nav_section(nav, "sidebar", {"title": "Extra", "url": "/extra/"})

    assert "sidebar:" in patched
    assert '- title: "Extra"' in patched
