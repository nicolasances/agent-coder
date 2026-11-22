"""Idempotency check: is there already an open PR for the issue this task implements?

Pub/Sub is at-least-once, so a task can be delivered twice. Before spending a 3 hour agent
run, ask GitHub. Matching is on how the /implement flow links a PR to its issue: a closing
keyword ("Closes #N") in the PR body, which GitHub also surfaces as closingIssuesReferences.
Branch names are deliberately not used: the agent invents them.

Partial work (a pushed branch with no PR) is not a PR, so it is ignored.
"""

import json
import os
import re
import subprocess
from typing import Callable

ISSUE_URL_PATTERN = re.compile(r"^https://github\.com/([^/]+/[^/]+)/issues/(\d+)/?$")


def parse_issue_url(issue_url: str) -> tuple[str, int]:
    """Split https://github.com/<owner>/<repo>/issues/<n> into ("owner/repo", n)."""

    match = ISSUE_URL_PATTERN.match(issue_url)

    if not match:
        raise ValueError(f"Not a GitHub issue URL: {issue_url}")

    return match.group(1), int(match.group(2))


def gh_runner(token: str) -> Callable[[list[str]], str]:
    """A function running `gh <args>` with the given token, returning stdout."""

    def run_gh(args: list[str]) -> str:
        env = {**os.environ, "GH_TOKEN": token}
        result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env)

        if result.returncode != 0:
            raise RuntimeError(f"gh {' '.join(args[:2])} failed with exit code {result.returncode}: {result.stderr}")

        return result.stdout

    return run_gh


def open_pr_exists_for_issue(issue_url: str, run_gh: Callable[[list[str]], str]) -> bool:
    repo, issue_number = parse_issue_url(issue_url)

    output = run_gh(["pr", "list", "--repo", repo, "--state", "open", "--limit", "200", "--json", "number,body,closingIssuesReferences"])

    closing_keyword = re.compile(rf"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#{issue_number}\b", re.IGNORECASE)

    for pr in json.loads(output):
        linked = [ref.get("number") for ref in pr.get("closingIssuesReferences") or []]

        if issue_number in linked or closing_keyword.search(pr.get("body") or ""):
            return True

    return False
