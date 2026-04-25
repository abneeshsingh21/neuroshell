"""
test_config.py — Unit tests for config.py

Covers:
- os.getlogin() crash fix (_get_machine_identity safe fallback)
- Fernet encrypt/decrypt round-trip
- XOR → Fernet auto-migration
- set_secret / get_secret persistence
- HAS_FERNET flag
"""
import json
import base64
import pytest


# ─── Machine Identity ────────────────────────────────────────

class TestGetMachineIdentity:
    def test_returns_string(self):
        from config import _get_machine_identity
        result = _get_machine_identity()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_contains_colon_separators(self):
        from config import _get_machine_identity
        result = _get_machine_identity()
        parts = result.split(":")
        assert len(parts) >= 3, f"Expected node:user:system format, got: {result!r}"

    def test_survives_getlogin_oserror(self, monkeypatch):
        """Simulates Docker/WSL/CI where os.getlogin() raises OSError."""
        import os
        monkeypatch.setattr(os, "getlogin", lambda: (_ for _ in ()).throw(OSError("no tty")))
        from config import _get_machine_identity
        result = _get_machine_identity()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_survives_missing_env_vars(self, monkeypatch):
        """Falls back to literal 'user' when all env vars are absent."""
        import os
        monkeypatch.setattr(os, "getlogin", lambda: (_ for _ in ()).throw(OSError("no tty")))
        monkeypatch.delenv("USERNAME", raising=False)
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.delenv("LOGNAME", raising=False)
        from config import _get_machine_identity
        result = _get_machine_identity()
        assert "user" in result


# ─── Fernet Encryption ───────────────────────────────────────

class TestFernetEncryption:
    def test_has_fernet_true_after_install(self):
        from config import HAS_FERNET
        assert HAS_FERNET is True, (
            "cryptography package must be installed. Run: pip install cryptography"
        )

    def test_round_trip(self):
        from config import _fernet_encrypt, _fernet_decrypt, HAS_FERNET
        if not HAS_FERNET:
            pytest.skip("cryptography not installed")
        plaintext = b"super-secret-api-key-12345"
        token = _fernet_encrypt(plaintext)
        assert token != plaintext
        recovered = _fernet_decrypt(token)
        assert recovered == plaintext

    def test_different_plaintexts_produce_different_tokens(self):
        from config import _fernet_encrypt, HAS_FERNET
        if not HAS_FERNET:
            pytest.skip("cryptography not installed")
        t1 = _fernet_encrypt(b"secret-A")
        t2 = _fernet_encrypt(b"secret-B")
        assert t1 != t2

    def test_tampered_token_raises(self):
        from config import _fernet_encrypt, _fernet_decrypt, HAS_FERNET
        from cryptography.fernet import InvalidToken
        if not HAS_FERNET:
            pytest.skip("cryptography not installed")
        token = _fernet_encrypt(b"my-secret")
        # Flip a byte in the middle of the ciphertext
        tampered = bytearray(token)
        tampered[40] ^= 0xFF
        with pytest.raises(Exception):  # InvalidToken or similar
            _fernet_decrypt(bytes(tampered))


# ─── Secret Persistence ──────────────────────────────────────

class TestSecretPersistence:
    def test_set_and_get_secret(self, tmp_secrets_file):
        from config import Config
        cfg = Config.load()
        cfg.set_secret("TEST_KEY", "hello-world")
        assert cfg.get_secret("TEST_KEY") == "hello-world"

    def test_secrets_written_to_disk(self, tmp_secrets_file):
        from config import Config
        cfg = Config.load()
        cfg.set_secret("DISK_KEY", "disk-value")
        assert tmp_secrets_file.exists(), "Secrets file was not created on disk"

    def test_secrets_file_is_encrypted(self, tmp_secrets_file):
        from config import Config
        cfg = Config.load()
        cfg.set_secret("PRIVATE", "plaintext-forbidden")
        raw = tmp_secrets_file.read_text(encoding="utf-8")
        assert "plaintext-forbidden" not in raw, "Secret stored in plaintext!"
        envelope = json.loads(raw)
        # Must be versioned Fernet or legacy XOR — never plaintext value
        assert "data" in envelope

    def test_secrets_survive_reload(self, tmp_secrets_file):
        from config import Config
        cfg1 = Config.load()
        cfg1.set_secret("RELOAD_KEY", "persist-me")
        # Simulate a fresh load
        cfg2 = Config.load()
        assert cfg2.get_secret("RELOAD_KEY") == "persist-me"

    def test_xor_to_fernet_migration(self, tmp_secrets_file):
        """Write a v1 XOR envelope then reload — should auto-migrate to Fernet v2."""
        from config import _derive_machine_key, _xor_crypt, HAS_FERNET
        if not HAS_FERNET:
            pytest.skip("cryptography not installed — migration won't happen")
        secrets_data = {"MIGRATED_KEY": "migrated-value"}
        plaintext = json.dumps(secrets_data).encode("utf-8")
        key = _derive_machine_key()
        encrypted = _xor_crypt(plaintext, key)
        envelope = {
            "_encrypted": True,
            "data": base64.b64encode(encrypted).decode("ascii"),
        }
        tmp_secrets_file.write_text(json.dumps(envelope), encoding="utf-8")

        from config import Config
        cfg = Config.load()
        assert cfg.get_secret("MIGRATED_KEY") == "migrated-value"

        # File should now be v2 Fernet
        new_envelope = json.loads(tmp_secrets_file.read_text(encoding="utf-8"))
        assert new_envelope.get("_enc_version") == 2, "Not migrated to Fernet v2!"
