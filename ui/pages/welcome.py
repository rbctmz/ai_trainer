"""Welcome page renderer for unauthenticated users."""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from state import StateManager


def render_welcome_page(_state: "StateManager") -> None:
    """Экран приветствия для неподключённых пользователей."""
    st.markdown("## Добро пожаловать в персональный AI тренер!")
    st.markdown("")
    st.markdown("Этот инструмент поможет вам:")
    st.markdown("- 📊 Анализировать тренировочные данные из Garmin Connect")
    st.markdown("- 💓 Отслеживать показатели HRV и восстановления")
    st.markdown("- 📈 Планировать тренировки с помощью модели Банистера")
    st.markdown("- 🤖 Получать персонализированные рекомендации от AI")
    st.markdown("")
    st.markdown("### Для начала работы:")
    st.markdown("1. Подключитесь к Garmin Connect в боковой панели")
    st.markdown("2. Синхронизируйте ваши тренировочные данные")
    st.markdown("3. Начните анализировать и планировать тренировки!")
    st.markdown("")
    st.markdown("---")
    st.markdown("*Требуется аккаунт Garmin Connect с историей тренировок*")
