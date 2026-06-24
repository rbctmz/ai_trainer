"""Chat-shell helpers for the AI coaching page."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import pandas as pd
import streamlit as st

from services import demo_mode as demo_mode_service
from state import StateManager
from ui.components.ai_coach_entry import (
    _normalize_ai_coach_handoff,
    render_dashboard_handoff,
    render_empty_ai_chat_guidance,
)


CHAT_PAGE_STYLES = """
    <style>
    .main > div {
        max-width: 1200px;
        padding: 0 2rem;
    }

    .chat-container {
        max-width: 800px;
        margin: 0 auto;
    }

    .stChatMessage {
        max-width: 800px !important;
    }

    .stChatMessage > div {
        max-width: 100% !important;
    }

    .stChatMessage [data-testid="stMarkdownContainer"] {
        max-width: 100% !important;
    }

    .chat-input-fixed {
        position: sticky;
        bottom: 0;
        background: var(--ic-surface-raised, white);
        padding: 15px 0;
        border-top: 1px solid var(--ic-hairline, #ddd);
        z-index: 999;
        max-width: 800px;
        margin: 0 auto;
    }

    .quick-buttons {
        margin-bottom: 10px;
        max-width: 800px;
        margin: 0 auto 10px auto;
    }

    .sidebar-chat-list {
        max-height: 400px;
        overflow-y: auto;
    }

    .chat-title {
        font-size: 0.9rem;
        font-weight: 500;
        margin-bottom: 2px;
    }

    .chat-meta {
        font-size: 0.75rem;
        color: var(--ic-muted, #666);
        margin: 0;
    }

    [data-testid="stChatMessage"][data-testid*="assistant"] {
        background-color: var(--ic-surface, #f8f9fa);
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }

    [data-testid="stChatMessage"][data-testid*="user"] {
        background-color: var(--ic-surface-raised, #e3f2fd);
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    </style>
"""


def chat_page_styles(dark_mode: bool = False) -> str:
    """Return chat page CSS tuned for the active theme.

    In dark mode the assistant/user bubbles need a slightly raised surface
    (var(--ic-surface-raised)) rather than the fixed light grays, otherwise
    they blend into the dark app background.
    """
    if dark_mode:
        return CHAT_PAGE_STYLES.replace(
            "background-color: var(--ic-surface, #f8f9fa);",
            "background-color: var(--ic-surface);",
        ).replace(
            "background-color: var(--ic-surface-raised, #e3f2fd);",
            "background-color: var(--ic-surface-raised);",
        )
    # light: keep the legacy pastel tints for the user bubble for visual continuity
    return CHAT_PAGE_STYLES.replace(
        "background-color: var(--ic-surface-raised, #e3f2fd);",
        "background-color: #e3f2fd;",
    ).replace(
        "background-color: var(--ic-surface, #f8f9fa);",
        "background-color: #f8f9fa;",
    )


def _build_quick_question_prompts() -> tuple[dict[str, str], ...]:
    return (
        {
            "label": "💪 Форма",
            "key": "form_q",
            "help": "Как моя текущая форма?",
            "prompt": "Проанализируй мою текущую форму (TSB, CTL, ATL) и состояние восстановления (HRV). Дай четкую оценку готовности к нагрузкам.",
        },
        {
            "label": "📅 План",
            "key": "plan_q",
            "help": "План на неделю",
            "prompt": "На основе моего текущего состояния (TSB, HRV, недавние тренировки) составь конкретный план тренировок на следующую неделю. ОБЯЗАТЕЛЬНО дай четкий план по дням с видами тренировок и интенсивностью.",
        },
        {
            "label": "📊 Прогресс",
            "key": "progress_q",
            "help": "Анализ прогресса",
            "prompt": "Покажи мой прогресс за месяц: тренды нагрузки, лучшие результаты, изменение формы. ОБЯЗАТЕЛЬНО дай конкретные выводы.",
        },
        {
            "label": "💓 HRV",
            "key": "hrv_q",
            "help": "Анализ восстановления",
            "prompt": "Проанализируй мое состояние восстановления: HRV тренды, нагрузка за неделю, качество сна. ОБЯЗАТЕЛЬНО дай рекомендации по тренировкам.",
        },
    )


def ensure_ai_chat_session_state(state: StateManager, database: Any) -> None:
    """Ensure the chat page has its transient state initialized."""
    if "ai_tools" not in state:
        from models.ai_tools import AITools

        state.ai_tools = AITools(database)

    if "data_context" not in state:
        state.data_context = None
        state.context_loaded = False

    if "current_chat_id" not in state:
        state.current_chat_id = None

    if state.current_chat_id is None:
        if demo_mode_service.is_demo_mode(state):
            state.current_chat_id = state.chat_manager.create_new_chat(title="Демо AI коуч")
        else:
            existing_chats = state.chat_manager.get_chat_list()
            if existing_chats:
                state.current_chat_id = existing_chats[0]["id"]


def apply_ai_chat_styles(dark_mode: bool = False) -> None:
    """Apply page-local chat styling tuned for the active theme."""
    st.markdown(chat_page_styles(dark_mode), unsafe_allow_html=True)


def render_ai_chat_sidebar(
    state: StateManager,
    database: Any,
    build_system_prompt: Callable[[Optional[Dict[str, Any]]], str],
) -> int:
    """Render sidebar controls and diagnostics for the AI chat."""
    with st.sidebar:
        st.divider()
        st.subheader("⚙️ Настройки")

        context_days = st.selectbox(
            "📅 Период анализа",
            [30, 60, 90, 180],
            index=1,
            help="Количество дней данных для анализа AI",
        )

        if st.button("🔄 Обновить данные", help="Загрузить свежие данные"):
            with st.spinner("Загрузка данных..."):
                from models.ai_data_context import AIDataContext

                data_context = AIDataContext(database)
                state.data_context = data_context.get_full_context(context_days)
                state.context_loaded = True
                st.success("✅ Данные обновлены")

        st.divider()
        st.subheader("🔍 Диагностика данных")

        if state.context_loaded and state.data_context:
            context = state.data_context

            def fmt_health(value, fmt_mask=".1f"):
                if value is None or (hasattr(pd, "isna") and pd.isna(value)):
                    return "н/д"
                return format(float(value), fmt_mask)

            summary = context["summary"]

            st.success(f"✅ Данные загружены: {context_days} дней")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Тренировок", summary.get("total_activities", 0))
            with col2:
                st.metric("HRV записей", summary.get("hrv_data_points", 0))
            with col3:
                st.metric("Общий TSS", f"{summary.get('total_tss', 0):.0f}")

            st.write("**Доступные модули данных:**")
            data_modules = []

            if context.get("activities", {}).get("has_data", False):
                data_modules.append("✅ Активности")
            else:
                data_modules.append("❌ Активности")

            if context.get("hrv", {}).get("has_data", False):
                data_modules.append("✅ HRV данные")
            else:
                data_modules.append("❌ HRV данные")

            if context.get("performance_metrics", {}).get("has_data", False):
                data_modules.append("✅ Метрики (Banister)")
            else:
                data_modules.append("❌ Метрики (Banister)")

            if context.get("sleep", {}).get("has_data", False):
                data_modules.append("✅ Данные сна")
            else:
                data_modules.append("❌ Данные сна")

            if context.get("daily_health", {}).get("has_data", False):
                data_modules.append("✅ Ежедневное здоровье")
            else:
                data_modules.append("❌ Ежедневное здоровье")

            if context.get("training_status", {}).get("has_data", False):
                data_modules.append("✅ Garmin Training Status")
            else:
                data_modules.append("❌ Garmin Training Status")

            if context.get("user_profile", {}).get("has_data", False):
                data_modules.append("✅ Профиль пользователя")
            else:
                data_modules.append("❌ Профиль пользователя")

            st.write(" • ".join(data_modules))

            if context.get("activities", {}).get("recent_activities"):
                with st.expander("🏃 Последние активности"):
                    recent = context["activities"]["recent_activities"][:5]
                    for activity in recent:
                        st.write(
                            f"• {activity.get('date', 'N/A')} - {activity.get('sport', 'N/A')} "
                            f"({activity.get('duration_minutes', 0)} мин, TSS: {activity.get('tss', 0)})"
                        )

            if context.get("performance_metrics", {}).get("has_data", False):
                with st.expander("📊 Текущие метрики"):
                    pm = context["performance_metrics"]["banister_model"]
                    st.write(f"• CTL: {pm.get('ctl', 0):.1f}")
                    st.write(f"• ATL: {pm.get('atl', 0):.1f}")
                    st.write(f"• TSB: {pm.get('tsb', 0):.1f}")

            if context.get("daily_health", {}).get("has_data", False):
                with st.expander("🏥 Ежедневное здоровье"):
                    dh_stats = context["daily_health"]["stats"]
                    st.write(f"• Шаги (средние): {fmt_health(dh_stats.get('avg_steps'), '.0f')}")
                    st.write(f"• ЧСС покоя: {fmt_health(dh_stats.get('avg_resting_hr'))}")
                    st.write(f"• Активные минуты: {fmt_health(dh_stats.get('avg_active_minutes'))}")
                    st.write(f"• Тренд шагов: {context['daily_health']['trend_steps'] or 'н/д'}")

            if context.get("training_status", {}).get("has_data", False):
                with st.expander("🎯 Garmin Training Status"):
                    latest = context["training_status"]["latest"]
                    summary = context["training_status"]["summary"]
                    st.write(f"• Последний статус: {latest.get('training_status', 'н/д')}")
                    readiness_avg = summary.get("avg_training_readiness")
                    st.write(
                        f"• Readiness (среднее): {fmt_health(readiness_avg)}/100"
                        if readiness_avg is not None
                        else "• Readiness: данных нет"
                    )
                    load_avg = summary.get("avg_training_load_7d")
                    st.write(
                        f"• Нагрузка 7д (средняя): {fmt_health(load_avg)}"
                        if load_avg is not None
                        else "• Нагрузка 7д: данных нет"
                    )
                    vo2_avg = summary.get("avg_vo2_max")
                    st.write(
                        f"• VO₂max (средний): {fmt_health(vo2_avg)}"
                        if vo2_avg is not None
                        else "• VO₂max: данных нет"
                    )

            if context.get("hrv", {}).get("has_data", False):
                with st.expander("💓 HRV состояние"):
                    hrv_stats = context["hrv"]["stats"]
                    st.write(f"• Текущий RMSSD: {hrv_stats.get('current_rmssd', 0):.1f} мс")
                    st.write(f"• Состояние: {hrv_stats.get('recovery_state', 'unknown')}")

            if context.get("sleep", {}).get("has_data", False):
                with st.expander("😴 Состояние сна"):
                    sleep_stats = context["sleep"]["stats"]
                    st.write(f"• Среднее время сна: {sleep_stats.get('avg_total_sleep_hours', 0):.1f} ч/ночь")
                    st.write(f"• Оценка сна: {sleep_stats.get('avg_sleep_score', 0):.1f}/100")
                    st.write(f"• Качество: {context['sleep'].get('sleep_quality', 'unknown')}")
                    st.write(f"• Данных: {context['sleep'].get('data_points', 0)} записей")

        else:
            st.warning("⚠️ Данные не загружены - нажмите '🔄 Обновить данные'")
            st.info("🤖 **AI имеет доступ ко ВСЕМ данным из Garmin Connect:**")
            st.markdown(
                """
            **Данные активностей:**
            • Тренировки (дата, спорт, длительность, расстояние)
            • Пульс (средний, максимальный, зоны)
            • Мощность и TSS (Training Stress Score)
            • Набор высоты и темп
            • Анализ по видам спорта

            **HRV (вариабельность сердечного ритма):**
            • RMSSD (основной показатель)
            • Стресс-индекс и уровень восстановления
            • Тренды и динамика
            • Корреляция с тренировочной нагрузкой

            **Данные сна:**
            • Общее время сна и эффективность сна
            • Фазы сна (глубокий, легкий, REM)
            • Оценка качества сна (Garmin Sleep Score)
            • Время засыпания и пробуждения
            • Количество пробуждений за ночь
            • Анализ паттернов и трендов сна

            **Ежедневное здоровье:**
            • Шаги и активные калории
            • ЧСС в покое и интенсивные минуты
            • Тренды активности по дням

            **Garmin Training Status:**
            • Readiness, тренированность и VO₂max
            • Недельная нагрузка и ACWR
            • История статусов Garmin

            **Модель Банистера:**
            • CTL (хроническая тренировочная нагрузка)
            • ATL (острая тренировочная нагрузка)
            • TSB (баланс стресса тренировки)
            • Прогноз формы и рекомендации

            **Аналитика:**
            • Недельные и месячные тренды
            • Распределение интенсивности
            • Паттерны тренировок
            • Профиль спортсмена и уровень подготовки
            """
            )

            if st.button("🔬 Показать полный контекст для AI"):
                with st.expander("📋 Системный промпт AI", expanded=True):
                    system_prompt = build_system_prompt(state.data_context)
                    st.code(system_prompt, language="markdown")

                with st.expander("🗄️ Полный контекст данных"):
                    from models.ai_data_context import AIDataContext

                    context_formatter = AIDataContext(None)
                    formatted_context = context_formatter.format_context_for_ai(state.data_context)
                    st.code(formatted_context, language="markdown")

        chats = state.chat_manager.get_chat_list()
        if chats:
            stats = state.chat_manager.get_stats()
            st.divider()
            st.subheader("📊 Статистика")
            col1, col2 = st.columns(2)
            col1.metric("Чатов", stats["total_chats"])
            col2.metric("Сообщений", stats["total_messages"])

    return context_days


def ensure_ai_chat_context_loaded(
    state: StateManager,
    database: Any,
    context_days: int,
) -> None:
    """Load AI data context on first entry if it is not already cached."""
    if state.context_loaded:
        return

    with st.spinner("Загрузка данных для AI..."):
        from models.ai_data_context import AIDataContext

        data_context = AIDataContext(database)
        state.data_context = data_context.get_full_context(context_days)
        state.context_loaded = True


def render_ai_chat_conversation(
    state: StateManager,
    on_prompt_selected: Callable[[str], None],
) -> None:
    """Render the chat history or the first-run guidance."""
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        st.caption(f"ID текущего чата: {state.current_chat_id or '—'}")

        dashboard_handoff = _normalize_ai_coach_handoff(
            getattr(state, "ai_coach_handoff", None)
        )
        if dashboard_handoff is not None:
            render_dashboard_handoff(
                state,
                dashboard_handoff,
                on_prompt_selected,
            )

        current_messages = []
        if state.current_chat_id:
            current_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
        st.caption(f"Сообщений в чате: {len(current_messages)}")

        if current_messages:
            for message in current_messages:
                if message["role"] == "user":
                    with st.chat_message("user"):
                        st.write(message["content"])
                else:
                    with st.chat_message("assistant"):
                        st.markdown(message["content"])
        else:
            render_empty_ai_chat_guidance(
                state,
                dashboard_handoff,
                on_prompt_selected,
            )

        st.markdown("</div>", unsafe_allow_html=True)


def render_ai_chat_input_bar(
    on_prompt_selected: Callable[[str], None],
) -> None:
    """Render the quick prompts and free-form chat input."""
    st.markdown('<div class="chat-input-fixed">', unsafe_allow_html=True)

    st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
    st.markdown("**⚡ Быстрые вопросы:**")

    top_columns = st.columns(2)
    bottom_columns = st.columns(2)
    for column, prompt in zip([*top_columns, *bottom_columns], _build_quick_question_prompts()):
        with column:
            if st.button(
                prompt["label"],
                key=prompt["key"],
                help=prompt["help"],
            ):
                on_prompt_selected(prompt["prompt"])

    st.markdown("</div>", unsafe_allow_html=True)

    user_input = st.chat_input("Задайте вопрос AI тренеру...")
    if user_input:
        on_prompt_selected(user_input)

    st.markdown("</div>", unsafe_allow_html=True)


__all__ = [
    "_build_quick_question_prompts",
    "CHAT_PAGE_STYLES",
    "apply_ai_chat_styles",
    "ensure_ai_chat_context_loaded",
    "ensure_ai_chat_session_state",
    "render_ai_chat_conversation",
    "render_ai_chat_input_bar",
    "render_ai_chat_sidebar",
]
