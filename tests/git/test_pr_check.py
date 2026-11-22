import json

import pytest

from runner.git.pr_check import open_pr_exists_for_issue, parse_issue_url

ISSUE_URL = "https://github.com/acme/widgets/issues/8"


def gh_returning(prs: list):
    calls = []

    def run_gh(args: list[str]) -> str:
        calls.append(args)

        return json.dumps(prs)

    run_gh.calls = calls  # type: ignore[attr-defined]

    return run_gh


def test_parse_issue_url_returns_repo_and_number():
    assert parse_issue_url(ISSUE_URL) == ("acme/widgets", 8)


def test_parse_issue_url_rejects_something_that_is_not_an_issue_url():
    with pytest.raises(ValueError):
        parse_issue_url("https://github.com/acme/widgets/pull/8")


def test_no_open_prs_means_no_existing_pr():
    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning([])) is False


def test_pr_that_github_links_to_the_issue_counts():
    prs = [{"number": 3, "body": "", "closingIssuesReferences": [{"number": 8}]}]

    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is True


def test_pr_with_closes_keyword_in_the_body_counts():
    prs = [{"number": 3, "body": "Implements the thing.\n\nCloses #8", "closingIssuesReferences": []}]

    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is True


def test_closes_keyword_is_case_insensitive_and_accepts_fixes_and_resolves():
    for body in ["closes #8", "Fixes #8", "resolved #8"]:
        prs = [{"number": 3, "body": body, "closingIssuesReferences": []}]

        assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is True


def test_pr_for_a_different_issue_does_not_count():
    prs = [{"number": 3, "body": "Closes #9", "closingIssuesReferences": [{"number": 9}]}]

    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is False


def test_issue_number_that_merely_starts_with_the_same_digits_does_not_count():
    prs = [{"number": 3, "body": "Closes #80", "closingIssuesReferences": []}]

    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is False


def test_pr_that_only_mentions_the_issue_without_a_closing_keyword_does_not_count():
    prs = [{"number": 3, "body": "Related to #8", "closingIssuesReferences": []}]

    assert open_pr_exists_for_issue(ISSUE_URL, gh_returning(prs)) is False


def test_it_asks_gh_for_open_prs_of_the_issues_repo():
    run_gh = gh_returning([])

    open_pr_exists_for_issue(ISSUE_URL, run_gh)

    args = run_gh.calls[0]  # type: ignore[attr-defined]

    assert args[:3] == ["pr", "list", "--repo"]
    assert "acme/widgets" in args
    assert "open" in args
