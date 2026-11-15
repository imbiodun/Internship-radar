import json
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.cache import Cache
from app.config import Settings, settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMError(RuntimeError):
    """Base error for failures at the LLM boundary."""


class LLMUnavailable(LLMError):
    """Raised when no configured provider can complete a request."""


class Provider(Protocol):
    name: str

    def complete(self, prompt: str, model: str, json_mode: bool) -> str:
        ...


@dataclass(frozen=True)
class AnthropicProvider:
    api_key: str
    cheap_model: str
    strong_model: str
    name: str = "anthropic"

    def complete(self, prompt: str, model: str, json_mode: bool) -> str:
        request = prompt
        if json_mode:
            request += "\nReturn only valid JSON with no markdown."
        try:
            response = Anthropic(api_key=self.api_key, timeout=45.0).messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": request}],
            )
            content = response.content[0]
            return content.text
        except Exception as exc:
            raise LLMError(f"Anthropic request failed: {type(exc).__name__}") from exc


@dataclass(frozen=True)
class OpenAICompatProvider:
    name: str
    api_key: str
    base_url: str

    def complete(self, prompt: str, model: str, json_mode: bool) -> str:
        try:
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=45.0,
            )
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if not content:
                raise LLMError("Provider returned an empty response")
            return content
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(
                f"{self.name} request failed: {type(exc).__name__}"
            ) from exc


def build_providers(config: Settings) -> list[Provider]:
    providers: list[Provider] = []
    provider_configs = {
        "anthropic": (
            config.anthropic_api_key,
            lambda: AnthropicProvider(
                api_key=config.anthropic_api_key or "",
                cheap_model=config.anthropic_cheap_model,
                strong_model=config.anthropic_strong_model,
            ),
        ),
        "gemini": (
            config.gemini_api_key,
            lambda: OpenAICompatProvider(
                name="gemini",
                api_key=config.gemini_api_key or "",
                base_url=config.gemini_base_url or "",
            ),
        ),
        "verda": (
            config.verda_api_key,
            lambda: OpenAICompatProvider(
                name="verda",
                api_key=config.verda_api_key or "",
                base_url=config.verda_base_url or "",
            ),
        ),
    }
    for provider_name in config.llm_chain:
        provider_config = provider_configs.get(provider_name)
        if provider_config is not None and provider_config[0]:
            providers.append(provider_config[1]())
    return providers


class LLMService:
    def __init__(
        self,
        config: Settings,
        providers: list[Provider] | None = None,
        cache: Cache | None = None,
    ) -> None:
        self.config = config
        self.providers = providers if providers is not None else build_providers(config)
        self.cache = cache or Cache(config.cache_db_path)

    def complete_json(
        self, prompt: str, schema: type[ModelT], tier: str
    ) -> ModelT:
        cache_key = Cache.key_for(
            {
                "schema_version": "llm-json-v1",
                "prompt": prompt,
                "schema": schema.model_json_schema(),
                "tier": tier,
            }
        )
        cached = self.cache.get(cache_key, self.config.extraction_ttl_seconds)
        if cached is not None:
            return schema.model_validate(cached.value["value"])
        if self.config.cache_only:
            raise LLMUnavailable("Response not cached and CACHE_ONLY=true")

        errors: list[str] = []
        for provider in self.providers:
            model = self._model_for(provider.name, tier)
            retry_prompt = prompt
            for attempt in range(2):
                try:
                    raw = provider.complete(retry_prompt, model, json_mode=True)
                    result = schema.model_validate_json(raw)
                except ValidationError as exc:
                    errors.append(f"{provider.name}: invalid JSON response")
                    retry_prompt = (
                        f"{prompt}\nValidation error: {exc}. Return corrected JSON only."
                    )
                    continue
                except LLMError as exc:
                    errors.append(str(exc))
                    break
                self.cache.record_event("llm_call", provider.name)
                self.cache.set(
                    cache_key,
                    "llm_extraction",
                    {"provider": provider.name, "value": result.model_dump(mode="json")},
                )
                return result
            if attempt == 1:
                continue
        raise LLMUnavailable("; ".join(errors) or "No LLM providers are configured")

    def complete_text(self, prompt: str, tier: str) -> str:
        cache_key = Cache.key_for(
            {"schema_version": "llm-text-v1", "prompt": prompt, "tier": tier}
        )
        cached = self.cache.get(cache_key, self.config.draft_ttl_seconds)
        if cached is not None:
            return str(cached.value["value"])
        if self.config.cache_only:
            raise LLMUnavailable("Response not cached and CACHE_ONLY=true")

        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider.complete(
                    prompt, self._model_for(provider.name, tier), json_mode=False
                )
            except LLMError as exc:
                errors.append(str(exc))
                continue
            self.cache.record_event("llm_call", provider.name)
            self.cache.set(
                cache_key,
                "llm_text",
                {"provider": provider.name, "value": result},
            )
            return result
        raise LLMUnavailable("; ".join(errors) or "No LLM providers are configured")

    def _model_for(self, provider_name: str, tier: str) -> str:
        if provider_name == "anthropic":
            return (
                self.config.anthropic_cheap_model
                if tier == "cheap"
                else self.config.anthropic_strong_model
            )
        if provider_name == "gemini":
            return self.config.gemini_model or ""
        if provider_name == "verda":
            return self.config.verda_model or ""
        raise LLMError(f"Unknown LLM provider: {provider_name}")


_service: LLMService | None = None


def _default_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService(settings)
    return _service


def complete_json(prompt: str, schema: type[ModelT], tier: str) -> ModelT:
    return _default_service().complete_json(prompt, schema, tier)


def complete_text(prompt: str, tier: str) -> str:
    return _default_service().complete_text(prompt, tier)
