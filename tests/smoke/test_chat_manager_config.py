from __future__ import annotations

import pytest

from config.settings import Settings
from models.chat_manager import ChatManager


pytestmark = pytest.mark.smoke


def test_chat_manager_defaults_to_configured_chats_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    chats_dir = tmp_path / "isolated-chats"
    monkeypatch.setattr(Settings, "CHATS_DIR", str(chats_dir))

    manager = ChatManager()

    assert manager.chats_dir == str(chats_dir)
    assert chats_dir.exists()
