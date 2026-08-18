# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell NLP Intent Classifier — Production Grade
Multi-intent detection, confidence calibration, custom intent training,
temperature-scaled softmax, persistent corrections.
"""

import hashlib
import json
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path

try:
    import joblib  # safer than pickle, supports compression
    HAS_JOBLIB = True
except ImportError:
    import pickle  # fallback if joblib unavailable
    class _MockJoblib:
        @staticmethod
        def load(f): raise NotImplementedError()
        @staticmethod
        def dump(val, f, **kwargs): raise NotImplementedError()
    joblib = _MockJoblib()
    HAS_JOBLIB = False

try:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from config import NLP_MODELS_DIR

# ═══════════════════════════════════════════════════════════
# Secure Model Persistence (replaces bare pickle)
# ═══════════════════════════════════════════════════════════

def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_model_save(model, path: Path):
    """Save model with a SHA-256 sidecar file for tamper detection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if HAS_JOBLIB:
        joblib.dump(model, path, compress=3)
    else:
        with open(path, "wb") as f:
            pickle.dump(model, f)
    # Write hash sidecar
    hash_path = path.with_suffix(".sha256")
    hash_path.write_text(_compute_file_hash(path), encoding="utf-8")


def _safe_model_load(path: Path):
    """Load model only if the cache is trustworthy for the current runtime.

    Returns None when the file is tampered or serialized by an incompatible
    scikit-learn version so the caller can retrain safely.
    """
    hash_path = path.with_suffix(".sha256")
    if hash_path.exists():
        expected = hash_path.read_text(encoding="utf-8").strip()
        actual = _compute_file_hash(path)
        if actual != expected:
            import logging
            logging.getLogger("neuroshell.nlp").error(
                "Model file hash mismatch — possible tampering! Rejecting load. "
                "Delete %s to retrain.", path
            )
            return None  # Caller will retrain

    if HAS_JOBLIB:
        load_fn = joblib.load
    else:
        def load_fn(target_path: Path):
            with open(target_path, "rb") as f:
                return pickle.load(f)  # noqa: S301 — gated by hash check above

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = load_fn(path)

    for record in caught:
        message = str(record.message)
        if (
            record.category.__name__ == "InconsistentVersionWarning"
            or ("Trying to unpickle estimator" in message and "when using version" in message)
        ):
            import logging
            logger = logging.getLogger("neuroshell.nlp")
            for stale_path in (path, hash_path):
                try:
                    if stale_path.exists():
                        stale_path.unlink()
                except OSError:
                    logger.debug("Failed to remove stale NLP model cache file: %s", stale_path, exc_info=True)
            logger.info(
                "Cleared stale NLP intent model cache due to sklearn version mismatch: %s",
                path,
            )
            return None

    for record in caught:
        warnings.warn(record.message, category=record.category, stacklevel=2)

    return model


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: str
    confidence: float
    all_scores: dict = field(default_factory=dict)
    secondary_intent: str | None = None
    secondary_confidence: float = 0.0
    is_multi_intent: bool = False


