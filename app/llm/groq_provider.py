from __future__ import annotations

import json
from typing import Any

from groq import Groq

from app.schemas import LLMAnalysis, SummaryOutput


class GroqProvider:
    provider_name = "groq"

    def __init__(self, *, api_key: str, model: str) -> None:
        self.model_name = model
        self._client = Groq(api_key=api_key)

    def _complete(
        self, system: str, user: str, schema: type[LLMAnalysis] | type[SummaryOutput]
    ) -> Any:
        response = self._client.chat.completions.create(
            model=self.model_name,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    # Best-effort schema mode works across more Groq models; Pydantic
                    # remains authoritative and the graph performs one bounded repair.
                    "strict": False,
                    "schema": schema.model_json_schema(),
                },
            },
        )
        return json.loads(response.choices[0].message.content or "")

    def analyze(self, message: str, system_prompt: str) -> Any:
        return self._complete(system_prompt, message, LLMAnalysis)

    def repair(
        self, message: str, candidate: Any, validation_errors: list[str], system_prompt: str
    ) -> Any:
        request = (
            f"Message:\n{message}\n\nInvalid output:\n{candidate!r}\n\n"
            f"Validation errors:\n{validation_errors!r}\nReturn a corrected result."
        )
        return self._complete(system_prompt, request, LLMAnalysis)

    def summarize(self, validated_context: dict[str, Any], system_prompt: str) -> Any:
        return self._complete(system_prompt, json.dumps(validated_context), SummaryOutput)
