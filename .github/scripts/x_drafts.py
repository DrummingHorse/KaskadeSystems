#!/usr/bin/env python3
"""Open a GitHub issue for each new post in evolution/x-posts.json.

Runs on pushes to main that change that file. It compares the file at the
previous commit with the new one. Every post id that wasn't there before
becomes an issue assigned to the repository owner, so GitHub notifies them.
The issue holds a one-tap link that opens X with the post filled in.

Nothing is posted to X from here. The workflow has no X credentials, and its
only token is the repository's own, limited to reading code and opening issues.

Check locally without touching GitHub:
    DRY_RUN=1 python3 .github/scripts/x_drafts.py <before-sha> <after-sha>
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse

POSTS_PATH = "evolution/x-posts.json"
LABEL = "x-post"
X_LIMIT = 280      # characters per post on X
LINK_WEIGHT = 23   # X counts every link as 23 characters
INTENT = "https://x.com/intent/tweet"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")

# Code point ranges X counts as one character; everything else counts as two.
# Emoji sequences may be overcounted, which errs on the safe side.
LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def weighted_length(text: str) -> int:
    total = 0
    for char in text:
        point = ord(char)
        total += 1 if any(lo <= point <= hi for lo, hi in LIGHT_RANGES) else 2
    return total


def git_show(rev: str) -> str | None:
    """The posts file at a commit, or None when it isn't there."""
    result = subprocess.run(
        ["git", "show", f"{rev}:{POSTS_PATH}"],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def load_posts(rev: str) -> list[dict]:
    if not rev or set(rev) == {"0"}:
        return []
    raw = git_show(rev)
    if raw is None:
        return []
    return json.loads(raw).get("posts", [])


def intent_link(text: str, link: str) -> str:
    params = {"text": text}
    if link:
        params["url"] = link
    return INTENT + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def render(post: dict, after: str) -> str:
    text = str(post["text"]).strip()
    link = str(post.get("link", "")).strip()
    used = weighted_length(text) + (1 + LINK_WEIGHT if link else 0)
    quoted = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())

    lines = [
        f"**Draft post for X** (about {used} of {X_LIMIT} characters, link included)",
        "",
        quoted,
        "",
    ]
    if link:
        lines += [f"Link: {link}", ""]
    if used > X_LIMIT:
        lines += [
            f"**Over the limit by about {used - X_LIMIT} characters.** "
            "Shorten it on X before posting, or fix it in a new pull request.",
            "",
        ]
    lines += [
        f"### [Post on X]({intent_link(text, link)})",
        "",
        "Opens X with the post filled in. You can edit it there, and nothing is "
        "posted until you press Post.",
        "",
        "After posting, close this issue. Paste the post's link in a comment if "
        "you want a record of it.",
        "",
        "---",
        f"Drafted by {post.get('by') or 'an unnamed contributor'}, "
        f"entry `{post['id']}`, merged in {after[:7]}.",
    ]
    return "\n".join(lines)


def gh(*args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["gh", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def ensure_label() -> None:
    gh("label", "create", LABEL, "--color", "FBBF24",
       "--description", "Draft post for X from the Evolution log", "--force")


def existing_titles() -> set[str]:
    out = gh("issue", "list", "--label", LABEL, "--state", "all",
             "--limit", "1000", "--json", "title", "--jq", ".[].title")
    return set(out.splitlines())


def open_issue(title: str, body: str) -> None:
    args = ["issue", "create", "--title", title, "--body-file", "-", "--label", LABEL]
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    try:
        print(gh(*args, *(["--assignee", owner] if owner else []), input_text=body).strip())
    except subprocess.CalledProcessError:
        # Assignment can fail on unusual setups; the issue still matters more.
        print(gh(*args, input_text=body).strip())


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: x_drafts.py <before-sha> <after-sha>", file=sys.stderr)
        return 2
    before, after = sys.argv[1], sys.argv[2]
    dry_run = os.environ.get("DRY_RUN") == "1"

    try:
        old_ids = {str(p.get("id")) for p in load_posts(before)}
    except (json.JSONDecodeError, AttributeError):
        print("Previous version unreadable; relying on existing issues to avoid repeats.")
        old_ids = set()

    raw = git_show(after)
    if raw is None:
        print(f"{POSTS_PATH} not found at {after[:7]}; nothing to do.")
        return 0
    posts = json.loads(raw).get("posts", [])

    fresh: list[dict] = []
    seen: set[str] = set()
    for post in posts:
        pid = str(post.get("id", ""))
        if not ID_PATTERN.match(pid):
            print(f"::warning::Skipped a post with a missing or malformed id: {pid!r}")
            continue
        if not str(post.get("text", "")).strip():
            print(f"::warning::Skipped {pid}: its text is empty")
            continue
        if pid in seen:
            print(f"::warning::Skipped a second post with the id {pid}")
            continue
        seen.add(pid)
        if pid not in old_ids:
            fresh.append(post)

    if not fresh:
        print("No new posts.")
        return 0

    titles: set[str] = set()
    if not dry_run:
        ensure_label()
        titles = existing_titles()

    for post in fresh:
        title = f"Post to X: {post['id']}"
        if title in titles:
            print(f"Already has an issue: {title}")
            continue
        body = render(post, after)
        if dry_run:
            print("=" * 72)
            print(title)
            print("-" * 72)
            print(body)
        else:
            open_issue(title, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
