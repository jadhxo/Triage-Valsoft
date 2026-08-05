from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLMProvider
from app.llm.groq_provider import GroqProvider
from app.llm.ollama_provider import OllamaProvider


class UnavailableProvider:
    provider_name = "unavailable"

    def __init__(self, model: str, reason: str) -> None:
        self.model_name = model
        self._reason = reason

    def analyze(self, message: str, system_prompt: str):
        del message, system_prompt
        raise RuntimeError(self._reason)

    def repair(self, message: str, candidate, validation_errors: list[str], system_prompt: str):
        del message, candidate, validation_errors, system_prompt
        raise RuntimeError(self._reason)

    def summarize(self, validated_context: dict, system_prompt: str):
        del validated_context, system_prompt
        raise RuntimeError(self._reason)


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model=settings.llm_model)
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
    return GroqProvider(api_key=settings.groq_api_key, model=settings.llm_model)


def create_provider_for_api(settings: Settings) -> LLMProvider:
    try:
        return create_provider(settings)
    except RuntimeError as exc:
        return UnavailableProvider(settings.llm_model, str(exc))
