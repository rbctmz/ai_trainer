"""Sidebar chat management helpers."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from state import StateManager


def render_chat_management(state: "StateManager") -> None:
    """Render saved-chat management controls in the sidebar."""
    chat_manager = state.chat_manager

    with st.sidebar:
        st.subheader("💬 Управление чатами")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Новый чат", use_container_width=True, type="primary"):
                new_chat_id = chat_manager.create_new_chat()
                state.current_chat_id = new_chat_id
                state.switch_to_chat_tab = True
                state.selected_page = "🤖 AI Коучинг"
                st.rerun()

        with col2:
            if state.current_chat_id and st.button("🧹 Очистить", use_container_width=True):
                if chat_manager.clear_chat(state.current_chat_id):
                    st.success("Чат очищен")
                    st.rerun()

        chats = chat_manager.get_chat_list()

        if chats:
            st.markdown('<div class="sidebar-chat-list">', unsafe_allow_html=True)

            for chat in chats:
                is_current = chat["id"] == state.current_chat_id

                col1, col2 = st.columns([4, 1])

                with col1:
                    chat_title = chat["title"][:30] + ("..." if len(chat["title"]) > 30 else "")
                    button_text = f"{'🔵' if is_current else '💬'} {chat_title}"

                    if st.button(
                        button_text,
                        key=f"chat_{chat['id']}",
                        use_container_width=True,
                        help=f"Сообщений: {chat['message_count']} • {chat['updated_at'][:16].replace('T', ' ')}",
                    ):
                        state.current_chat_id = chat["id"]
                        state.selected_page = "🤖 AI Коучинг"
                        state.switch_to_chat_tab = True
                        st.success(f"Выбран чат: {chat['title'][:20]}...")
                        st.rerun()

                with col2:
                    if st.button("🗑️", key=f"delete_{chat['id']}", help="Удалить чат"):
                        if chat_manager.delete_chat(chat["id"]):
                            if state.current_chat_id == chat["id"]:
                                state.current_chat_id = None
                            st.success("Чат удален")
                            st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Пока нет сохраненных чатов")


__all__ = ["render_chat_management"]
