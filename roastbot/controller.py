from __future__ import annotations

import logging
from typing import Optional

from .config import Settings
from .diff_utils import summarize_diff
from .github_client import GitHubClient
from .llm import RoastEngine
from .llm_openai import OpenAIEngine, OpenAIConfig
from .state import State

logger = logging.getLogger(__name__)


class Controller:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gh = GitHubClient(settings.github_token)
        # Select LLM engine
        if settings.llm_provider == "openai":
            try:
                if not settings.openai_api_key:
                    raise ValueError("OPENAI_API_KEY is required when llm_provider=openai")
                self.engine = OpenAIEngine(
                    OpenAIConfig(api_key=settings.openai_api_key, model=settings.openai_model, base_url=settings.openai_base_url)
                )
            except Exception as e:
                logger.warning("OpenAI engine unavailable (%s); falling back to mock engine.", e)
                self.engine = RoastEngine()
        else:
            self.engine = RoastEngine()
        self.state = State(settings.state_file)
        self.state.load()

    def run_once(self) -> None:
        for full_repo in self.settings.repos:
            try:
                self._process_repo(full_repo)
            except Exception as e:
                logger.exception("Error processing repo %s: %s", full_repo, e)
        self.state.save(max_entries=getattr(self.settings, "state_max_entries", None) or None)

    def _process_repo(self, full_repo: str) -> None:
        prs = self.gh.list_open_prs(full_repo)
        logger.info("Repo %s: found %d open PRs", full_repo, len(prs))
        for pr in prs:
            if self.state.has_reviewed(full_repo, pr.head_sha):
                logger.debug("Already reviewed %s@%s", full_repo, pr.head_sha[:7])
                continue
            if self.settings.branch_filters and pr.base_ref not in self.settings.branch_filters:
                logger.debug("Skipping PR #%s base %s not in filters", pr.number, pr.base_ref)
                continue
            self._review_pr(pr)
            # Mark all commits in this PR as reviewed
            try:
                owner, repo = full_repo.split("/", 1)
                commits = self.gh.get_pr_commits(owner, repo, pr.number)
                for sha in commits:
                    self.state.mark_reviewed(full_repo, sha)
            except Exception as e:
                logger.warning("Error marking commits from PR #%s: %s", pr.number, e)
            self.state.mark_reviewed(full_repo, pr.head_sha)
        # Optionally review branch commits that are not part of any PR
        if self.settings.review_commits:
            owner, repo = full_repo.split("/", 1)
            for branch in (self.settings.branch_filters or []):
                try:
                    commits = self.gh.list_commits(full_repo, branch, per_page=30)
                except Exception as e:
                    logger.warning("Failed listing commits for %s %s: %s", full_repo, branch, e)
                    continue
                logger.info("Repo %s branch %s: inspecting %d commits", full_repo, branch, len(commits))
                for c in commits:
                    sha = c.get("sha")
                    if not sha:
                        continue
                    if self.state.has_reviewed(full_repo, sha):
                        logger.debug("Already reviewed commit %s@%s", full_repo, sha[:7])
                        continue
                    # Skip merge commits (multi-parent)
                    parents = c.get("parents") or []
                    if isinstance(parents, list) and len(parents) >= 2:
                        logger.debug("Skipping merge commit %s", sha[:7])
                        continue
                    # Skip commits that are associated with any PR (open/closed)
                    try:
                        if self.gh.pulls_for_commit(owner, repo, sha):
                            logger.debug("Skipping commit %s; associated with PR", sha[:7])
                            continue
                    except Exception as e:
                        logger.debug("pulls_for_commit failed for %s: %s; proceeding", sha[:7], e)
                    try:
                        self._review_commit(full_repo, owner, repo, branch, c)
                    except Exception as e:
                        logger.error("_review_commit failed for %s: %s; not reviewed", sha[:7], e)
                    self.state.mark_reviewed(full_repo, sha)

    def _review_pr(self, pr) -> None:
        diff = self.gh.get_pr_diff(pr.owner, pr.repo, pr.number)
        files = self.gh.get_pr_files(pr.owner, pr.repo, pr.number)
        ci = self.gh.commit_status(pr.owner, pr.repo, pr.head_sha)
        ci_summary = ci.get("state", "unknown").upper()
        trimmed = summarize_diff(diff)
        prompt = self.engine.build_prompt(
            repo=f"{pr.owner}/{pr.repo}", subject=pr.title, author=pr.author, base=pr.base_ref, ci=ci_summary, diff=trimmed
        )
        resp = self.engine.review(repo=f"{pr.owner}/{pr.repo}", subject=pr.title, author=pr.author, base=pr.base_ref, ci=ci_summary, diff=trimmed)
        body = self._format_review_body(pr, resp, prompt)
        self.gh.post_pr_review(pr.owner, pr.repo, pr.number, body)
        logger.info("Posted review on %s PR #%d (%s)", f"{pr.owner}/{pr.repo}", pr.number, pr.head_sha[:7])

    def _review_commit(self, full_repo: str, owner: str, repo: str, branch: str, commit: dict) -> None:
        sha = commit["sha"]
        try:
            diff = self.gh.get_commit_diff(owner, repo, sha)
        except Exception as e:
            logger.warning("Failed to fetch diff for %s@%s: %s", full_repo, sha[:7], e)
            return
        ci = {}
        try:
            ci = self.gh.commit_status(owner, repo, sha)
        except Exception:
            pass
        ci_summary = (ci.get("state") or "unknown").upper()
        msg = (commit.get("commit", {}) or {}).get("message") or ""
        subject_line = msg.splitlines()[0].strip() if msg else ""
        author = (commit.get("commit", {}).get("author", {}) or {}).get("name") or (commit.get("author", {}) or {}).get("login") or "unknown"
        trimmed = summarize_diff(diff)
        subject = f"Commit {sha[:7]} to {branch}: {subject_line}".strip()
        prompt = self.engine.build_prompt(repo=f"{owner}/{repo}", subject=subject, author=author, base=branch, ci=ci_summary, diff=trimmed)
        resp = self.engine.review(repo=f"{owner}/{repo}", subject=subject, author=author, base=branch, ci=ci_summary, diff=trimmed)
        body = self._format_commit_body(owner, repo, sha, branch, subject_line, resp, prompt)
        self.gh.post_commit_comment(owner, repo, sha, body)
        logger.info("Posted review on %s commit %s", f"{owner}/{repo}", sha[:7])

    @staticmethod
    def _format_issues(issues) -> str:
        if issues is None:
            return "No issues found."
        if isinstance(issues, str):
            return issues
        try:
            items = [str(i) for i in list(issues)]
        except Exception:
            return str(issues)
        if not items:
            return "No issues found."
        return "\n\n---\n\n".join(items)

    @staticmethod
    def _format_review_body(pr, resp, prompt: str) -> str:
        marker = GitHubClient.review_marker(f"{pr.owner}/{pr.repo}", pr.head_sha)
        return ''.join([
            f"{marker}\n"
            f"# 🔥 RoastBot Review\n\n ### For {pr.owner}/{pr.repo} PR #{pr.number}: {pr.title}\n\n"
            f"📃 Summary\n-------\n{resp.summary}\n\n"
            f"😖 Issues\n------\n" + Controller._format_issues(resp.issues) + "\n\n"
            f"👍 Praise\n------\n{resp.praise}\n\n"
            f"😈 Killer Roast\n------------\n{resp.one_killer_roast_line}\n\n"
        ])

    @staticmethod
    def _format_commit_body(owner: str, repo: str, sha: str, branch: str, subject_line: str, resp, prompt: str) -> str:
        marker = GitHubClient.review_marker(f"{owner}/{repo}", sha)
        title = subject_line or sha[:7]
        return ''.join([
            f"{marker}\n"
            f"# 🔥 RoastBot Review\n\n ### For {owner}/{repo} commit {sha[:7]} on {branch}: {title}\n\n"
            f"📃 Summary\n-------\n{resp.summary}\n\n"
            f"😖 Issues\n------\n" + Controller._format_issues(resp.issues) + "\n\n"
            f"👍 Praise\n------\n{resp.praise}\n\n"
            f"😈 Killer Roast\n------------\n{resp.one_killer_roast_line}\n\n"
        ])
