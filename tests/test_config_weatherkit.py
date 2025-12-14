import logging

import config


def test_weatherkit_private_key_literal_newlines(monkeypatch, caplog):
    monkeypatch.delenv("WEATHERKIT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setenv(
        "WEATHERKIT_PRIVATE_KEY",
        "-----BEGIN PRIVATE KEY-----\\nABCDEF\\n-----END PRIVATE KEY-----",
    )

    caplog.set_level(logging.WARNING)
    key = config._load_weatherkit_private_key()

    assert "\n" in key
    assert "\\n" not in key
    assert "literal \\n; converting to newlines" in " ".join(caplog.messages)


def test_weatherkit_private_key_path_misplaced(monkeypatch, caplog):
    monkeypatch.delenv("WEATHERKIT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setenv("WEATHERKIT_PRIVATE_KEY", "/home/pi/AuthKey.p8")

    caplog.set_level(logging.WARNING)
    key = config._load_weatherkit_private_key()

    assert key == "/home/pi/AuthKey.p8"
    assert "looks like a path; set WEATHERKIT_PRIVATE_KEY_PATH" in " ".join(
        caplog.messages
    )
