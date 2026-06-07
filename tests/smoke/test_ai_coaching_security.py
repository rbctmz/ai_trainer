"""Security-focused smoke tests for the AI coaching settings UI."""
from ui.pages import ai_coaching


def test_hidden_api_key_input_never_prefills_secret(monkeypatch):
    captured = {}

    def fake_text_input(label, **kwargs):
        captured["label"] = label
        captured["kwargs"] = kwargs
        return ""

    captions = []

    monkeypatch.setattr(ai_coaching.st, "text_input", fake_text_input)
    monkeypatch.setattr(ai_coaching.st, "caption", captions.append)

    resolved = ai_coaching._render_hidden_api_key_input(
        "API Key:",
        "openai_api_key_override",
        "env-secret-value",
    )

    assert resolved == "env-secret-value"
    assert captured["label"] == "API Key:"
    assert captured["kwargs"]["value"] == ""
    assert captured["kwargs"]["type"] == "password"
    assert captured["kwargs"]["key"] == "openai_api_key_override"
    assert captions


def test_hidden_api_key_input_prefers_manual_override(monkeypatch):
    monkeypatch.setattr(
        ai_coaching.st,
        "text_input",
        lambda label, **kwargs: "typed-secret-value",
    )
    caption_called = False

    def fake_caption(_message):
        nonlocal caption_called
        caption_called = True

    monkeypatch.setattr(ai_coaching.st, "caption", fake_caption)

    resolved = ai_coaching._render_hidden_api_key_input(
        "API Key:",
        "openai_api_key_override",
        "env-secret-value",
    )

    assert resolved == "typed-secret-value"
    assert caption_called is False
