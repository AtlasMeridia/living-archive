"""Tests for auth.py: OAuth token resolution and client caching."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.auth import resolve_token, get_client, _read_hermes_env


class TestResolveToken:
    """Token resolution priority: ANTHROPIC_API_KEY > CLAUDE_CODE_OAUTH_TOKEN > hermes .env."""

    def test_prefers_api_key(self, monkeypatch):
        """ANTHROPIC_API_KEY takes priority."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")
        token, source = resolve_token()
        assert token == "sk-ant-test123"
        assert source == "ANTHROPIC_API_KEY"

    def test_falls_back_to_oauth_env(self, monkeypatch):
        """CLAUDE_CODE_OAUTH_TOKEN used when no API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token-abc")
        token, source = resolve_token()
        assert token == "oauth-token-abc"
        assert source == "CLAUDE_CODE_OAUTH_TOKEN"

    def test_falls_back_to_hermes_env(self, monkeypatch, tmp_path):
        """Reads from ~/.hermes/.env when env vars are empty."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        hermes_env = tmp_path / ".env"
        hermes_env.write_text('# comment\nCLAUDE_CODE_OAUTH_TOKEN=hermes-oauth-xyz\n')

        with patch("src.auth._HERMES_ENV", hermes_env):
            token, source = resolve_token()
        assert token == "hermes-oauth-xyz"
        assert "hermes:" in source

    def test_raises_when_nothing_found(self, monkeypatch, tmp_path):
        """ValueError when no credential is available."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        hermes_env = tmp_path / ".env"
        hermes_env.write_text("# nothing useful\n")

        # Patch _HERMES_HOME too so the real ~/.hermes/profiles/*/.env
        # files on a dev machine can't satisfy the lookup.
        with patch("src.auth._HERMES_HOME", tmp_path), \
             patch("src.auth._HERMES_ENV", hermes_env):
            with pytest.raises(ValueError, match="No Anthropic credential"):
                resolve_token()


class TestReadHermesEnv:
    """Low-level .env parser. Returns (value, source_path) tuples."""

    def test_reads_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('FOO=bar\nCLAUDE_CODE_OAUTH_TOKEN=mytoken\nBAZ=qux\n')
        with patch("src.auth._HERMES_ENV", env_file):
            assert _read_hermes_env("CLAUDE_CODE_OAUTH_TOKEN") == ("mytoken", str(env_file))
            assert _read_hermes_env("FOO") == ("bar", str(env_file))
            assert _read_hermes_env("MISSING") == ("", "")

    def test_strips_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('TOKEN="quoted-value"\n')
        with patch("src.auth._HERMES_ENV", env_file):
            assert _read_hermes_env("TOKEN") == ("quoted-value", str(env_file))

    def test_skips_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('# CLAUDE_CODE_OAUTH_TOKEN=fake\nCLAUDE_CODE_OAUTH_TOKEN=real\n')
        with patch("src.auth._HERMES_ENV", env_file):
            assert _read_hermes_env("CLAUDE_CODE_OAUTH_TOKEN") == ("real", str(env_file))

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent"
        with patch("src.auth._HERMES_ENV", missing):
            assert _read_hermes_env("ANYTHING") == ("", "")


class TestGetClient:
    """Client creation and caching."""

    def test_creates_anthropic_client(self, monkeypatch):
        """get_client() returns a valid Anthropic client."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        # Reset module cache
        import src.auth
        src.auth._client = None

        client = get_client()
        assert client is not None

        # Second call returns same instance (cached)
        client2 = get_client()
        assert client is client2

        # Clean up
        src.auth._client = None

    def test_raises_without_credentials(self, monkeypatch, tmp_path):
        """get_client() raises when no credentials are available."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        import src.auth
        src.auth._client = None

        hermes_env = tmp_path / ".env"
        hermes_env.write_text("")

        with patch("src.auth._HERMES_HOME", tmp_path), \
             patch("src.auth._HERMES_ENV", hermes_env):
            with pytest.raises(ValueError):
                get_client()

        # Clean up
        src.auth._client = None