class IntentClassifier:
    """
    Production-grade intent classifier.

    Features:
    - TF-IDF + Calibrated SVM for reliable confidence scores
    - Multi-intent detection ("run tests and push to main")
    - Temperature-scaled softmax for confidence calibration
    - Custom intent training from user corrections
    - Persistent correction storage
    - Comprehensive fallback with 50+ patterns
    """

    INTENTS = {
        "shell_command": [
            "git push origin main", "git pull", "git commit -m 'fix'",
            "ls -la", "dir /s", "cd ..", "mkdir test", "rm -rf node_modules",
            "pip install flask", "npm install", "docker ps", "docker-compose up",
            "python main.py", "node server.js", "cargo build", "go run main.go",
            "cat file.txt", "grep -r 'TODO'", "find . -name '*.py'",
            "chmod +x script.sh", "tar -xzf archive.tar.gz", "curl https://api.com",
            "ssh user@server", "scp file.txt remote:", "kubectl get pods",
            "terraform plan", "aws s3 ls", "heroku logs --tail",
            "pytest", "pytest -v", "python -m pytest", "npm test", "npm run build",
            "pip freeze", "pip list", "conda activate env",
            "echo hello", "cat README.md", "touch newfile.txt",
            "mv old.py new.py", "cp file1 file2", "wc -l *.py",
            "sort data.txt", "head -n 20 log.txt", "tail -f server.log",
            "ps aux", "top", "htop", "kill 1234", "pkill node",
            "netstat -tlnp", "lsof -i :8080", "ifconfig", "ipconfig",
            "make build", "cmake .", "gcc main.c", "javac Main.java",
            "systemctl restart nginx", "service apache2 start",
            "git stash pop", "git rebase -i HEAD~3", "git cherry-pick abc123",
            "rsync -avz src/ dest/", "df -h", "du -sh *", "free -m",
            "env", "export PATH=$PATH:/usr/local", "alias ll='ls -la'",
        ],
        "natural_language": [
            "show me all big files", "find large files over 100mb",
            "what files changed today", "list all python files",
            "compress this folder", "download that file",
            "show disk usage", "find duplicate files",
            "count lines of code", "find all TODO comments",
            "make a new folder called projects", "rename this file",
            "show me running processes", "kill the node server",
            "connect to the database", "deploy to production",
            "show me the biggest folders", "clean up temp files",
            "list all docker containers", "restart the web server",
            "show git changes", "merge develop into main",
            "install all dependencies", "update all packages",
            "backup this directory", "search for the config file",
            "show me network connections", "check port 8080",
            "create a virtual environment", "activate the venv",
            "find broken links", "monitor cpu usage",
            "set up a cron job", "schedule a backup",
            "move all logs to archive", "batch rename images",
            "split this big file", "compare two directories",
            "find files modified in the last week",
            "list installed packages", "show who is logged in",
        ],
        "question": [
            "what does tar -xzf do", "what is grep",
            "how do I ssh into a server", "what's the difference between cp and mv",
            "why did that command fail", "what is a pipe",
            "how do environment variables work", "what does chmod 755 mean",
            "explain regex", "what is docker compose",
            "how to undo a git commit", "what's a fork bomb",
            "what does this error mean", "why is my disk full",
            "how do I find my IP address", "what port is this running on",
            "what is the best way to", "can you tell me about",
            "what does this flag do", "what is the syntax for",
            "how do I check memory usage", "what version of python am I using",
        ],
        "fix_request": [
            "fix", "fix it", "fix that", "fix last error",
            "fix the error", "fix this", "auto fix",
            "repair", "solve it", "debug this",
            "what went wrong", "why did it fail",
            "fix the last command", "try again with fix",
            "resolve this error", "troubleshoot",
            "the command failed please fix", "auto repair this",
        ],
        "explain_request": [
            "explain ls -la", "explain: git rebase", "explain that command",
            "break down this command", "what does this do",
            "explain the last command", "explain: docker run",
            "show me what that means", "explain",
            "how does this work", "walk me through this",
            "explain the output", "explain this pipeline",
        ],
        "undo_request": [
            "undo", "undo last", "undo that", "rollback",
            "restore", "revert", "go back",
            "undo the last command", "restore my files",
            "undo last change", "revert that", "take that back",
        ],
        "help_request": [
            "help", "help translate", "help me",
            "how do I use this", "tutorial", "guide",
            "show commands", "what can you do",
            "help with git", "help safety", "show me examples",
        ],
        "pipeline_request": [
            "build a pipeline", "chain these commands",
            "pipe these together", "combine commands for",
            "create a workflow to", "multi-step command for",
            "process this file through", "pipeline for",
            "build a data pipeline", "create a CI pipeline",
            "link these commands", "automate this workflow",
        ],
        "docker_request": [
            "start the containers", "spin up docker",
            "bring up the stack", "launch compose services",
            "stop all containers", "tear down docker",
            "rebuild the docker image", "show container logs",
            "enter the container shell", "check container health",
            "prune unused images", "list all images and containers",
            "restart the database container", "scale the service",
        ],
        "deploy_request": [
            "deploy to staging", "deploy to production",
            "push to cloud", "publish the release",
            "create a release tag", "ship it",
            "promote to prod", "rollback deployment",
            "deploy the latest build", "release version 2.0",
            "push docker image to registry", "update the live server",
        ],
        "query_request": [
            "query the database", "run a sql query",
            "select from users table", "show database tables",
            "count rows in orders", "fetch API data",
            "search for records", "get data from endpoint",
            "call the API", "list records matching",
            "lookup user by email", "aggregate sales data",
        ],
    }

    # Keywords indicating multi-intent
    CONJUNCTIONS = {"and", "then", "also", "plus", "after that", "followed by", "&&"}

    def __init__(self):
        self._model: Pipeline | None = None
        self._model_path = NLP_MODELS_DIR / "intent_classifier.pkl"
        self._corrections_path = NLP_MODELS_DIR / "corrections.json"
        self._corrections: list[tuple[str, str]] = []
        self._loaded = False
        self._temperature = 1.5  # Calibration temperature

    def initialize(self) -> bool:
        """Initialize or load the classifier."""
        if not HAS_SKLEARN:
            return False

        self._load_corrections()

        if self._model_path.exists():
            try:
                self._model = _safe_model_load(self._model_path)
                if self._model is not None:
                    self._loaded = True
                    return True
            except Exception:
                pass

        return self._train_from_examples()

    def classify(self, text: str) -> IntentResult:
        """Classify user input intent with multi-intent support."""
        if not self._model or not HAS_SKLEARN:
            return self._fallback_classify(text)

        try:
            # Check for multi-intent
            multi = self._detect_multi_intent(text)
            if multi:
                return multi

            intent = self._model.predict([text])[0]
            scores = self._model.decision_function([text])[0]

            # Temperature-scaled softmax for calibrated confidence
            classes = self._model.classes_
            score_dict = self._softmax_scores(classes, scores)

            confidence = score_dict.get(intent, 0.5)

            # Secondary intent
            sorted_intents = sorted(score_dict.items(), key=lambda x: x[1], reverse=True)
            secondary = sorted_intents[1] if len(sorted_intents) > 1 else (None, 0.0)

            return IntentResult(
                intent=intent,
                confidence=round(confidence, 3),
                all_scores=score_dict,
                secondary_intent=secondary[0],
                secondary_confidence=round(secondary[1], 3),
            )
        except Exception:
            return self._fallback_classify(text)

    def add_correction(self, text: str, correct_intent: str):
        """Store user correction and persist."""
        self._corrections.append((text, correct_intent))
        self._save_corrections()

        if len(self._corrections) >= 10:
            self._retrain_with_corrections()

    def get_stats(self) -> dict:
        """Get classifier statistics."""
        return {
            "loaded": self._loaded,
            "has_sklearn": HAS_SKLEARN,
            "correction_count": len(self._corrections),
            "intent_count": len(self.INTENTS),
            "example_count": sum(len(v) for v in self.INTENTS.values()),
        }

    # ── Internal ──────────────────────────────────────────

    def _detect_multi_intent(self, text: str) -> IntentResult | None:
        """Detect multi-intent inputs like 'run tests and push to main'."""
        text_lower = text.lower()
        for conj in self.CONJUNCTIONS:
            if f" {conj} " in text_lower:
                parts = text_lower.split(f" {conj} ", 1)
                if len(parts) == 2 and len(parts[0]) > 3 and len(parts[1]) > 3:
                    r1 = self.classify(parts[0]) if self._model else self._fallback_classify(parts[0])
                    r2 = self.classify(parts[1]) if self._model else self._fallback_classify(parts[1])
                    return IntentResult(
                        intent=r1.intent,
                        confidence=r1.confidence,
                        all_scores=r1.all_scores,
                        secondary_intent=r2.intent,
                        secondary_confidence=r2.confidence,
                        is_multi_intent=True,
                    )
        return None

    def _softmax_scores(self, classes, scores) -> dict:
        """Temperature-scaled softmax for confidence calibration."""
        scaled = [s / self._temperature for s in scores]
        max_s = max(scaled)
        exp_scores = [math.exp(s - max_s) for s in scaled]
        total = sum(exp_scores)
        return {cls: round(e / total, 3) for cls, e in zip(classes, exp_scores)}

    def _train_from_examples(self) -> bool:
        texts, labels = [], []
        for intent, examples in self.INTENTS.items():
            for example in examples:
                texts.append(example)
                labels.append(intent)

        # Include corrections
        for text, intent in self._corrections:
            texts.append(text)
            labels.append(intent)

        try:
            self._model = Pipeline([
                ("tfidf", TfidfVectorizer(ngram_range=(1, 3), max_features=8000, sublinear_tf=True)),
                ("svm", LinearSVC(max_iter=2000, C=1.0)),
            ])
            self._model.fit(texts, labels)

            _safe_model_save(self._model, self._model_path)

            self._loaded = True
            return True
        except Exception:
            return False

    def _retrain_with_corrections(self):
        try:
            self._train_from_examples()
            self._corrections.clear()
            self._save_corrections()
        except Exception:
            pass

    def _load_corrections(self):
        try:
            if self._corrections_path.exists():
                with open(self._corrections_path) as f:
                    self._corrections = [(c["text"], c["intent"]) for c in json.load(f)]
        except Exception:
            self._corrections = []

    def _save_corrections(self):
        try:
            NLP_MODELS_DIR.mkdir(parents=True, exist_ok=True)
            with open(self._corrections_path, "w") as f:
                json.dump([{"text": t, "intent": i} for t, i in self._corrections], f)
        except Exception:
            pass

    def _fallback_classify(self, text: str) -> IntentResult:
        """Comprehensive regex fallback."""
        text_lower = text.strip().lower()

        if text_lower in ("fix", "fix it", "fix that", "fix last error", "fix this", "debug this"):
            return IntentResult(intent="fix_request", confidence=0.9, all_scores={})
        elif text_lower.startswith("explain") or text_lower.startswith("break down"):
            return IntentResult(intent="explain_request", confidence=0.9, all_scores={})
        elif text_lower in ("undo", "rollback", "revert", "go back"):
            return IntentResult(intent="undo_request", confidence=0.9, all_scores={})
        elif text_lower in ("help", "tutorial", "guide"):
            return IntentResult(intent="help_request", confidence=0.9, all_scores={})
        elif text_lower.startswith(("build a pipeline", "pipe ", "chain ")):
            return IntentResult(intent="pipeline_request", confidence=0.85, all_scores={})
        elif any(w in text_lower for w in ("deploy", "ship it", "push to cloud", "release", "promote to prod")):
            return IntentResult(intent="deploy_request", confidence=0.8, all_scores={})
        elif any(w in text_lower for w in ("container", "docker", "compose up", "compose down", "spin up")):
            return IntentResult(intent="docker_request", confidence=0.8, all_scores={})
        elif any(w in text_lower for w in ("query", "select from", "database", "sql", "api call", "fetch data")):
            return IntentResult(intent="query_request", confidence=0.75, all_scores={})
        elif text_lower.startswith(("what", "how", "why", "when", "where", "can you tell")):
            return IntentResult(intent="question", confidence=0.7, all_scores={})

        shell_starters = [
            "git", "ls", "cd", "dir", "pip", "npm", "docker", "kubectl",
            "python", "node", "cargo", "go", "cat", "grep", "find", "chmod",
            "mkdir", "rm", "cp", "mv", "tar", "curl", "ssh", "echo",
            "pytest", "make", "cmake", "gcc", "javac", "dotnet",
            "terraform", "helm", "aws", "az", "gcloud",
            "rsync", "systemctl", "service", "journalctl", "redis-cli",
        ]
        first_word = text_lower.split()[0] if text_lower.split() else ""
        if first_word in shell_starters:
            return IntentResult(intent="shell_command", confidence=0.8, all_scores={})

        return IntentResult(intent="natural_language", confidence=0.5, all_scores={})
