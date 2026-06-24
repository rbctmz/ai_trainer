"""Welcome page renderer for unauthenticated users."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st
from services import acceptance_mode as acceptance_mode_service, demo_mode as demo_mode_service

if TYPE_CHECKING:
    from state import StateManager


@dataclass(frozen=True)
class WelcomeGarminMode:
    """Pure description of how the welcome page should present the Garmin path.

    Decoupled from Streamlit so the gating contract can be unit-tested without
    rendering. The boolean flags map directly to which blocks render.

    ``show_real_garmin_path`` is True whenever the user can actually attempt a
    real Garmin login: outside acceptance mode, or inside acceptance mode when
    the runner has explicitly allowed login (ACCEPTANCE_DISABLE_GARMIN=0).
    ``show_demo_only_acceptance_block`` is the inverse for the acceptance block
    that previously (incorrectly) hid the real path behind "login is disabled".
    """

    is_acceptance_mode: bool
    garmin_login_allowed: bool
    show_real_garmin_path: bool
    show_demo_only_acceptance_block: bool
    garmin_status_text: str


def resolve_welcome_garmin_mode() -> WelcomeGarminMode:
    """Decide which Garmin onboarding surface the welcome page should render.

    The old code gated the real Garmin path on ``acceptance_enabled`` alone, so
    an acceptance run with ``ACCEPTANCE_DISABLE_GARMIN=0`` still hid the real
    path and falsely claimed login was disabled. This resolver derives the
    visible behaviour from the actual ``garmin_disabled()`` contract instead.
    """
    is_acceptance = acceptance_mode_service.is_acceptance_mode()
    login_allowed = not acceptance_mode_service.garmin_disabled()

    show_real = login_allowed  # real path shown whenever a real login can run

    if is_acceptance and not login_allowed:
        status = "Реальный Garmin login отключён в этом acceptance runtime."
    elif is_acceptance:
        status = "Acceptance runtime: реальный Garmin login разрешён — используйте свои данные аккуратно."
    else:
        status = "Подключите аккаунт Garmin, чтобы работать со своими данными."

    return WelcomeGarminMode(
        is_acceptance_mode=is_acceptance,
        garmin_login_allowed=login_allowed,
        show_real_garmin_path=show_real,
        show_demo_only_acceptance_block=not show_real,
        garmin_status_text=status,
    )


def render_welcome_page(state: "StateManager") -> None:
    """Экран приветствия для неподключённых пользователей."""
    stats = state.database.get_database_stats()
    has_local_cache = any(stats.values())
    acceptance_info = acceptance_mode_service.runtime_info(state)
    acceptance_enabled = acceptance_info.get("enabled", False)
    garmin_mode = resolve_welcome_garmin_mode()

    st.markdown("## Добро пожаловать в персональный AI тренер!")
    st.markdown("Выберите, как хотите войти в продукт: с реальными данными Garmin или на временном демо-наборе.")

    if acceptance_enabled:
        st.info(
            "🧪 Acceptance mode активен: этот запуск использует изолированную временную БД и предназначен "
            f"для безопасного browser clickthrough. {garmin_mode.garmin_status_text}"
        )

    feature_col, path_col = st.columns([1, 2])

    with feature_col:
        st.markdown("### Что вы получите")
        st.markdown("- 📊 Анализ тренировочной нагрузки")
        st.markdown("- 💓 HRV и восстановление")
        st.markdown("- 😴 Качество сна")
        st.markdown("- 📈 Планирование тренировок")
        st.markdown("- 🤖 Следующие шаги от AI коуча")

    with path_col:
        garmin_col, demo_col = st.columns(2)

        with garmin_col:
            st.markdown("### 🔗 Garmin Connect")
            if garmin_mode.show_demo_only_acceptance_block:
                st.markdown("Acceptance instance отключает реальный Garmin path.")
                st.markdown("1. Используйте изолированный demo dataset")
                st.markdown("2. Прогоняйте dashboard, planning и exports")
                st.markdown("3. При необходимости переинициализируйте dataset из sidebar")
                st.caption("Этот запуск нужен для безопасной регрессии, а не для работы с реальным аккаунтом.")
            else:
                st.markdown("Для реального сценария:")
                st.markdown("1. Введите email и пароль Garmin в боковой панели")
                st.markdown("2. Подключитесь и синхронизируйте последние 30 дней")
                st.markdown("3. Откройте dashboard и AI coaching на своих данных")
                if garmin_mode.is_acceptance_mode:
                    st.caption("Acceptance runtime, но реальный login разрешён — основная локальная БД не затрагивается.")
                else:
                    st.caption("Подходит, если вы хотите сразу работать со своей историей тренировок.")

        with demo_col:
            st.markdown("### 🎮 Демо-режим" if not acceptance_enabled else "### 🧪 Acceptance dataset")
            if acceptance_enabled:
                st.markdown("Для стандартного acceptance checkpoint:")
                st.markdown("1. Сбросится только изолированная acceptance БД")
                st.markdown("2. Сразу откроется dashboard с planning и AI coaching")
                st.markdown("3. Можно безопасно прогонять реальный browser clickthrough")
                st.caption("Основная локальная БД не затрагивается, потому что acceptance runtime уже изолирован.")
            else:
                st.markdown("Для быстрого знакомства:")
                st.markdown("1. Загрузится временный локальный набор sample data")
                st.markdown("2. Сразу откроется dashboard с метриками, сном и планированием")
                st.markdown("3. AI coaching будет доступен без подключения Garmin")
                st.caption("Демо-режим очищает локальный кэш и не смешивается с реальными данными.")

            if has_local_cache and not acceptance_enabled:
                st.warning("Запуск демо-режима заменит текущий локальный кэш данных на временный sample dataset.")

            if st.button(
                "🎮 Запустить демо-режим" if not acceptance_enabled else "🧪 Восстановить acceptance dataset",
                type="primary",
                width="stretch",
                key="start_demo_mode_btn",
            ):
                if acceptance_enabled:
                    result = acceptance_mode_service.reset_acceptance_dataset(state)
                else:
                    result = demo_mode_service.activate_demo_mode(state)
                st.success(
                    ("✅ Демо-режим активирован: " if not acceptance_enabled else "✅ Acceptance dataset готов: ")
                    +
                    f"{result['activities']} активностей, {result['hrv_days']} дней HRV, "
                    f"{result['sleep_days']} дней сна."
                )
                st.rerun()

    st.markdown("---")
    if acceptance_enabled:
        st.caption("Acceptance mode запускается на отдельной временной БД и нужен для безопасной регрессии UI/product flow.")
    else:
        st.caption("Garmin onboarding требует аккаунт Garmin Connect. Демо-режим использует временные локальные данные и подходит для первого знакомства с интерфейсом.")
