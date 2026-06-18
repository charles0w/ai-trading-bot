"""LLM completion helpers (live). Kept tiny + lazy so the rest of the package
imports without the SDKs installed.

- anthropic_completion: the analyst writer (Claude).
- ollama_completion:    a cross-family judge (different family than the writer,
                        to avoid self-preference bias). Needs a local Ollama.
"""

from __future__ import annotations

from typing import Callable


def anthropic_completion(model: str = "claude-sonnet-4-6", max_tokens: int = 512) -> Callable[[str], str]:
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def complete(prompt: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in msg.content)

    return complete


def ollama_completion(model: str = "llama3.1", url: str = "http://localhost:11434/api/generate") -> Callable[[str], str]:
    import json
    import urllib.request

    def complete(prompt: str) -> str:
        body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get("response", "")

    return complete
