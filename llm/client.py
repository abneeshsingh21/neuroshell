# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell LLM Client — Production Grade
Handles LLM communication with streaming, exponential backoff retry,
response caching, token tracking, conversation memory, and multi-model routing.
Supports: Ollama (local) + Groq (cloud fallback).
"""

import os
import time
import json
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional, Generator, Callable
from dataclasses import dataclass, field
from collections import OrderedDict
from core.events import neuro_events

_llm_log = logging.getLogger("neuroshell.llm")

try:
    import ollama  # type: ignore[import-not-found]
    HAS_OLLAMA = True
except ImportError:
    ollama = None  # type: ignore[assignment]
    HAS_OLLAMA = False

try:
    from groq import Groq  # type: ignore[import-not-found]
    HAS_GROQ = True
except ImportError:
    Groq = None  # type: ignore[assignment,misc]
    HAS_GROQ = False

# Groq model mapping (local model → Groq equivalent)
GROQ_MODEL_MAP = {
    "qwen3:4b": "llama-3.1-8b-instant",
    "llama3": "llama-3.1-8b-instant",
    "llama3:8b": "llama-3.1-8b-instant",
    "mistral": "mixtral-8x7b-32768",
    "gemma2": "gemma2-9b-it",
    "deepseek-r1": "deepseek-r1-distill-llama-70b",
}


# ═══════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    """Comprehensive response from the LLM."""
    text: str
    model: str
    latency_ms: float
    tokens_used: int = 0
    is_fallback: bool = False
    error: str = ""
    from_cache: bool = False
    retry_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def success(self) -> bool:
        return bool(self.text) and not self.error


@dataclass
class ConversationMessage:
    """A message in conversation history."""
    role: str       # system, user, assistant
    content: str
    timestamp: float = field(default_factory=time.time)
    is_fragile: bool = False # Flag for microcompression candidates
    compressed: bool = False # Flag indicating if it has been microcompressed

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class TokenBudget:
    """Token usage tracking and budgeting."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_requests: int = 0
    total_failures: int = 0
    session_start: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def avg_tokens_per_request(self) -> float:
        return self.total_tokens / max(1, self.total_requests)

    @property
    def success_rate(self) -> float:
        total = self.total_requests + self.total_failures
        return round(self.total_requests / max(1, total) * 100, 1)  # type: ignore[return-value]

    def to_dict(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "avg_tokens_per_request": round(self.avg_tokens_per_request),
            "success_rate": self.success_rate,
            "session_s": round(time.time() - self.session_start),
        }


# ═══════════════════════════════════════════════════════════
# LRU Cache for Responses
# ═══════════════════════════════════════════════════════════

