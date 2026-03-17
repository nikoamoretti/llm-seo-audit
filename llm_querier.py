"""
LLM API Querier - Handles querying multiple LLM providers.
Supports: Claude (Anthropic), GPT (OpenAI), Gemini (Google), Perplexity
"""

import anthropic
import openai
from google import genai


SUFFIX = (
    "\n\nPlease provide specific business names and brief reasons for each recommendation. "
    "List them in order of your confidence in the recommendation."
)


class LLMQuerier:
    """Queries multiple LLM APIs with business-related prompts."""

    def __init__(self, api_keys: dict):
        self.api_keys = api_keys
        self._clients = {}

        if "anthropic" in api_keys:
            self._clients["anthropic"] = anthropic.Anthropic(api_key=api_keys["anthropic"])

        if "openai" in api_keys:
            self._clients["openai"] = openai.OpenAI(api_key=api_keys["openai"])

        if "gemini" in api_keys:
            self._clients["gemini"] = genai.Client(api_key=api_keys["gemini"])

        if "perplexity" in api_keys:
            self._clients["perplexity"] = openai.OpenAI(
                api_key=api_keys["perplexity"],
                base_url="https://api.perplexity.ai",
            )

    def query(self, provider: str, prompt: str) -> str:
        """Query a specific LLM provider and return the text response."""
        method = getattr(self, f"_query_{provider}", None)
        if method is None:
            raise ValueError(f"Unknown provider: {provider}")
        return method(prompt)

    def _query_anthropic(self, prompt: str) -> str:
        client = self._clients["anthropic"]
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt + SUFFIX}],
        )
        return message.content[0].text

    def _query_openai(self, prompt: str) -> str:
        client = self._clients["openai"]
        response = client.chat.completions.create(
            model="gpt-5.4",
            max_completion_tokens=1024,
            messages=[{"role": "user", "content": prompt + SUFFIX}],
        )
        return response.choices[0].message.content

    def _query_gemini(self, prompt: str) -> str:
        client = self._clients["gemini"]
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt + SUFFIX,
        )
        return response.text

    def _query_perplexity(self, prompt: str) -> str:
        client = self._clients["perplexity"]
        response = client.chat.completions.create(
            model="sonar",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt + SUFFIX}],
        )
        return response.choices[0].message.content
