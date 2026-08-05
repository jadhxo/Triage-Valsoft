from __future__ import annotations

import json
from typing import Any

from ollama import Client

from app.schemas import LLMAnalysis, SummaryOutput


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self, *, base_url: str, model: str) -> None:
        self.model_name = model
        self._client = Client(host=base_url)

    def _complete(
        self, system: str, user: str, schema: type[LLMAnalysis] | type[SummaryOutput]
    ) -> Any:
        response = self._client.chat(
            model=self.model_name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format=schema.model_json_schema(),
            options={"temperature": 0},
        )
        return json.loads(response.message.content)

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
