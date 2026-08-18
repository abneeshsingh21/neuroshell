# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Multi-Model Manager
Switch between Ollama models on-the-fly without restarting.
List available models, switch active model, and check model status.
"""

import time
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    size_gb: float = 0
    modified: str = ""
    family: str = ""
    parameters: str = ""
    quantization: str = ""
    is_active: bool = False


class ModelManager:
    """
    Manages LLM model selection and switching.

    Features:
    - List all available Ollama models
    - Switch active model at runtime
    - Model information display
    - Warm-up ping after switching
    """

    def __init__(self, config, llm_client=None):
        self.config = config
        self.llm = llm_client
        self._last_models: list[ModelInfo] = []
        self._last_check: float = 0

    def list_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List all available Ollama models."""
        # Cache for 30 seconds
        if not force_refresh and self._last_models and (time.time() - self._last_check < 30):
            return self._last_models

        try:
            import ollama
            response = ollama.list()
            models = response.get("models", [])

            result = []
            for m in models:
                name = m.get("name", "")
                size_bytes = m.get("size", 0)
                details = m.get("details", {})

                info = ModelInfo(
                    name=name,
                    size_gb=round(size_bytes / (1024**3), 1) if size_bytes else 0,
                    modified=m.get("modified_at", "")[:10],
                    family=details.get("family", ""),
                    parameters=details.get("parameter_size", ""),
                    quantization=details.get("quantization_level", ""),
                    is_active=(name == self.config.llm.model),
                )
                result.append(info)

            self._last_models = result
            self._last_check = time.time()
            return result

        except ImportError:
            return []
        except Exception:
            return self._last_models

    def switch_model(self, model_name: str) -> tuple[bool, str]:
        """
        Switch to a different model.
        Returns (success, message).
        """
        models = self.list_models(force_refresh=True)
        model_names = [m.name for m in models]

        # Check exact match
        if model_name not in model_names:
            # Try partial match
            matches = [n for n in model_names if model_name.lower() in n.lower()]
            if len(matches) == 1:
                model_name = matches[0]
            elif len(matches) > 1:
                return False, f"Ambiguous model name. Matches: {', '.join(matches)}"
            else:
                return False, f"Model '{model_name}' not found. Use 'models' to list available models."

        # Update config
        old_model = self.config.llm.model
        self.config.llm.model = model_name

        # Update LLM client if available
        if self.llm:
            self.llm.model = model_name
            # Clear response cache for fresh results with new model
            if hasattr(self.llm, '_cache'):
                self.llm._cache.clear()

        # Warm-up ping
        warmup_ok = self._warmup(model_name)
        status = "ready" if warmup_ok else "switched (warmup pending)"

        return True, f"Switched: {old_model} → {model_name} ({status})"

    def current_model(self) -> str:
        """Get the current active model name."""
        return self.config.llm.model

    def get_active_model(self) -> str:
        """Alias for current_model."""
        return self.current_model()

    def list_available_models(self) -> list[dict]:
        """Return list of models as dicts for UI select menu."""
        models = self.list_models()
        return [
            {
                "name": m.name,
                "description": f"{m.size_gb}GB {m.parameters}".strip(),
                "is_active": m.is_active,
            }
            for m in models
        ]

    def get_model_info(self, model_name: str = "") -> ModelInfo | None:
        """Get info about a specific model."""
        target = model_name or self.config.llm.model
        models = self.list_models()
        for m in models:
            if m.name == target:
                return m
        return None

    def get_formatted_list(self) -> str:
        """Get formatted list of available models."""
        models = self.list_models(force_refresh=True)

        if not models:
            return "❌ No models found. Is Ollama running?\n   Start: ollama serve"

        lines = ["\n🤖 Available Models:\n"]

        for m in models:
            active = " ◀ active" if m.is_active else ""
            size = f"{m.size_gb}GB" if m.size_gb else ""
            params = f" | {m.parameters}" if m.parameters else ""
            quant = f" | {m.quantization}" if m.quantization else ""
            lines.append(f"  {'→' if m.is_active else ' '} {m.name:<30} {size}{params}{quant}{active}")

        lines.append(f"\n  Total: {len(models)} models | Active: {self.config.llm.model}")
        lines.append("  Switch: model <name>")
        return "\n".join(lines)

    def _warmup(self, model_name: str) -> bool:
        """Send a minimal request to warm up the model."""
        try:
            import ollama
            ollama.generate(model=model_name, prompt="hi", options={"num_predict": 1})
            return True
        except Exception:
            return False
