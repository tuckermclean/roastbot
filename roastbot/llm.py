from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


PROMPT_TEMPLATE = """
You are a brutally honest, witty, and hilarious senior engineer who roasts code mercilessly.
Stay savage about the code, but do not insult real-world protected traits.

Context:
- Repo: {repo}
- Subject: {subject}
- Author: {author}
- Base: {base}
- CI Status: {ci}

Diff (trimmed):
```
{diff}
```

Instructions:
- Produce:
  1) summary: Roasted paragraph that clearly states what’s wrong/right.
  2) issues: Bullet list. Each item: [severity: 🟥|🟧|🟨] message -> suggested fix.
  3) praise: Short, still snarky.
  4) one_killer_roast_line: Single memorable insult about the code, not the person.
- Focus on humor, correctness, security, performance, maintainability, tests, naming, style.
- Include precise, actionable suggestions. If something’s fine, acknowledge it briefly (in tone).
- Never use slurs or reference protected classes. Keep it professional-but-mean.
- Sprinkle ✨ a few emojis liberally.
- Output strings SHOULD be formatted as Markdown.

Example Structure:
```
{{'summary': 'A pithy summary','issues': ['🟥 A really bad issue', '🟧 Get this one soon', '🟨 Eh, maybe fix it'],'praise': 'Actually, it''s not so bad','one_killer_roast_line: 'OK, it really is that bad.'}}
```

"""


@dataclass
class LLMResponse:
    summary: str
    issues: str
    praise: str
    one_killer_roast_line: str


class RoastEngine:
    def __init__(self) -> None:
        pass

    def build_prompt(self, *, repo: str, subject: str, author: str, base: str, ci: str, diff: str) -> str:
        return PROMPT_TEMPLATE.format(repo=repo, subject=subject, author=author, base=base, ci=ci, diff=diff)

    def review(self, *, repo: str, subject: str, author: str, base: str, ci: str, diff: str) -> LLMResponse:
        # Mock implementation that returns templated roast. Replace with real API as needed.
        prompt = self.build_prompt(repo=repo, subject=subject, author=author, base=base, ci=ci, diff=diff)
        # Simulate some analysis by looking at diff length
        severity = "🟥" if len(diff) > 2000 else "🟧" if len(diff) > 400 else "🟨"
        summary = (
            f"Look at this masterpiece of chaos: '{subject}'. Half-baked abstractions flirting with undefined behavior. "
            f"It’s like you refactored by roulette. Fix the obvious sharp edges before this merges."
        )
        issues = [
            f"{severity} Diff size/control: Keep PRs small and coherent. Break this into focused changes.",
            f"🟧 Tests: Add unit/integration tests covering edge cases the diff obviously punts on.",
            f"🟨 Naming/structure: Pick names that don’t need a decoder ring and extract helpers."
        ]
        praise = "At least you used version control instead of emailing patches. Progress."
        one = "This PR handles edge cases the way a sieve handles water."
        return LLMResponse(summary=summary, issues=issues, praise=praise, one_killer_roast_line=one)
