import json
import os
import anthropic
from typing import Tuple


class RewardSwarmJudge:
    _SYSTEM_PROMPT = 'You are a ruthless Adversarial Code Reviewer. Your job is to evaluate whether the provided stdout output genuinely proves that the given task_description was solved. Be strict. Output ONLY valid JSON with no markdown, no code blocks, no explanation outside JSON. Format: {"score": 1, "critique": ""} for pass, or {"score": 0, "critique": "detailed reason for failure"} for failure.'

    def __init__(self, use_opus: bool = False):
        self._client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        self._model = 'claude-opus-4-7' if use_opus else 'claude-sonnet-4-5'

    def judge(self, stdout: str, task_description: str) -> Tuple[bool, str]:
        """Evaluate if stdout proves task_description was solved. Returns (passed, critique)."""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=[{'type': 'text', 'text': self._SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}],
                messages=[{'role': 'user', 'content': f'TASK DESCRIPTION:\n{task_description}\n\nSANDBOX STDOUT:\n{stdout}'}],
            )
            response_text = response.content[0].text.strip()
            data = json.loads(response_text)
            return (bool(data.get('score', 0) == 1), str(data.get('critique', '')))
        except json.JSONDecodeError:
            return (False, f'Judge returned unparseable response: {response_text[:200]}')
        except anthropic.APIError:
            return (True, '')
        except Exception:
            return (True, '')
