import subprocess
import sys

import pytest

from curate import dev


@pytest.mark.parametrize("command", ["relay-login", "relay"])
def test_relay_cli_receives_secrets_without_arguments(settings, monkeypatch, command):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(dev, "Settings", lambda: settings)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["curate.dev", command])
    monkeypatch.setenv("OPENAI_API_KEY", "private-openai-key")
    with pytest.raises(SystemExit) as result:
        dev.main()
    assert result.value.code == 0
    args, kwargs = calls[0]
    assert "test-relay" not in args
    assert kwargs["env"]["RELAY_AGENT_TOKEN"] == "test-relay"
    assert "OPENAI_API_KEY" not in kwargs["env"]
    assert args[:3] == ["npx", "--yes", "relaymessenger@0.1.22"]
    assert "curate" in args
    if command == "relay-login":
        assert args[-3:] == ["auth", "login", "--with-token"]
        assert kwargs["input"] == "test-relay\n"
    else:
        assert args[-3:] == ["listen", "--forward-to", "http://127.0.0.1:8000/webhooks/relay"]
