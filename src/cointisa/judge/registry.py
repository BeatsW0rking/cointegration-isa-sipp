from __future__ import annotations

from cointisa.judge.base import PlausibilityJudge
from cointisa.judge.clairic_backend import ClairicJudge
from cointisa.judge.claude_backend import ClaudeJudge
from cointisa.judge.jev_backend import JevJudge
from cointisa.judge.rules import RulesJudge

BACKENDS: dict[str, type[PlausibilityJudge]] = {
    "rules": RulesJudge,
    "claude": ClaudeJudge,
    "jev": JevJudge,
    "clairic": ClairicJudge,
}


def make_judge(name: str) -> PlausibilityJudge:
    return BACKENDS[name]()