class LRUCache:
    """Thread-safe LRU cache for LLM responses."""

    def __init__(self, capacity: int = 200):
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str, max_age_s: float = 3600) -> Optional[str]:
        """Get cached value if not expired."""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (time.time() - timestamp) < max_age_s:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return value
                else:
                    del self._cache[key]  # type: ignore[misc]
            self._misses += 1
            return None

    def put(self, key: str, value: str):
        """Store a value."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (value, time.time())
            else:
                if len(self._cache) >= self._capacity:
                    self._cache.popitem(last=False)
                self._cache[key] = (value, time.time())

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "capacity": self._capacity,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(1, total) * 100, 1),  # type: ignore[arg-type]
        }

    def clear(self):
        with self._lock:
            self._cache.clear()


# ═══════════════════════════════════════════════════════════
# LLM Client — Production Engine
# ═══════════════════════════════════════════════════════════


# ============================================================
# Prompt Injection Sanitizer
# ============================================================

_PROMPT_INJECTION_TOKENS = [
    "[INST]", "[/INST]", "<<SYS>>", "<</SYS>>",
    "<|im_start|>", "<|im_end|>", "<|system|>",
    "IGNORE PREVIOUS INSTRUCTIONS",
    "Ignore all previous instructions",
]
_MAX_USER_CONTENT_LEN = 2000


def _sanitize_for_prompt(text: str) -> str:
    """Strip LLM injection tokens from user-controlled content."""
    for token in _PROMPT_INJECTION_TOKENS:
        text = text.replace(token, "[FILTERED]")
    if len(text) > _MAX_USER_CONTENT_LEN:
        text = text[:_MAX_USER_CONTENT_LEN] + "... [truncated]"
    return text


class LLMClient:
    """
    Production-grade LLM client with Ollama + Groq cloud fallback.

    Features:
    - Ollama (local) as primary, Groq (cloud) as fallback
    - Streaming token-by-token output
    - Exponential backoff retry (configurable attempts)
    - LRU response cache for repeated prompts
    - Token counting and budget tracking
    - Conversation memory with context window management
    - Health check with model availability verification
    - Graceful degradation when offline
    - Thread-safe caching
    """

    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0    # seconds
    RETRY_MULTIPLIER = 4.0
    HEALTH_CHECK_INTERVAL = 30   # seconds
    MAX_CONVERSATION_TURNS = 20
    CACHE_MAX_AGE = 3600         # 1 hour
    HARD_TIMEOUT = 60            # seconds — absolute wall-clock limit

    def __init__(self, config):
        self.config = config.llm
        self._available = False
        self._last_health_check: float = 0
        self._model_loaded = False
        self._cache = LRUCache(capacity=200)
        self._budget = TokenBudget()
        self._conversation: list[ConversationMessage] = []
        self._lock = threading.Lock()
        self._warmed_up = False

        # Groq cloud fallback
        self._groq_client: Any = None
        self._groq_available = False
        groq_key = os.environ.get("GROQ_API_KEY", getattr(self.config, "groq_api_key", ""))
        if HAS_GROQ and groq_key:
            try:
                self._groq_client = Groq(api_key=groq_key)  # type: ignore[misc]
                self._groq_available = True
            except Exception:
                pass

        # Hard timeout from config
        self._hard_timeout = getattr(
            getattr(config, 'resilience', None), 'llm_hard_timeout', self.HARD_TIMEOUT
        )

    # ═══════════════════════════════════════════════════════
    # Warmup & Prompt Compression
    # ═══════════════════════════════════════════════════════

    def warmup_async(self):
        """Pre-warm the Ollama model in background thread for faster first response."""
        if self._warmed_up or not HAS_OLLAMA:
            return

        def _warmup():
            try:
                ollama.chat(  # type: ignore[union-attr]
                    model=self.config.model,
                    messages=[{"role": "user", "content": "hi"}],
                    options={"num_predict": 1},
                    think=False,
                )
                self._warmed_up = True
                self._available = True
                self._model_loaded = True
            except Exception:
                pass

        thread = threading.Thread(target=_warmup, daemon=True)
        thread.start()

    @staticmethod
    def compress_prompt(prompt: str, max_chars: int = 2000) -> str:
        """Compress prompt to reduce token count while preserving meaning."""
        if len(prompt) <= max_chars:
            return prompt

        # Remove excessive whitespace
        import re
        prompt = re.sub(r'\n{3,}', '\n\n', prompt)
        prompt = re.sub(r' {2,}', ' ', prompt)
        prompt = re.sub(r'\t+', ' ', prompt)

        # Remove common filler phrases
        fillers = [
            "please note that ", "it is important to ", "as you can see ",
            "in other words ", "for example ", "that is to say ",
        ]
        for filler in fillers:
            prompt = prompt.replace(filler, "")

        # Truncate if still too long, keeping start and end
        if len(prompt) > max_chars:
            half = max_chars // 2 - 10
            prompt = prompt[:half] + "\n...\n" + prompt[-half:]  # type: ignore[index]

        return prompt.strip()

    def _adaptive_timeout(self, prompt: str) -> float:
        """Calculate adaptive timeout based on expected response length."""
        # Short prompts (completions, fixes) get shorter timeouts
        char_count = len(prompt)
        if char_count < 100:
            return 15.0
        elif char_count < 500:
            return 30.0
        else:
            return 60.0

    def _with_hard_timeout(self, func: Callable[..., Any], timeout: Optional[float] = None) -> Any:
        """Execute func with a hard wall-clock timeout to prevent shell freeze.

        Uses ThreadPoolExecutor so the main thread is never blocked indefinitely.
        If the call exceeds the timeout, raises TimeoutError.
        """
        timeout = timeout or self._hard_timeout
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(func)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                _llm_log.warning("LLM call timed out after %ds", timeout)
                raise TimeoutError(f"LLM call exceeded hard timeout of {timeout}s")

    @property
    def groq_model(self) -> str:
        """Get the Groq model equivalent for the current local model."""
        return GROQ_MODEL_MAP.get(self.config.model, "llama-3.1-8b-instant")

    @property
    def has_any_llm(self) -> bool:
        """Check if any LLM backend is available."""
        return self.is_available() or self._groq_available

    # ═══════════════════════════════════════════════════════
    # Health & Availability
    # ═══════════════════════════════════════════════════════

    def is_available(self) -> bool:
        """Check if Ollama is running and model is available (cached)."""
        now = time.time()
        if now - self._last_health_check < self.HEALTH_CHECK_INTERVAL:
            return self._available

        self._last_health_check = now

        if not HAS_OLLAMA:
            self._available = False
            return False

        try:
            models = ollama.list()  # type: ignore[union-attr]
            model_list = models.get("models", [])
            model_names = [m.get("name", "") for m in model_list]
            self._available = True
            self._model_loaded = any(self.config.model in name for name in model_names)
            return self._available
        except Exception:
            self._available = False
            return False

    def health_status(self) -> dict:
        """Get detailed health status."""
        available = self.is_available()
        return {
            "ollama_installed": HAS_OLLAMA,
            "ollama_running": available,
            "groq_available": self._groq_available,
            "active_backend": "ollama" if available else ("groq" if self._groq_available else "none"),
            "model": self.config.model,
            "groq_model": self.groq_model if self._groq_available else None,
            "model_loaded": self._model_loaded if available else False,
            "base_url": getattr(self.config, "base_url", "localhost:11434"),
            "cache": self._cache.stats,
            "budget": self._budget.to_dict(),
            "conversation_turns": len(self._conversation),
        }

    # ═══════════════════════════════════════════════════════
    # Groq Cloud Fallback Methods
    # ═══════════════════════════════════════════════════════

    def _groq_generate(self, prompt: str, system_prompt: str = "",
                       temperature: Optional[float] = None) -> LLMResponse:
        """Generate via Groq cloud API (fallback)."""
        if not self._groq_client:
            return self._fallback_response("Groq API not configured")

        start = time.time()
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self._groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            latency = (time.time() - start) * 1000
            text = response.choices[0].message.content if response.choices else ""
            usage = response.usage

            self._budget.total_requests += 1
            self._budget.total_completion_tokens += (usage.completion_tokens if usage else 0)
            self._budget.total_prompt_tokens += (usage.prompt_tokens if usage else 0)

            return LLMResponse(
                text=text,
                model=f"groq:{self.groq_model}",
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                tokens_used=(usage.total_tokens if usage else 0),
                prompt_tokens=(usage.prompt_tokens if usage else 0),
                completion_tokens=(usage.completion_tokens if usage else 0),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._budget.total_failures += 1
            return self._fallback_response(f"Groq error: {e}", latency)

    def _groq_generate_streaming(self, prompt: str, system_prompt: str = "",
                                  temperature: Optional[float] = None,
                                  callback: Optional[Callable[..., Any]] = None) -> LLMResponse:
        """Generate via Groq with streaming (fallback)."""
        if not self._groq_client:
            return self._fallback_response("Groq API not configured")

        start = time.time()
        chunks = []
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            stream = self._groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    chunks.append(delta.content)
                    if callback:
                        callback(delta.content)  # type: ignore[misc]

            latency = (time.time() - start) * 1000
            full_text = "".join(chunks)
            self._budget.total_requests += 1
            self._budget.total_completion_tokens += len(chunks)

            return LLMResponse(
                text=full_text,
                model=f"groq:{self.groq_model}",
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                tokens_used=len(chunks),
                completion_tokens=len(chunks),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._budget.total_failures += 1
            return LLMResponse(
                text="".join(chunks),
                model=f"groq:{self.groq_model}",
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                is_fallback=True, error=str(e),
            )

    def _groq_chat(self, user_message: str, system_prompt: str = "",
                   temperature: Optional[float] = None) -> LLMResponse:
        """Multi-turn chat via Groq (fallback)."""
        self._conversation.append(ConversationMessage(role="user", content=user_message))
        if len(self._conversation) > self.MAX_CONVERSATION_TURNS * 2:
            self._conversation = self._conversation[-(self.MAX_CONVERSATION_TURNS * 2):]  # type: ignore[index]

        if not self._groq_client:
            return self._fallback_response("Groq API not configured")

        start = time.time()
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend([m.to_dict() for m in self._conversation])

            response = self._groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            latency = (time.time() - start) * 1000
            text = response.choices[0].message.content if response.choices else ""
            self._conversation.append(ConversationMessage(role="assistant", content=text))

            usage = response.usage
            self._budget.total_requests += 1
            self._budget.total_completion_tokens += (usage.completion_tokens if usage else 0)

            return LLMResponse(
                text=text,
                model=f"groq:{self.groq_model}",
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                tokens_used=(usage.total_tokens if usage else 0),
                completion_tokens=(usage.completion_tokens if usage else 0),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._budget.total_failures += 1
            return self._fallback_response(f"Groq chat error: {e}", latency)

    # ═══════════════════════════════════════════════════════
    # Generation with Retry & Cache
    # ═══════════════════════════════════════════════════════

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        use_cache: bool = True,
        max_retries: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response with retry and caching. Falls back to Ollama if Groq fails."""
        prompt = _sanitize_for_prompt(prompt)  # Prevent prompt injection from command output
        # ── Priority: Groq Cloud (fast, <1s) → Ollama (slow, local) ──
        if self._groq_available:
            try:
                result = self._groq_generate(prompt, system_prompt, temperature)
                if result.success:
                    return result
            except Exception:
                pass  # Fall through to Ollama

        if not HAS_OLLAMA:
            return self._fallback_response("No LLM available (install Ollama or set GROQ_API_KEY)")

        # Check cache
        if use_cache:
            cache_key = self._cache_key(prompt, system_prompt, temperature)
            cached = self._cache.get(cache_key, max_age_s=self.CACHE_MAX_AGE)
            if cached:
                return LLMResponse(
                    text=cached, model=self.config.model,
                    latency_ms=0.1, from_cache=True,
                )

        # Retry loop with exponential backoff
        retries = max_retries or self.MAX_RETRIES
        delay = self.INITIAL_RETRY_DELAY
        last_error = ""
        start = time.time()  # Initialize here to prevent UnboundLocalError if retries=0

        for attempt in range(retries):
            start = time.time()
            try:
                messages = self._build_messages(prompt, system_prompt)

                response = self._with_hard_timeout(
                    lambda: ollama.chat(  # type: ignore[union-attr]
                        model=self.config.model,
                        messages=messages,
                        options={
                            "temperature": temperature or self.config.temperature,
                            "num_predict": self.config.max_tokens,
                        },
                        think=False,
                    )
                )

                latency = (time.time() - start) * 1000
                text = response.get("message", {}).get("content", "")
                # Strip any <think>...</think> reasoning tokens
                if '<think>' in text:
                    import re as _re
                    text = _re.sub(r'<think>.*?</think>', '', text, flags=_re.DOTALL).strip()
                eval_count = response.get("eval_count", 0)
                prompt_eval_count = response.get("prompt_eval_count", 0)

                # Update budget
                self._budget.total_requests += 1
                self._budget.total_completion_tokens += eval_count
                self._budget.total_prompt_tokens += prompt_eval_count

                # Cache successful response
                if text and use_cache:
                    self._cache.put(cache_key, text)

                result = LLMResponse(
                    text=text,
                    model=self.config.model,
                    latency_ms=round(latency, 1),  # type: ignore[arg-type]
                    tokens_used=eval_count + prompt_eval_count,
                    prompt_tokens=prompt_eval_count,
                    completion_tokens=eval_count,
                    retry_count=attempt,
                )
                return result

            except Exception as e:
                last_error = str(e)
                self._budget.total_failures += 1

                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= self.RETRY_MULTIPLIER  # type: ignore[misc]

        # Ollama exhausted — try Groq cloud fallback
        if self._groq_available:
            return self._groq_generate(prompt, system_prompt, temperature)

        latency = (time.time() - start) * 1000
        return self._fallback_response(last_error, latency)

    def generate_streaming(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        callback: Optional[Callable[..., Any]] = None,
    ) -> LLMResponse:
        """Generate with streaming token-by-token output. Falls back to Ollama."""
        # ── Priority: Groq Cloud (fast) → Ollama (local) ──
        if self._groq_available:
            try:
                result = self._groq_generate_streaming(prompt, system_prompt, temperature, callback)
                if result.success:
                    return result
            except Exception:
                pass  # Fall through to Ollama

        if not HAS_OLLAMA:
            return self._fallback_response("No LLM available (install Ollama or set GROQ_API_KEY)")

        start = time.time()
        chunks = []

        try:
            messages = self._build_messages(prompt, system_prompt)

            stream = ollama.chat(  # type: ignore[union-attr]
                model=self.config.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": temperature or self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
                think=False,  # Disable qwen3 thinking mode for speed
            )

            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    chunks.append(token)
                    if callback:
                        callback(token)  # type: ignore[misc]

            latency = (time.time() - start) * 1000
            full_text = "".join(chunks)

            self._budget.total_requests += 1
            self._budget.total_completion_tokens += len(chunks)

            return LLMResponse(
                text=full_text,
                model=self.config.model,
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                tokens_used=len(chunks),
                completion_tokens=len(chunks),
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            self._budget.total_failures += 1
            # Fallback to Groq cloud
            if self._groq_available and not chunks:
                return self._groq_generate_streaming(prompt, system_prompt, temperature, callback)
            return LLMResponse(
                text="".join(chunks),
                model=self.config.model,
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                is_fallback=True,
                error=str(e),
            )

    def generate_json(self, prompt: str, system_prompt: str = "") -> Optional[dict]:
        """Generate and parse a JSON response with robust extraction."""
        json_system = system_prompt + "\n\nRespond with valid JSON only. No markdown, no explanation. Be concise."
        response = self.generate(prompt, json_system)

        if not response.success:
            return None

        return self._extract_json(response.text)

    # ═══════════════════════════════════════════════════════
    # Conversation Memory
    # ═══════════════════════════════════════════════════════

    def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Multi-turn conversation with context window management. Falls back to Ollama."""
        
        # Microcompression heuristic: if user message is massive (e.g. pasted code/files), mark fragile
        is_massive = len(user_message) > 3000
        msg = ConversationMessage(role="user", content=user_message, is_fragile=is_massive)
        self._conversation.append(msg)

        # Trim conversation if too long
        if len(self._conversation) > self.MAX_CONVERSATION_TURNS * 2:
            self._conversation = self._conversation[-(self.MAX_CONVERSATION_TURNS * 2):]  # type: ignore[index]
            
        # Trigger background Token Garbage Collection (Microcompression)
        self._trigger_microcompression()

        # ── Priority: Groq Cloud (fast) → Ollama (local) ──
        if self._groq_available:
            try:
                result = self._groq_chat(user_message, system_prompt, temperature)
                if result.success:
                    self._conversation.append(ConversationMessage(role="assistant", content=result.text))
                    return result
            except Exception:
                pass  # Fall through to Ollama

        if not HAS_OLLAMA:
            return self._fallback_response("No LLM available (install Ollama or set GROQ_API_KEY)")

        start = time.time()

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt + "\n/no_think"})
            messages.extend([m.to_dict() for m in self._conversation])

            response = ollama.chat(  # type: ignore[union-attr]
                model=self.config.model,
                messages=messages,
                options={
                    "temperature": temperature or self.config.temperature,
                    "num_predict": self.config.max_tokens,
                },
                think=False,  # Disable qwen3 thinking mode for speed
            )

            latency = (time.time() - start) * 1000
            text = response.get("message", {}).get("content", "")
            # Strip <think> tags
            if '<think>' in text:
                import re as _re
                text = _re.sub(r'<think>.*?</think>', '', text, flags=_re.DOTALL).strip()

            # Add assistant response to history
            self._conversation.append(ConversationMessage(role="assistant", content=text))

            self._budget.total_requests += 1
            eval_count = response.get("eval_count", 0)
            self._budget.total_completion_tokens += eval_count

            return LLMResponse(
                text=text,
                model=self.config.model,
                latency_ms=round(latency, 1),  # type: ignore[arg-type]
                tokens_used=eval_count,
                completion_tokens=eval_count,
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._budget.total_failures += 1
            # Fallback to Groq cloud
            if self._groq_available:
                return self._groq_chat(user_message, system_prompt, temperature)
            return self._fallback_response(str(e), latency)

    def clear_conversation(self):
        """Clear conversation history."""
        self._conversation.clear()

    def get_conversation(self) -> list[dict]:
        """Get conversation history."""
        return [m.to_dict() for m in self._conversation]

    # ═══════════════════════════════════════════════════════
    # Multi-Agent Memory Microcompression
    # ═══════════════════════════════════════════════════════

    def _trigger_microcompression(self):
        """Asynchronously trigger token garbage collection for old fragile messages."""
        if not HAS_OLLAMA and not self._groq_available:
            return

        def _garbage_collect():
            with self._lock:
                # We need to leave the most recent 3 turns alone (immediate context)
                safe_zone = 3 * 2 # 3 pairs of user/assistant
                if len(self._conversation) <= safe_zone:
                    return
                
                # Check messages outside the safe zone
                target_msgs = self._conversation[:-safe_zone]
                
            for msg in target_msgs:
                if msg.is_fragile and not msg.compressed and len(msg.content) > 3000:
                    try:
                        # Summarize the massive payload
                        compression_prompt = f"Summarize the following terminal output or file contents in 3 bullet points so I retain core context but drop the bloat:\n\n{msg.content[:15000]}"
                        
                        # Use generate (not chat) to avoid polluting history further
                        res = self.generate(compression_prompt, system_prompt="You are an internal context-compressor. Be extremely concise.", use_cache=False)
                        
                        if res.success:
                            with self._lock:
                                msg.content = f"<SYSTEM_MICROCOMPRESSED>\n{res.text}\n</SYSTEM_MICROCOMPRESSED>"
                                msg.compressed = True
                                _llm_log.info(f"Microcompressed massive token block. Saved ~{res.tokens_used} tokens.")
                                neuro_events.emit("gc_update", f"⚡ Token GC: Microcompressed history saving ~{res.tokens_used} tokens.")
                    except Exception as e:
                        _llm_log.warning(f"Microcompression failed: {e}")

        # Spawn non-blocking garbage collector
        threading.Thread(target=_garbage_collect, daemon=True).start()

    # ═══════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════

    def _build_messages(self, prompt: str, system_prompt: str) -> list[dict]:
        """Build message list for the API."""
        messages = []
        if system_prompt:
            # Append /no_think to disable reasoning in qwen3 models
            messages.append({"role": "system", "content": system_prompt + "\n/no_think"})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _extract_json(self, text: str) -> Optional[dict]:
        """Robust JSON extraction from LLM output."""
        text = text.strip()

        # Strip <think>...</think> reasoning tags from qwen3
        if '<think>' in text:
            import re
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Handle markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])  # type: ignore[index]
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass

        # Find JSON objects and arrays
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])  # type: ignore[index]
                except json.JSONDecodeError:
                    # Try fixing common issues
                    candidate = text[start:end + 1]  # type: ignore[index]
                    # Remove trailing commas
                    import re
                    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
        return None

    def _cache_key(self, prompt: str, system_prompt: str, temperature: Optional[float]) -> str:
        """Generate cache key from prompt parameters."""
        content = f"{self.config.model}:{system_prompt}:{prompt}:{temperature or self.config.temperature}"  # type: ignore[index]
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _fallback_response(self, error: str, latency_ms: float = 0) -> LLMResponse:
        """Create a fallback error response."""
        return LLMResponse(
            text="", model=self.config.model,
            latency_ms=latency_ms, is_fallback=True, error=error,
        )

    @property
    def budget(self) -> dict:
        """Get token budget statistics."""
        return self._budget.to_dict()

    @property
    def cache_stats(self) -> dict:
        """Get cache statistics."""
        return self._cache.stats

    def clear_cache(self):
        """Clear the response cache."""
        self._cache.clear()
