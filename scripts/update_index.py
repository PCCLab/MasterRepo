#!/usr/bin/env python3
"""Rebuild the project index in README.md from all public repos carrying a topic tag.

Only metadata (name, description, link, language, last push) is read.
No code is copied. Standard library only, so there is nothing to install.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TOPIC_FILE = "topic.txt"            # the tag teams add to their repos
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = "README.md"
OWNERS_FILE = "allowed_owners.txt"  # one GitHub username per line
START, END = "<!-- INDEX:START -->", "<!-- INDEX:END -->"              # the table
TOPIC_START, TOPIC_END = "<!-- TOPIC:START -->", "<!-- TOPIC:END -->"  # the tag in the instructions

SKIP_ARCHIVED = False  # set True to hide archived repos
EXCLUDE = set()        # e.g. {"team-a/old-demo"} to hide specific repos


def load_topic(path=TOPIC_FILE):
    """Read the tag from topic.txt. The INDEX_TOPIC env variable, if set, overrides it (handy for tests)."""
    override = os.environ.get("INDEX_TOPIC", "").strip().lower()
    if override:
        return override
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Create it with the tag on a single line.")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip().lower()
            if line:
                return line
    sys.exit(f"{path} has no tag in it.")


def load_allowed_owners(path=OWNERS_FILE):
    """Read usernames from a text file. Empty set = no owner is allowed."""
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Create it with one GitHub username per line.")
    owners = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip().lower()
            if line:
                owners.add(line)
    return owners


TOPIC = load_topic()


def api(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_repos():
    """Public repos with the topic (forks are excluded by GitHub search by default)."""
    query = urllib.parse.quote(f"topic:{TOPIC} is:public")
    repos, page = [], 1
    while True:
        data = api(f"https://api.github.com/search/repositories"
                   f"?q={query}&per_page=100&page={page}")
        items = data.get("items", [])
        repos.extend(items)
        if len(items) < 100:
            return repos
        page += 1


def cell(text):
    """Make text safe inside a markdown table cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build_table(repos, allowed_owners):
    repos = [r for r in repos
             if r["full_name"] not in EXCLUDE
             and r["owner"]["login"].lower() in allowed_owners
             and not (SKIP_ARCHIVED and r["archived"])]
    repos.sort(key=lambda r: (r["owner"]["login"].lower(), r["name"].lower()))

    lines = [
        f"_{len(repos)} public projects tagged `{TOPIC}`._",
        "",
        "| Project | Team | Description | Language | Last update |",
        "|---|---|---|---|---|",
    ]
    for r in repos:
        owner = r["owner"]["login"]
        lines.append(
            f"| [{cell(r['name'])}]({r['html_url']}) "
            f"| [{cell(owner)}]({r['owner']['html_url']}) "
            f"| {cell(r['description'])} "
            f"| {cell(r['language'])} "
            f"| {(r['pushed_at'] or '')[:10]} |"
        )
    return "\n".join(lines)


def replace_between(content, start, end, text):
    """Replace everything between two markers. Returns None if the markers are missing."""
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        return None
    return pattern.sub(lambda _: f"{start}{text}{end}", content)


def main():
    allowed_owners = load_allowed_owners()
    if not allowed_owners:
        print(f"Warning: {OWNERS_FILE} has no usernames, so no repo will be listed.")

    try:
        repos = fetch_repos()
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub API error: {e.code} {e.reason}")

    with open(README, encoding="utf-8") as f:
        content = f.read()

    new_content = replace_between(content, START, END,
                                  f"\n{build_table(repos, allowed_owners)}\n")
    if new_content is None:
        sys.exit(f"Markers {START} / {END} not found in {README}")

    with_topic = replace_between(new_content, TOPIC_START, TOPIC_END, f"`{TOPIC}`")
    if with_topic is None:
        print(f"Note: markers {TOPIC_START} / {TOPIC_END} not found, "
              f"so the tag in the instructions was not updated.")
    else:
        new_content = with_topic

    if new_content == content:
        print("No changes.")
        return
    with open(README, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"Index updated: {len(repos)} repos found with the tag.")


if __name__ == "__main__":
    main()
