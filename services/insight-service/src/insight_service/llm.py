"""The call to the language model: a prompt template, the chat model of LangChain and a parser of
the text, joined in a chain. Also the list of the models of a provider.

`ChatOpenAI` talks to any API with the chat completions of OpenAI when it is given its address. The
person chooses the provider from a fixed list (never an address: our server would call any address
it is given) and brings their own key, which comes with the question and is never kept.
"""

import json

import httpx
import openai
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

MAX_CHARACTERS = 1500
# At most this many names of models from a provider (some list hundreds).
MAX_MODELS = 500

# The providers that can be chosen, by id, and the address of their API.
PROVIDERS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "mistral": "https://api.mistral.ai/v1",
    "ollama": "https://ollama.com/v1",
    "openai": "https://api.openai.com/v1",
}

# The rules (with the question) as the system message, the facts as the message of the person.
PROMPT = ChatPromptTemplate.from_messages([("system", "{rules}"), ("human", "{facts}")])


class LlmUnavailable(Exception):
    """The model did not give a text. Its message never carries the key; `status` is the HTTP
    status of the provider, if it answered one (for the log)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class KeyRefused(LlmUnavailable):
    """The provider said no to the key (401 or 403)."""


class ProviderBusy(LlmUnavailable):
    """The provider said too many requests (429): the free plans allow so many tokens a minute."""


def reasons(provider: str, model: str) -> bool:
    """Whether the model "reasons" before it writes and takes `reasoning_effort` (gpt-oss in Groq,
    the gpt-5 and o models of OpenAI). Asked to reason little, it answers sooner, spends less of the
    quota and does not run out of room before the text. Other providers do not get the field."""
    if provider == "groq":
        return "gpt-oss" in model
    return provider == "openai" and model.startswith(("gpt-5", "o3", "o4"))


class Llm:
    def __init__(self, client: httpx.AsyncClient):
        # The HTTP client of the chat model: the tests give one with a fake model, no network.
        self.client = client

    def chat_model(self, provider: str, model: str, key: str) -> ChatOpenAI:
        """The chat model of this question: the provider, the model and the key of the person."""
        return ChatOpenAI(
            base_url=PROVIDERS[provider],
            model=model,
            api_key=key,
            temperature=0.3,
            timeout=20,
            # No retries: a question that fails says so, and the quota is not spent twice.
            max_retries=0,
            http_async_client=self.client,
            **({"reasoning_effort": "low"} if reasons(provider, model) else {}),
        )

    async def write(self, rules: str, facts: dict, provider: str, model: str, key: str) -> str:
        """The text that the model writes from the rules and the facts."""
        try:
            chain = PROMPT | self.chat_model(provider, model, key) | StrOutputParser()
            text = await chain.ainvoke(
                {"rules": rules, "facts": json.dumps(facts, ensure_ascii=False)}
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
            raise KeyRefused("the key was not accepted", error.status_code) from None
        except openai.RateLimitError:
            raise ProviderBusy("the provider is busy", 429) from None
        except openai.APIStatusError as error:
            raise LlmUnavailable("the model did not answer", error.status_code) from None
        except (openai.OpenAIError, httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # The message of the error is not kept: it could carry the key or the address.
            raise LlmUnavailable("the model did not answer") from None
        text = text.strip()
        if not text:
            raise LlmUnavailable("the model gave no text")
        return text[:MAX_CHARACTERS]

    async def models(self, provider: str, key: str) -> list[str]:
        """The names of the models of the provider that this key can use (GET /models, the same
        format in every provider of the list), in alphabetical order."""
        try:
            answer = await self.client.get(
                f"{PROVIDERS[provider]}/models", headers={"Authorization": f"Bearer {key}"}
            )
        except httpx.HTTPError:
            raise LlmUnavailable("the provider did not answer") from None
        if answer.status_code in (401, 403):
            raise KeyRefused("the key was not accepted", answer.status_code)
        if answer.status_code == 429:
            raise ProviderBusy("the provider is busy", 429)
        if answer.status_code != 200:
            raise LlmUnavailable("the provider did not answer", answer.status_code)
        try:
            items = answer.json()["data"]
            names = [item["id"] for item in items if isinstance(item, dict) and "id" in item]
        except (ValueError, KeyError, TypeError):
            raise LlmUnavailable("the provider gave no list") from None
        return sorted(name for name in names if isinstance(name, str))[:MAX_MODELS]
