"""
test_nlp.py — Unit tests for nlp/intent_classifier.py

Covers:
- _safe_model_save writes a .sha256 sidecar
- _safe_model_load rejects tampered model files
- _safe_model_load accepts valid model files
- IntentClassifier fallback classify (no sklearn needed)
"""
import warnings
import pytest
from pathlib import Path


class TestSafeModelPersistence:
    def test_save_creates_sha256_sidecar(self, tmp_path):
        from nlp.intent_classifier import _safe_model_save, _compute_file_hash
        model_obj = {"weights": [1.0, 2.0, 3.0]}
        model_path = tmp_path / "model.pkl"
        _safe_model_save(model_obj, model_path)
        sidecar = tmp_path / "model.sha256"
        assert sidecar.exists(), ".sha256 sidecar not created"
        assert sidecar.read_text().strip() == _compute_file_hash(model_path)

    def test_load_accepts_valid_file(self, tmp_path):
        from nlp.intent_classifier import _safe_model_save, _safe_model_load
        model_obj = {"test": True}
        model_path = tmp_path / "model.pkl"
        _safe_model_save(model_obj, model_path)
        assert _safe_model_load(model_path) == model_obj

    def test_load_rejects_tampered_file(self, tmp_path):
        from nlp.intent_classifier import _safe_model_save, _safe_model_load
        model_path = tmp_path / "model.pkl"
        _safe_model_save({"ok": True}, model_path)
        with open(model_path, "ab") as f:
            f.write(b"\x00\xFF malicious")
        assert _safe_model_load(model_path) is None, "Tampered file must return None"

    def test_load_without_sidecar_still_loads(self, tmp_path):
        from nlp.intent_classifier import _safe_model_save, _safe_model_load
        model_path = tmp_path / "model.pkl"
        _safe_model_save({"legacy": True}, model_path)
        (tmp_path / "model.sha256").unlink()
        assert _safe_model_load(model_path) is not None

    def test_load_rejects_inconsistent_version_warning_and_retrains(self, tmp_path, monkeypatch):
        import nlp.intent_classifier as ic

        model_path = tmp_path / "model.pkl"
        model_path.write_bytes(b"legacy-model")
        hash_path = tmp_path / "model.sha256"
        hash_path.write_text("legacy-sidecar", encoding="utf-8")

        InconsistentVersionWarning = type("InconsistentVersionWarning", (UserWarning,), {})

        def fake_joblib_load(_path):
            warnings.warn(
                InconsistentVersionWarning(
                    "Trying to unpickle estimator TfidfVectorizer from version 1.8.0 when using version 1.5.2."
                ),
                category=InconsistentVersionWarning,
            )
            return {"legacy": True}

        monkeypatch.setattr(ic, "HAS_JOBLIB", True)
        monkeypatch.setattr(ic, "_compute_file_hash", lambda _path: "legacy-sidecar")
        monkeypatch.setattr(ic.joblib, "load", fake_joblib_load)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert ic._safe_model_load(model_path) is None

        assert caught == []
        assert not model_path.exists()
        assert not hash_path.exists()


class TestFallbackClassifier:
    def setup_method(self):
        from nlp.intent_classifier import IntentClassifier
        self.clf = IntentClassifier()
        self.clf._model = None

    def test_fix_intent(self):
        r = self.clf._fallback_classify("fix")
        assert r.intent == "fix_request"
        assert r.confidence >= 0.8

    def test_explain_intent(self):
        assert self.clf._fallback_classify("explain git rebase").intent == "explain_request"

    def test_undo_intent(self):
        assert self.clf._fallback_classify("undo").intent == "undo_request"

    def test_question_intent(self):
        assert self.clf._fallback_classify("what does chmod 755 mean").intent == "question"

    def test_deploy_intent(self):
        assert self.clf._fallback_classify("deploy to production").intent == "deploy_request"

    def test_confidence_in_range(self):
        r = self.clf._fallback_classify("ls -la")
        assert 0.0 <= r.confidence <= 1.0
