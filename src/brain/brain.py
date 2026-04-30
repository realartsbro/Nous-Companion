"""
Nous Companion — Brain

LLM-driven quip generation using character personality.
Generates short, in-character reactions with expression selection.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

from brain.character_loader import Character
from hermes_runtime import get_api_server_key, get_api_server_url

logger = logging.getLogger(__name__)


@dataclass
class Quip:
    """A generated quip with expression selection."""
    text: str
    expression: str
    raw_response: str = ""


# Default LLM config — routes through hermes's API server
# hermes handles: model switching, provider routing, API keys, godmode
DEFAULT_LLM_CONFIG = {
    "base_url": get_api_server_url(),  # hermes API server (OpenAI-compatible)
    "model": "hermes-agent",  # hermes ignores this — uses its active model
    "api_key": get_api_server_key(),
    "temperature": 0.7,
    "max_tokens": 150,
    "timeout_s": 30,
}


class Brain:
    """Generates character quips via LLM based on conversation context."""

    def __init__(
        self,
        character: Character,
        llm_config: Optional[dict] = None,
    ):
        self.character = character
        self.llm = {**DEFAULT_LLM_CONFIG, **(llm_config or {})}
        self._system_prompt = character.build_system_prompt()

        # Conversation context for continuity
        self._history: list[dict] = []
        self._max_history = 6  # keep last 3 exchanges

    def _build_messages(self, context: str) -> list[dict]:
        """Build the messages array for the LLM call."""
        messages = [
            {"role": "system", "content": self._system_prompt},
        ]
        # Add recent history for continuity
        messages.extend(self._history)
        # Add current context
        messages.append({"role": "user", "content": context})
        return messages

    def _update_history(self, context: str, quip_text: str):
        """Maintain a short conversation history for context."""
        self._history.append({"role": "user", "content": context})
        self._history.append({"role": "assistant", "content": quip_text})
        # Trim to max
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    async def generate_quip(
        self,
        context: str,
        event_type: str = "response",
    ) -> Quip:
        """
        Generate a quip based on conversation context.

        Args:
            context: What just happened (e.g., user query, assistant response, tool output)
            event_type: thinking | response | tool_use | error
        """
        # Build a natural context prompt
        event_prefix = {
            "thinking": "The assistant just received a query and is thinking about it.",
            "response": "The assistant just responded.",
            "tool_use": "The assistant just used a tool.",
            "error": "Something just went wrong.",
        }.get(event_type, "Something just happened.")

        full_context = f"{event_prefix}\n\nContext:\n{context[:800]}"

        messages = self._build_messages(full_context)

        try:
            quip = await self._call_llm(messages)
            self._update_history(full_context, quip.text)

            # Validate expression exists, fall back to neutral
            if quip.expression not in self.character.expression_names:
                logger.warning(
                    f"LLM picked unknown expression '{quip.expression}', "
                    f"falling back to 'neutral'"
                )
                quip.expression = "neutral"

            return quip

        except Exception as e:
            logger.error(f"Brain LLM call failed: {e}")
            # Fallback quip — no LLM needed
            return Quip(
                text="...",
                expression="neutral",
                raw_response=f"ERROR: {e}",
            )

    async def _call_llm(self, messages: list[dict]) -> Quip:
        """Call the LLM and parse the response."""
        url = f"{self.llm['base_url']}/chat/completions"
        payload = {
            "model": self.llm["model"],
            "messages": messages,
            "temperature": self.llm["temperature"],
            "max_tokens": self.llm["max_tokens"],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.llm['api_key']}",
        }

        timeout = aiohttp.ClientTimeout(total=self.llm["timeout_s"])

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"LLM returned {resp.status}: {body[:200]}"
                    )

                data = await resp.json()
                content = data["choices"][0]["message"]["content"]

        # Parse JSON response
        quip = self._parse_quip(content)
        quip.raw_response = content
        return quip

    def _parse_quip(self, raw: str) -> Quip:
        """Parse LLM response into a Quip. Handles JSON with markdown fences."""
        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            return Quip(
                text=data.get("quip", text),
                expression=data.get("expression", "neutral"),
            )
        except json.JSONDecodeError:
            # LLM didn't return JSON — treat entire response as quip text
            logger.warning(f"LLM didn't return valid JSON, using raw text as quip")
            return Quip(text=text, expression="neutral")

    def clear_history(self):
        """Reset conversation history (e.g., on session change)."""
        self._history.clear()
