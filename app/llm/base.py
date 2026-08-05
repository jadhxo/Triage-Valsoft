from __future__ import annotations

from typing import Any, Protocol


class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def analyze(self, message: str, system_prompt: str) -> Any: ...

    def repair(
        self,
        message: str,
        candidate: Any,
        validation_errors: list[str],
        system_prompt: str,
    ) -> Any: ...

    def summarize(self, validated_context: dict[str, Any], system_prompt: str) -> Any: ...
