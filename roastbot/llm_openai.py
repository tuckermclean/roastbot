from __future__ import annotations

import os, logging
from dataclasses import dataclass
from typing import Optional
from pprint import pprint

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from .llm import LLMResponse, PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


@dataclass
class OpenAIConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None


class OpenAIEngine:
    def __init__(self, cfg: OpenAIConfig) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package not installed; add 'openai' to dependencies")
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url) if cfg.base_url else OpenAI(api_key=cfg.api_key)
        self.model = cfg.model

    def build_prompt(self, *, repo: str, subject: str, author: str, base: str, ci: str, diff: str) -> str:
        return PROMPT_TEMPLATE.format(repo=repo, subject=subject, author=author, base=base, ci=ci, diff=diff)

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def review(self, *, repo: str, subject: str, author: str, base: str, ci: str, diff: str) -> LLMResponse:
        prompt = self.build_prompt(repo=repo, subject=subject, author=author, base=base, ci=ci, diff=diff)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a brutally honest, witty, and hilarious senior engineer who roasts code mercilessly while being technically precise and professional. Always produce strict JSON with keys: summary, issues, praise, one_killer_roast_line."},
                {"role": "user", "content": prompt + "\n\nRespond ONLY in minified JSON with keys: summary, issues, praise, one_killer_roast_line."},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        import json
        from .json_utils import coerce_roast_json
        try:
            data = json.loads(content)
        except Exception:
            data = {}
        
        pprint(data)
        parsed = coerce_roast_json(data)
        pprint(parsed)
        # If the model didn't actually give us anything useful, fall back to raw content
        if not (parsed.summary or parsed.issues or parsed.praise):
            logger.warning("OpenAI roast JSON was empty; falling back to raw content")
            text = (content or "").strip()
            return LLMResponse(
                summary=text or "LLM returned no structured roast content.",
                issues=[],
                praise="",
                one_killer_roast_line=parsed.one_killer_roast_line,  # keep default roast line
            )
        return LLMResponse(
            summary=parsed.summary,
            issues=parsed.issues,
            praise=parsed.praise,
            one_killer_roast_line=parsed.one_killer_roast_line,
        )
