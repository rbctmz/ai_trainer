"""AI coaching page renderers and chat helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from config.settings import Settings
from state import StateManager, get_state_manager


def render_ai_coaching_page(state: StateManager) -> None:
    """Render the AI coaching page with provider selection and chat."""
    st.header("🤖 AI Коучинг")

    from models.ai_coach_universal import UniversalAICoach
    from models.ai_providers import AIProviderFactory

    if not getattr(state, "ai_coach", None):
        state.ai_coach = None
    if not state.selected_provider:
        state.selected_provider = Settings.DEFAULT_AI_PROVIDER

    with st.sidebar.expander("⚙️ Настройки AI", expanded=True):
        st.subheader("Выбор AI провайдера")
        available = AIProviderFactory.get_available_providers()
        for name, is_available in available.items():
            if is_available:
                st.success(f"✅ {name}")
            else:
                st.error(f"❌ {name}")

        provider_options = {
            "OpenAI (GPT)": "openai",
            "Anthropic (Claude)": "anthropic",
            "Google (Gemini)": "google",
            "Ollama (Локально)": "ollama",
        }

        selected_name = st.selectbox(
            "Провайдер:",
            options=list(provider_options.keys()),
            index=list(provider_options.values()).index(state.selected_provider),
        )
        selected_provider = provider_options[selected_name]

        provider_kwargs = {}

        @st.cache_data(ttl=300)
        def get_models_for_provider(provider_type, **kwargs):
            try:
                temp_provider = AIProviderFactory.create_provider(provider_type, **kwargs)
                return temp_provider.get_available_models()
            except Exception:
                return []

        if selected_provider == "openai":
            api_key = st.text_input("API Key:", value=Settings.OPENAI_API_KEY or "", type="password")
            if api_key:
                with st.spinner("Загрузка списка моделей OpenAI..."):
                    available_models = get_models_for_provider("openai", api_key=api_key)
            else:
                available_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo-preview"]

            if available_models:
                current_model = Settings.OPENAI_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} доступно)",
                    available_models,
                    index=default_index,
                    help=f"Выберите модель из {len(available_models)} доступных",
                )
            else:
                model = st.text_input("Модель:", value=Settings.OPENAI_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей. Введите название модели вручную.")
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "anthropic":
            api_key = st.text_input("API Key:", value=Settings.ANTHROPIC_API_KEY or "", type="password")
            available_models = [
                "claude-3-haiku-20240307",
                "claude-3-sonnet-20240229",
                "claude-3-opus-20240229",
                "claude-2.1",
                "claude-2.0",
            ]
            current_model = Settings.ANTHROPIC_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Claude",
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "google":
            api_key = st.text_input("API Key:", value=Settings.GOOGLE_API_KEY or "", type="password")
            available_models = [
                "models/gemini-2.5-flash",
                "models/gemini-2.0-flash-exp",
                "models/gemini-2.0-flash",
                "models/gemini-1.5-flash-latest",
                "models/gemini-1.5-flash",
                "models/gemini-1.5-flash-8b",
            ]
            current_model = Settings.GOOGLE_MODEL
            try:
                default_index = available_models.index(current_model)
            except ValueError:
                default_index = 0
            model = st.selectbox(
                f"Модель: ({len(available_models)} доступно)",
                available_models,
                index=default_index,
                help="Выберите модель Gemini",
            )
            provider_kwargs = {"api_key": api_key, "model": model}

        elif selected_provider == "ollama":
            host = st.text_input("Host:", value=Settings.OLLAMA_HOST)
            with st.spinner("Загрузка локальных моделей Ollama..."):
                available_models = get_models_for_provider("ollama", host=host, model="dummy")
            if available_models:
                current_model = Settings.OLLAMA_MODEL
                try:
                    default_index = available_models.index(current_model)
                except ValueError:
                    default_index = 0
                model = st.selectbox(
                    f"Модель: ({len(available_models)} локальных)",
                    available_models,
                    index=default_index,
                    help=f"Выберите локальную модель из {len(available_models)} установленных",
                )
            else:
                model = st.text_input("Модель:", value=Settings.OLLAMA_MODEL)
                st.warning("⚠️ Не удалось загрузить список моделей Ollama. Убедитесь, что Ollama запущен.")
            provider_kwargs = {"host": host, "model": model}

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Тест подключения", help="Проверить API ключ и подключение"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    with st.spinner("Проверка подключения..."):
                        test_result = provider.test_connection()
                    if test_result.get("success"):
                        st.success(f"✅ {test_result.get('message')}")
                        with st.expander("📋 Детали подключения"):
                            for key, value in test_result.items():
                                if key not in ["success", "message"]:
                                    st.write(f"**{key}:** {value}")
                    else:
                        st.error(f"❌ {test_result.get('error')}")
                except Exception as exc:
                    st.error(f"❌ Ошибка тестирования: {exc}")
        with col2:
            if st.button("🔌 Подключить AI", help="Подключиться к выбранному провайдеру"):
                try:
                    provider = AIProviderFactory.create_provider(selected_provider, **provider_kwargs)
                    if provider.is_available():
                        state.ai_coach = UniversalAICoach(provider)
                        state.selected_provider = selected_provider
                        st.success(f"✅ Подключено к {provider.get_model_name()}")
                        st.info(f"🎯 Выбранная модель: **{provider_kwargs.get('model')}**")
                    else:
                        st.error("❌ Не удалось подключиться к провайдеру")
                except Exception as exc:
                    st.error(f"❌ Ошибка: {exc}")

    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера в боковой панели")
        return

    if state.switch_to_chat_tab:
        state.switch_to_chat_tab = False

    render_ai_chat_page(state)


def render_ai_chat_page(state: StateManager) -> None:
    """Render the modern AI chat interface with history and tools."""
    database = state.database
    if state.ai_coach is None:
        st.warning("👆 Настройте AI провайдера для использования чата")
        return

    if "ai_tools" not in state:
        from models.ai_tools import AITools

        state.ai_tools = AITools(database)

    if "data_context" not in state:
        state.data_context = None
        state.context_loaded = False

    if "current_chat_id" not in state:
        state.current_chat_id = None

    if state.current_chat_id is None:
        existing_chats = state.chat_manager.get_chat_list()
        if existing_chats:
            state.current_chat_id = existing_chats[0]["id"]

    st.markdown(
        """
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
        background: white;
        padding: 15px 0;
        border-top: 1px solid #ddd;
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
        color: #666;
        margin: 0;
    }

    [data-testid="stChatMessage"][data-testid*="assistant"] {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }

    [data-testid="stChatMessage"][data-testid*="user"] {
        background-color: #e3f2fd;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

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
                    system_prompt = create_chat_system_prompt_with_tools(state.data_context)
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

    st.title("🤖 AI Тренер")

    if not state.context_loaded:
        with st.spinner("Загрузка данных для AI..."):
            from models.ai_data_context import AIDataContext

            data_context = AIDataContext(database)
            state.data_context = data_context.get_full_context(context_days)
            state.context_loaded = True

    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        st.caption(f"ID текущего чата: {state.current_chat_id or '—'}")

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
            with st.chat_message("assistant"):
                st.markdown(
                    """
                👋 **Привет! Я ваш персональный AI тренер.**

                У меня есть доступ ко всем вашим тренировочным данным и мощные инструменты для анализа:

                **🎯 Что я могу:**
                • Анализировать ваши тренировки и прогресс
                • Давать рекомендации по восстановлению и нагрузкам
                • Объяснять метрики и показатели простым языком
                • Составлять персональные планы тренировок
                • Отвечать на любые вопросы о ваших данных

                **💡 Попробуйте спросить:**
                - "Как мое восстановление сегодня?"
                - "Сколько тренировок у меня было в июле?"
                - "Покажи мой прогресс за последний месяц"
                - "Можно ли мне тренироваться интенсивно?"

                Начните диалог! 🚀
                """
                )

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="chat-input-fixed">', unsafe_allow_html=True)

    st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
    st.markdown("**⚡ Быстрые вопросы:**")
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        if st.button("💪 Форма", key="form_q", help="Как моя текущая форма?"):
            process_modern_chat_message(
                "Проанализируй мою текущую форму (TSB, CTL, ATL) и состояние восстановления (HRV). Дай четкую оценку готовности к нагрузкам."
            )

    with col2:
        if st.button("📅 План", key="plan_q", help="План на неделю"):
            process_modern_chat_message(
                "На основе моего текущего состояния (TSB, HRV, недавние тренировки) составь конкретный план тренировок на следующую неделю. ОБЯЗАТЕЛЬНО дай четкий план по дням с видами тренировок и интенсивностью."
            )

    with col3:
        if st.button("📊 Прогресс", key="progress_q", help="Анализ прогресса"):
            process_modern_chat_message(
                "Покажи мой прогресс за месяц: тренды нагрузки, лучшие результаты, изменение формы. ОБЯЗАТЕЛЬНО дай конкретные выводы."
            )

    with col4:
        if st.button("💓 HRV", key="hrv_q", help="Анализ восстановления"):
            process_modern_chat_message(
                "Проанализируй мое состояние восстановления: HRV тренды, нагрузка за неделю, качество сна. ОБЯЗАТЕЛЬНО дай рекомендации по тренировкам."
            )

    st.markdown("</div>", unsafe_allow_html=True)

    user_input = st.chat_input("Задайте вопрос AI тренеру...")

    if user_input:
        process_modern_chat_message(user_input)

    st.markdown("</div>", unsafe_allow_html=True)


def handle_chat_command(command: str, state) -> None:
    """Обрабатывает команды чата (начинающиеся с /)."""
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()

    state.chat_manager.add_message(state.current_chat_id, "user", command)

    with st.chat_message("user"):
        st.write(command)

    with st.chat_message("assistant"):
        response = ""

        if cmd == "/speechcore":
            response = handle_speechcore_command(args, state)
        else:
            response = (
                f"❓ Неизвестная команда: `{cmd}`\n\n"
                "Доступные команды:\n- `/speechcore` - Управление речевыми функциями"
            )

        st.markdown(response)
        state.chat_manager.add_message(state.current_chat_id, "assistant", response)

    st.rerun()


def handle_speechcore_command(args: str, state) -> str:
    """Обрабатывает команду /speechcore."""
    args = args.strip().lower()

    if "speechcore_enabled" not in state._session:
        state._session["speechcore_enabled"] = False
    if "speechcore_voice" not in state._session:
        state._session["speechcore_voice"] = "default"

    if args == "" or args == "help" or args == "?":
        enabled_status = "✅ Включен" if state._session.get("speechcore_enabled", False) else "❌ Выключен"
        voice_name = state._session.get("speechcore_voice", "default")
        return f"""🎤 **SpeechCore - Речевые функции AI тренера**

**Доступные команды:**
- `/speechcore` или `/speechcore help` - Показать эту справку
- `/speechcore on` - Включить речевой синтез (озвучивание ответов)
- `/speechcore off` - Выключить речевой синтез
- `/speechcore status` - Показать текущий статус
- `/speechcore voice <имя>` - Выбрать голос (например: `default`, `female`, `male`)

**Текущий статус:**
- Речевой синтез: {enabled_status}
- Голос: `{voice_name}`

**Примечание:** Речевой синтез будет озвучивать ответы AI тренера в чате."""

    elif args == "on" or args == "enable":
        state._session["speechcore_enabled"] = True
        return f"""✅ **Речевой синтез включен**

Ответы AI тренера теперь будут озвучиваться. Голос: `{state._session.get('speechcore_voice', 'default')}`

Используйте `/speechcore off` для отключения."""

    elif args == "off" or args == "disable":
        state._session["speechcore_enabled"] = False
        return """❌ **Речевой синтез выключен**

Ответы AI тренера больше не будут озвучиваться.

Используйте `/speechcore on` для включения."""

    elif args == "status":
        enabled = state._session.get("speechcore_enabled", False)
        voice = state._session.get("speechcore_voice", "default")
        return f"""📊 **Статус SpeechCore**

- Речевой синтез: {'✅ Включен' if enabled else '❌ Выключен'}
- Голос: `{voice}`

Используйте `/speechcore help` для списка команд."""

    elif args.startswith("voice "):
        voice_name = args.replace("voice ", "").strip()
        if voice_name:
            state._session["speechcore_voice"] = voice_name
            return f"""🎙️ **Голос изменен**

Новый голос: `{voice_name}`

Доступные варианты: `default`, `female`, `male`

Используйте `/speechcore on` для включения речевого синтеза."""
        else:
            return """❌ **Ошибка**

Укажите имя голоса. Например: `/speechcore voice female`"""

    else:
        return f"""❓ **Неизвестная подкоманда: `{args}`**

Используйте `/speechcore help` для списка доступных команд."""


def process_modern_chat_message(user_input):
    """Обрабатывает сообщение в современном чате с сохранением."""
    state = get_state_manager()

    if user_input.startswith("/"):
        handle_chat_command(user_input, state)
        return

    if not state.current_chat_id:
        state.current_chat_id = state.chat_manager.create_new_chat()

    if not state.chat_manager.add_message(state.current_chat_id, "user", user_input):
        st.error(f"❌ Не удалось сохранить сообщение пользователя (чат {state.current_chat_id}).")
        return

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()

        try:
            system_prompt = create_chat_system_prompt_with_tools(state.data_context)

            chat_messages = state.chat_manager.get_chat_messages(state.current_chat_id)
            conversation_history = ""
            for msg in chat_messages[:-1]:
                conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"

            full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""

            response_placeholder.markdown("🤖 *Генерирую ответ...*")

            ai_response = state.ai_coach.provider.generate_response(full_prompt, "")

            response_placeholder.markdown("🔧 *Обрабатываю данные...*")

            final_response = process_tool_calls(ai_response)
            final_response = maybe_append_progress_report(state, user_input, final_response)

            simulate_streaming_response(response_placeholder, final_response)

            if not state.chat_manager.add_message(state.current_chat_id, "assistant", final_response):
                st.error(f"❌ Не удалось сохранить ответ AI в чат (чат {state.current_chat_id}).")

            if state._session.get("speechcore_enabled", False):
                speak_text(final_response, state._session.get("speechcore_voice", "default"))

            state.selected_page = "🤖 AI Коучинг"
            state.switch_to_chat_tab = True

            st.rerun()

        except Exception as e:
            error_msg = f"❌ Ошибка AI: {e}"
            response_placeholder.markdown(error_msg)
            state.chat_manager.add_message(state.current_chat_id, "assistant", error_msg)


def process_chat_message(user_input):
    """Обрабатывает сообщение пользователя в чате с поддержкой инструментов."""
    state = get_state_manager()
    state.chat_messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("AI тренер анализирует данные..."):
            try:
                system_prompt = create_chat_system_prompt_with_tools(state.data_context)

                conversation_history = ""
                for msg in state.chat_messages[:-1]:
                    conversation_history += f"\n{msg['role'].upper()}: {msg['content']}"

                full_prompt = f"""
{system_prompt}

ИСТОРИЯ РАЗГОВОРА:{conversation_history}

НОВЫЙ ВОПРОС ПОЛЬЗОВАТЕЛЯ: {user_input}

Используй инструменты для получения точных данных. ОБЯЗАТЕЛЬНО завершай задачу полностью - если просят план, составляй конкретный план, а не только анализируй данные. Отвечай персонально, конкретно и полезно. Используй эмодзи.
"""

                ai_response = state.ai_coach.provider.generate_response(full_prompt, "")

                final_response = process_tool_calls(ai_response)
                final_response = maybe_append_progress_report(state, user_input, final_response)

                st.markdown(final_response)
                state.chat_messages.append({"role": "assistant", "content": final_response})

            except Exception as e:
                st.error(f"❌ Ошибка AI: {e}")


def create_chat_system_prompt_with_tools(data_context):
    """Создает системный промпт с инструментами для доступа к данным."""
    state = get_state_manager()

    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

У тебя есть доступ к мощным инструментам для анализа данных пользователя. Используй их для получения точной, актуальной информации.

ТВОИ ПРИНЦИПЫ:
• ВСЕГДА используй инструменты для получения конкретных данных
• ВСЕГДА завершай задачу полностью - не останавливайся на анализе
• Давай персонализированные, научно обоснованные советы
• Объясняй сложные концепции простым языком
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным с цифрами и фактами

ДАННЫЕ И ИНСТРУМЕНТЫ:
• Для запросов о шагах, калориях или ЧСС покоя ОБЯЗАТЕЛЬНО сначала вызывай инструмент **get_daily_health_stats** (укажи days при необходимости)
• Для readiness, VO₂max и статусов Garmin ОБЯЗАТЕЛЬНО сначала применяй **get_training_status** (для конкретных дат) или **analyze_training_status**
• Если вопрос требует период/дату, вызывай инструмент с параметром days/start/end, а затем цитируй фактические значения из результата
• Метрики CTL/ATL/TSB и анализ нагрузки получай через соответствующие инструменты, вместо общих оценок
• Если данных нет, явно сообщай об этом пользователю
"""

    tools_description = state.ai_tools.format_tool_descriptions_for_ai()

    return f"{base_prompt}\n\n{tools_description}"


def create_chat_system_prompt(data_context):
    """Создает системный промпт с полным контекстом данных пользователя."""
    from models.ai_data_context import AIDataContext

    base_prompt = """
Ты — персональный AI тренер по выносливости с глубокими знаниями спортивной науки.

У тебя есть полный доступ к данным пользователя и ты должен давать персонализированные, научно обоснованные советы.

ТВОИ ПРИНЦИПЫ:
• Всегда основывайся на предоставленных данных пользователя
• Объясняй сложные концепции простым языком
• Давай конкретные, практические рекомендации
• Учитывай индивидуальные особенности и текущее состояние
• Предупреждай о рисках перетренированности и травм
• Поощряй постепенное развитие и терпение

ТВОИ ЭКСПЕРТИЗЫ:
• Анализ тренировочной нагрузки (TSS, CTL, ATL, TSB)
• Интерпретация HRV и состояния восстановления
• Планирование тренировок и периодизация
• Физиология выносливости и адаптации
• Предотвращение перетренированности
• Техника и тактика в видах спорта на выносливость

СТИЛЬ ОБЩЕНИЯ:
• Дружелюбный и мотивирующий
• Используй эмодзи для лучшего восприятия
• Структурируй ответы с заголовками и списками
• Будь конкретным, но не перегружай деталями
• Адаптируй сложность под уровень пользователя
"""

    if not data_context or not data_context["summary"]["has_data"]:
        return (
            base_prompt
            + "\n\nВНИМАНИЕ: У пользователя нет данных тренировок. Давай общие рекомендации и объясни, как начать отслеживание тренировок."
        )

    context_formatter = AIDataContext(None)
    formatted_context = context_formatter.format_context_for_ai(data_context)

    return f"{base_prompt}\n\n{formatted_context}"


def process_tool_calls(ai_response):
    """Обрабатывает вызовы инструментов в ответе AI."""
    import re

    state = get_state_manager()

    tool_pattern = r"\[TOOL:\s*([^,\]]+)(?:,\s*([^\]]*))?\]"

    def replace_tool_call(match):
        tool_name = match.group(1).strip()
        params_str = match.group(2).strip() if match.group(2) else ""

        params = {}
        if params_str:
            param_pairs = [p.strip() for p in params_str.split(",")]
            for pair in param_pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if value.isdigit():
                        params[key] = int(value)
                    elif value.replace(".", "").isdigit():
                        params[key] = float(value)
                    else:
                        params[key] = value.strip("\"'")

        try:
            result = state.ai_tools.execute_tool(tool_name, **params)

            if result.get("success"):
                data = result["result"]
                formatted_result = format_tool_result(tool_name, data)
                return formatted_result
            else:
                return f"❌ Ошибка инструмента: {result.get('error', 'Неизвестная ошибка')}"

        except Exception as e:
            return f"❌ Ошибка выполнения {tool_name}: {str(e)}"

    processed_response = re.sub(tool_pattern, replace_tool_call, ai_response)
    return processed_response


def speak_text(text: str, voice: str = "default"):
    """Озвучивает текст с помощью Web Speech API через JavaScript."""
    import json
    import re

    clean_text = text
    clean_text = re.sub(r"^#+\s+", "", clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_text)
    clean_text = re.sub(r"\*(.+?)\*", r"\1", clean_text)
    clean_text = re.sub(r"`(.+?)`", r"\1", clean_text)
    clean_text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean_text)

    if len(clean_text) > 500:
        clean_text = clean_text[:500] + "..."

    clean_text_escaped = json.dumps(clean_text, ensure_ascii=False)

    js_code = f"""
    <script>
    (function() {{
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();

            function speak() {{
                const utterance = new SpeechSynthesisUtterance({clean_text_escaped});
                utterance.lang = 'ru-RU';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                utterance.volume = 1.0;

                const voices = window.speechSynthesis.getVoices();
                if (voices.length > 0) {{
                    let selectedVoice = voices.find(v => v.lang.startsWith('ru'));
                    if (!selectedVoice) {{
                        selectedVoice = voices[0];
                    }}
                    utterance.voice = selectedVoice;
                }}

                window.speechSynthesis.speak(utterance);
            }}

            if (window.speechSynthesis.getVoices().length > 0) {{
                speak();
            }} else {{
                window.speechSynthesis.onvoiceschanged = speak;
            }}
        }} else {{
            console.warn('Speech synthesis not supported');
        }}
    }})();
    </script>
    """

    import streamlit.components.v1 as components

    components.html(js_code, height=0)


def simulate_streaming_response(placeholder, text):
    """Симулирует стриминг вывода текста для лучшего UX."""
    import re
    import time

    if len(text) <= 100:
        placeholder.markdown(text)
        return

    sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)(?=\n)|(?<=:)\n", text)
    current_text = ""

    for i, sentence in enumerate(sentences):
        current_text += sentence

        if i < len(sentences) - 1:
            display_text = current_text + " ▋"
        else:
            display_text = current_text

        placeholder.markdown(display_text)

        if len(sentence) > 50:
            time.sleep(0.25)
        elif len(sentence) > 20:
            time.sleep(0.12)
        else:
            time.sleep(0.04)

    placeholder.markdown(current_text)


PROGRESS_KEYWORDS = (
    "прогресс за месяц",
    "прогресс за последний месяц",
    "покажи прогресс за месяц",
    "итоги месяца",
    "итоги за месяц",
    "month progress",
    "monthly progress",
)


def format_tool_result(tool_name, data):
    """Форматирует результат инструмента для красивого отображения."""
    if tool_name == "get_performance_metrics":
        tsb_emoji = "🟢" if data["tsb"] > 5 else "🟡" if data["tsb"] > -10 else "🟠" if data["tsb"] > -25 else "🔴"

        return f"""
## 📊 Текущие метрики производительности

### 🎯 Модель Банистера:
• **CTL** (хроническая нагрузка): **{data['ctl']:.1f}** 📈
• **ATL** (острая нагрузка): **{data['atl']:.1f}** ⚡
• **TSB** (баланс стресса): **{data['tsb']:+.1f}** {tsb_emoji}

### 🏃‍♂️ Анализ формы:
• **Текущая форма:** {data['form_state']}
• **Тренд фитнеса:** {data['fitness_trend']}
"""

    elif tool_name == "get_recent_activities":
        if data["count"] == 0:
            return "📭 **Нет недавних активностей**"

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
        }

        activities_text = f"## 🏃‍♂️ Последние {min(5, data['count'])} тренировок:\n\n"
        for i, activity in enumerate(data["activities"][:5], 1):
            sport = activity.get("sport", "unknown")
            emoji = sport_emojis.get(sport, "⚡")
            description = activity.get("description", f"{sport} - {activity.get('duration_minutes', 0):.0f}мин")
            activities_text += f"{i}. **{activity['date']}** {emoji} {description}\n"

        return activities_text

    elif tool_name == "get_activities":
        count = data.get("count", 0)
        period = data.get("period_days")
        activities = data.get("activities") or []

        if count == 0 or not activities:
            period_text = f"за {period} дней" if period is not None else ""
            return f"📭 **Нет тренировок {period_text}**"

        total_tss = sum(float(a.get("tss", 0) or 0) for a in activities)
        total_duration = sum(float(a.get("duration_minutes", 0) or 0) for a in activities)

        header = f"## 🏃‍♂️ Тренировки за {period} дней\n\n"
        summary = (
            f"- Всего занятий: **{count}**\n"
            f"- Суммарный TSS: **{total_tss:.0f}**\n"
            f"- Общее время: **{total_duration/60:.1f} ч**\n\n"
        )

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
            "strength": "💪",
        }

        rows = []
        for activity in activities[:7]:
            date = activity.get("date", "N/A")
            sport = activity.get("sport", "unknown")
            emoji = sport_emojis.get(sport.lower(), "⚡") if isinstance(sport, str) else "⚡"
            duration = activity.get("duration_minutes", 0) or 0
            tss = activity.get("tss", 0) or 0
            description = activity.get("description")
            if not description:
                description = f"{sport} — {duration:.0f} мин, TSS {tss:.0f}"
            rows.append(f"| {date} | {emoji} {description} |")

        table_header = "| Дата | Сессия |\n| --- | --- |\n"
        table_body = "\n".join(rows)

        return header + summary + table_header + table_body

    elif tool_name == "analyze_hrv_trends":
        recovery_emoji = {"отличное": "🟢", "хорошее": "🟡", "удовлетворительное": "🟠", "плохое": "🔴"}
        trend_emoji = {"improving": "📈", "declining": "📉"}

        return f"""
**💓 Анализ HRV:**
• Текущий RMSSD: {data['current_rmssd']:.1f} мс
• Среднее за 7 дней: {data['recent_avg_7days']:.1f} мс
• Базовый уровень: {data['baseline_median']:.1f} мс
• Тренд: {trend_emoji.get(data['trend_direction'], '')} {data['trend_direction']}
• Восстановление: {recovery_emoji.get(data['recovery_state'], '')} {data['recovery_state']}
"""

    elif tool_name == "get_activity_stats":
        return f"""
**📈 Статистика тренировок за {data['period_days']} дней:**
• Всего тренировок: {data['total_activities']}
• Общее время: {data['total_duration_hours']:.1f} ч
• Общий TSS: {data['total_tss']:.0f}
• Частота: {data['activities_per_week']:.1f} раз в неделю
• Средний TSS: {data['avg_tss_per_session']:.1f}
"""

    elif tool_name == "compare_periods":
        message = data.get("message")
        period2 = data.get("period2_days")

        if message:
            fallback = data.get("fallback", {})
            summary_lines = [f"### {message}"]

            recent_stats = fallback.get("recent_activity_stats")
            if isinstance(recent_stats, dict):
                summary_lines.append(
                    f"- Последний период: {recent_stats.get('total_activities', 0)} тренировок, "
                    f"{recent_stats.get('total_duration_hours', 0):.1f} ч, TSS {recent_stats.get('total_tss', 0):.0f}"
                )

            load_summary = fallback.get("training_load")
            if isinstance(load_summary, dict):
                summary_lines.append(f"- Тренд нагрузки: {load_summary.get('load_trend', 'н/д')}")

            summary_lines.append("Попробуй обновить данные, чтобы сравнить периоды заново.")

            return "## 📈 Прогресс за период\n\n" + "\n".join(summary_lines)

        recent = data.get("recent_period", {}) or {}
        previous = data.get("previous_period", {}) or {}
        comparison = data.get("comparison", {}) or {}

        def fmt_hours(minutes: float) -> str:
            return f"{(minutes or 0) / 60:.1f} ч"

        def fmt_delta(value: Optional[float], unit: str = "", precision: int = 0) -> str:
            if value is None:
                return "0"
            sign = "+" if value > 0 else ""
            formatted = f"{sign}{value:.{precision}f}" if precision > 0 else f"{sign}{int(value)}"
            return f"{formatted}{unit}"

        def arrow(value: Optional[float]) -> str:
            if value is None:
                return "→"
            if value > 0:
                return "↑"
            if value < 0:
                return "↓"
            return "→"

        recent_duration = recent.get("total_duration", 0.0)
        previous.get("total_duration", 0.0)
        volume_change = comparison.get("volume_change")
        duration_change_hours = (volume_change or 0) / 60 if volume_change is not None else None

        summary_block = [
            "## 📈 Прогресс за период",
            "",
            "**Итоги текущего периода**",
            f"- Тренировок: **{recent.get('activity_count', 0)}**",
            f"- Общее время: **{fmt_hours(recent_duration)}**",
            f"- Суммарный TSS: **{recent.get('total_tss', 0):.0f}**",
            f"- Частота: **{recent.get('activities_per_week', 0):.1f} / нед**",
        ]

        if not previous.get("no_data"):
            summary_block.extend(
                [
                    "",
                    f"**Динамика vs предыдущие {period2 or 'предыдущие'} дней**",
                    f"- Тренировок: {comparison.get('activity_count_change', 0):+d} {arrow(comparison.get('activity_count_change'))}",
                    f"- Объём: {fmt_delta(duration_change_hours, ' ч', 1)} {arrow(duration_change_hours)}",
                    f"- TSS: {fmt_delta(comparison.get('tss_change'), '', 0)} {arrow(comparison.get('tss_change'))}",
                ]
            )
        else:
            summary_block.append("\nНет данных для сравнения с предыдущим периодом.")

        return "\n".join(summary_block)

    elif tool_name == "analyze_training_load":
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        intensity = data.get("intensity_distribution", {})
        weekly = data.get("weekly_breakdown", []) or []

        intensity_lines = (
            [
                f"- Низкая: {intensity.get('low_intensity_percent', 0):.1f}%",
                f"- Умеренная: {intensity.get('moderate_intensity_percent', 0):.1f}%",
                f"- Высокая: {intensity.get('high_intensity_percent', 0):.1f}%",
            ]
            if intensity
            else ["- Нет данных по зонам интенсивности"]
        )

        if weekly:
            table_rows = [
                "| Неделя | Сессий | TSS | Часы |",
                "| --- | --- | --- | --- |",
            ]
            for week in weekly[:4]:
                hours = (week.get("total_duration", 0) or 0) / 60
                table_rows.append(
                    f"| {week.get('week', '—')} | {week.get('session_count', 0)} | "
                    f"{week.get('total_tss', 0):.0f} | {hours:.1f} |"
                )
            weekly_section = "\n".join(table_rows)
        else:
            weekly_section = "Нет разбивки по неделям."

        return f"""
## 📊 Анализ тренировочной нагрузки

### ⚙️ Распределение интенсивности:
{chr(10).join(intensity_lines)}

### 📅 Недельная разбивка:
{weekly_section}
"""

    elif tool_name == "analyze_recovery_state":
        factors = data.get("factors", [])
        hrv_data = data.get("hrv", {})
        training_load = data.get("training_load", {})

        hrv_section = ""
        if hrv_data:
            current_rmssd = hrv_data.get("current_rmssd", 0)
            baseline_rmssd = hrv_data.get("baseline_rmssd", 0)
            deviation = hrv_data.get("deviation_percent", 0)

            if deviation > 10:
                hrv_emoji = "🟢"
                hrv_status = "отличное"
            elif deviation > -5:
                hrv_emoji = "🟡"
                hrv_status = "хорошее"
            elif deviation > -15:
                hrv_emoji = "🟠"
                hrv_status = "удовлетворительное"
            else:
                hrv_emoji = "🔴"
                hrv_status = "требует внимания"

            hrv_section = f"""
### 💓 HRV Анализ:
• **Текущий RMSSD:** {current_rmssd:.1f} мс {hrv_emoji}
• **Базовый уровень:** {baseline_rmssd:.1f} мс
• **Отклонение:** {deviation:+.1f}% ({hrv_status})"""

        load_section = ""
        if training_load:
            week_tss = training_load.get("week_tss", 0)
            session_count = training_load.get("session_count", 0)
            avg_tss = training_load.get("avg_tss_per_session", 0)

            if week_tss > 400:
                load_emoji = "🔴"
                load_status = "высокая"
            elif week_tss > 250:
                load_emoji = "🟡"
                load_status = "умеренная"
            else:
                load_emoji = "🟢"
                load_status = "низкая"

            load_section = f"""
### ⚡ Недельная нагрузка:
• **TSS за неделю:** {week_tss:.0f} {load_emoji} ({load_status})
• **Тренировок:** {session_count}
• **Средний TSS:** {avg_tss:.1f}"""

        factors_section = ""
        if factors:
            factors_section = f"""
### 🎯 Анализ и рекомендации:
{chr(10).join([f"• {factor}" for factor in factors[:5]])}"""

        return f"""
## 🔋 Анализ состояния восстановления
{hrv_section}
{load_section}
{factors_section}"""

    elif tool_name == "get_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        latest = data.get("latest", {})
        summary = data.get("summary", {})

        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default

        status_distribution = summary.get("status_distribution", {})
        distribution_lines = [f"• {status}: {count}" for status, count in list(status_distribution.items())[:5]] if status_distribution else ["• Нет статистики по статусам"]

        history = data.get("history", [])
        readiness_rows = []
        for entry in history:
            readiness = entry.get("training_readiness")
            date_value = entry.get("date")
            if isinstance(date_value, str):
                date_str = date_value
            elif hasattr(date_value, "strftime"):
                date_str = date_value.strftime("%Y-%m-%d")
            else:
                date_str = str(date_value)
            if readiness is not None and not (hasattr(pd, "isna") and pd.isna(readiness)):
                readiness_rows.append((date_str, readiness))
        readiness_rows = readiness_rows[:7]
        if readiness_rows:
            readiness_table = "\n".join([f"| {date} | {fmt_number(value, '.0f')} / 100 |" for date, value in readiness_rows])
            readiness_block = f"""
### 📅 Readiness по датам:
| Дата | Readiness |
| --- | --- |
{readiness_table}
"""
        else:
            readiness_block = "\n### 📅 Readiness по датам:\n• Нет данных по дням\n"

        return f"""
## 📈 Статус тренированности (последние {data.get('period_days', 30)} дней)

### 🔝 Последний статус:
• Статус Garmin: {latest.get('training_status', 'н/д')}
• Readiness: {fmt_number(latest.get('training_readiness'), '.0f')} / 100
• Нагрузка 7 дней: {fmt_number(latest.get('training_load_7d'), '.0f')}
• VO₂max: {fmt_number(latest.get('vo2_max'), '.1f')}

### 📊 Средние значения:
• Readiness: {fmt_number(summary.get('avg_training_readiness'), '.1f')} / 100
• Нагрузка (7д): {fmt_number(summary.get('avg_training_load_7d'), '.1f')}
• VO₂max: {fmt_number(summary.get('avg_vo2_max'), '.1f')}

### 🧭 Распределение статусов:
{chr(10).join(distribution_lines)}
{readiness_block}
"""

    elif tool_name == "analyze_training_status":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        insights = data.get("insights", [])
        latest = data.get("latest", {})
        readiness = data.get("readiness_assessment", {})
        load = data.get("load_assessment", {})

        def fmt_section(section: Dict[str, Any], default: str) -> str:
            lines = [value for value in section.values() if isinstance(value, str)]
            return chr(10).join([f"• {line}" for line in lines]) if lines else default

        return f"""
## 🧠 Анализ статуса тренированности

### 🔝 Последний статус:
• {latest.get('summary', 'Нет данных')}

### 💡 Ключевые выводы:
{chr(10).join([f"• {item}" for item in insights]) if insights else "• Нет выводов — недостаточно данных"}

### 📈 Readiness:
{fmt_section(readiness, "• Недостаточно данных по readiness")}

### ⚙️ Нагрузка:
{fmt_section(load, "• Недостаточно данных по нагрузке")}
"""

    elif tool_name == "get_daily_health_stats":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if data.get("message"):
            return f"ℹ️ **{data['message']}**"

        stats = data.get("stats", {})
        trend = data.get("trend_steps", "н/д")
        recent = data.get("recent_entries", [])

        def fmt_number(value, fmt: str = ".1f", default: str = "н/д"):
            if value is None:
                return default
            try:
                if pd.isna(value):
                    return default
                return format(float(value), fmt)
            except (TypeError, ValueError):
                return default

        recent_lines = []
        for entry in recent[:5]:
            date = entry.get("date")
            steps = fmt_number(entry.get("steps"), ".0f")
            resting_hr = fmt_number(entry.get("resting_hr"), ".0f")
            active_minutes = fmt_number(entry.get("active_minutes"), ".0f")
            recent_lines.append(f"• {date}: шаги {steps}, ЧСС покоя {resting_hr}, активность {active_minutes} мин")

        return f"""
## 🏥 Ежедневные показатели здоровья ({data.get('period_days', 30)} дней)

### 📊 Средние значения:
• Шаги: {fmt_number(stats.get('avg_steps'), '.0f')} в день
• ЧСС покоя: {fmt_number(stats.get('avg_resting_hr'), '.1f')} уд/мин
• Активные минуты: {fmt_number(stats.get('avg_active_minutes'), '.1f')} мин/день
• Активные калории: {fmt_number(stats.get('avg_calories_active'), '.0f')} ккал/день

### 📈 Тренд шагов: {trend}

### 🗓️ Последние дни:
{chr(10).join(recent_lines) if recent_lines else "• Нет свежих записей"}
"""

    elif tool_name == "get_activities_by_date_range":
        if data["count"] == 0:
            return f"📭 **Нет тренировок в период {data['period']}**"

        stats = data["statistics"]

        sport_emojis = {
            "cycling": "🚴",
            "running": "🏃",
            "swimming": "🏊",
            "open_water_swimming": "🏊‍♂️",
            "walking": "🚶",
            "strength": "💪",
            "yoga": "🧘",
            "other": "⚡",
        }

        sports_text = []
        for sport, count in stats["sports_distribution"].items():
            emoji = sport_emojis.get(sport, "⚡")
            sports_text.append(f"{emoji} {sport}: {count}")

        activities_preview = ""
        if "activities" in data and data["activities"]:
            activities_preview = "\n\n**📋 Некоторые тренировки:**"
            for i, activity in enumerate(data["activities"][:5], 1):
                sport_emoji = sport_emojis.get(activity["sport"], "⚡")
                date_formatted = activity["date"]
                activities_preview += (
                    f"\n{i}. **{date_formatted}** {sport_emoji} {activity['sport']} - "
                    f"{activity['duration_minutes']:.0f}мин (TSS: {activity['tss']:.0f})"
                )

        return f"""
## 📊 Тренировки за период {data['period']}

### 📈 Основная статистика:
• **🏃‍♂️ Всего тренировок: {data['count']}**
• **⏱️ Общее время: {stats['total_duration_hours']:.1f} часов**
• **📈 Общий TSS: {stats['total_tss']:.0f}**
• **🎯 Средний TSS: {stats['avg_tss_per_session']:.1f}**
• **🏃 Дистанция: {stats['total_distance_km']:.1f} км**

### 🏆 Виды активности:
{chr(10).join([f"• {sport}" for sport in sports_text])}
{activities_preview}"""

    elif tool_name == "get_sleep_data":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"

        recent_sleep = data.get("recent_sleep", [])
        if recent_sleep:
            total_hours = []
            sleep_scores = []
            for record in recent_sleep:
                if record.get("total_sleep_hours") is not None:
                    total_hours.append(record["total_sleep_hours"])
                if record.get("sleep_score") is not None:
                    sleep_scores.append(record["sleep_score"])

            avg_hours = sum(total_hours) / len(total_hours) if total_hours else 0
            avg_score = sum(sleep_scores) / len(sleep_scores) if sleep_scores else 0

            latest_sleep = recent_sleep[0] if recent_sleep else {}
            recent_summary = f"Продолжительность: {latest_sleep.get('total_sleep_hours', 'н/д')}ч, "
            recent_summary += f"Качество: {latest_sleep.get('sleep_score', 'н/д')}/100, "
            recent_summary += f"Эффективность: {latest_sleep.get('sleep_efficiency', 'н/д')}%"
        else:
            avg_hours = 0
            avg_score = 0
            recent_summary = "Данные недоступны"

        return f"""
## 😴 Данные сна за последние {data.get('period_days', 30)} дней

### 📊 Основная информация:
• **Всего записей:** {data.get('data_points', 0)}
• **Среднее время сна:** {avg_hours:.1f} часов
• **Средняя оценка сна:** {avg_score:.1f}/100

### 🌙 Последний сон:
{recent_summary}"""

    elif tool_name == "get_sleep_stats":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных сна')}**"

        stats = data.get("statistics", {})
        quality = stats.get("current_sleep_quality", "не определено")

        quality_emoji = "🟢" if "отличное" in quality.lower() else "🟡" if "хорошее" in quality.lower() else "🟠" if "удовлетворительное" in quality.lower() else "🔴"

        avg_total = stats.get("avg_sleep_hours", 0) * 60
        deep_pct = (stats.get("avg_deep_sleep_minutes", 0) / avg_total * 100) if avg_total > 0 else 0
        rem_pct = (stats.get("avg_rem_sleep_minutes", 0) / avg_total * 100) if avg_total > 0 else 0
        light_pct = 100 - deep_pct - rem_pct if (deep_pct + rem_pct) <= 100 else 0

        return f"""
## 😴 Статистика сна за {stats.get('period_days', 30)} дней

### 🎯 Общая оценка: {quality_emoji} {quality}

### 📈 Средние показатели:
• **Продолжительность:** {stats.get('avg_sleep_hours', 0):.1f} часов
• **Качество сна:** {stats.get('avg_sleep_score', 0):.1f}/100
• **Эффективность:** {stats.get('avg_sleep_efficiency', 0):.1f}%
• **Пробуждения:** {stats.get('avg_awakenings', 0):.1f} раз за ночь

### 🌀 Фазы сна:
• **Глубокий сон:** {stats.get('avg_deep_sleep_minutes', 0):.0f} мин ({deep_pct:.1f}%)
• **Легкий сон:** Расчетное ({light_pct:.1f}%)
• **REM сон:** {stats.get('avg_rem_sleep_minutes', 0):.0f} мин ({rem_pct:.1f}%)"""

    elif tool_name == "analyze_sleep_patterns":
        if not data.get("has_data", True):
            return f"😴 **{data.get('message', 'Нет данных для анализа сна')}**"

        patterns = data.get("patterns", {})
        recommendations = patterns.get("recommendations", [])

        main_patterns = []
        if patterns.get("avg_sleep_duration"):
            main_patterns.append(f"• **Средняя продолжительность:** {patterns['avg_sleep_duration']}")
        if patterns.get("sleep_consistency"):
            main_patterns.append(f"• **Постоянство сна:** {patterns['sleep_consistency']}")
        if patterns.get("optimal_sleep_adherence"):
            main_patterns.append(f"• **Следование рекомендациям:** {patterns['optimal_sleep_adherence']}")

        quality_trends = []
        if patterns.get("avg_sleep_score"):
            quality_trends.append(f"• **Средняя оценка качества:** {patterns['avg_sleep_score']}")
        if patterns.get("sleep_trend"):
            quality_trends.append(f"• **Тренд:** {patterns['sleep_trend']}")

        phases_text = []
        if patterns.get("deep_sleep_percentage"):
            phases_text.append(f"• **Глубокий сон:** {patterns['deep_sleep_percentage']}")
        if patterns.get("rem_sleep_percentage"):
            phases_text.append(f"• **REM сон:** {patterns['rem_sleep_percentage']}")

        recommendations_text = ""
        if recommendations:
            recommendations_text = f"""
### 💡 Рекомендации:
{chr(10).join([f"• {rec}" for rec in recommendations[:5]])}"""

        return f"""
## 😴 Анализ паттернов сна за {data.get('period_days', 30)} дней

### 📊 Основные паттерны:
{chr(10).join(main_patterns) if main_patterns else "• Недостаточно данных для анализа"}

### 📈 Качество и тренды:
{chr(10).join(quality_trends) if quality_trends else "• Данные о качестве недоступны"}

### 🌀 Фазы сна:
{chr(10).join(phases_text) if phases_text else "• Данные о фазах недоступны"}
{recommendations_text}"""

    else:
        if isinstance(data, dict):
            if "message" in data:
                return f"ℹ️ **{data['message']}**"
            elif "error" in data:
                return f"❌ **Ошибка:** {data['error']}"

            result_text = f"## 📊 Результат: {tool_name.replace('_', ' ').title()}\n\n"

            important_keys = ["count", "total_tss", "period_days", "current_rmssd"]
            other_keys = [k for k in data.keys() if k not in important_keys and not k.startswith("_")]

            for key in important_keys:
                if key in data:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {data[key]}\n"

            for key in other_keys[:10]:
                value = data[key]
                if isinstance(value, (dict, list)) and len(str(value)) > 100:
                    result_text += f"• **{key.replace('_', ' ').title()}:** [данные доступны]\n"
                else:
                    result_text += f"• **{key.replace('_', ' ').title()}:** {value}\n"

            return result_text
        else:
            return f"**📊 {tool_name.replace('_', ' ').title()}:** {str(data)}"


def is_progress_request(text: Optional[str]) -> bool:
    """Определяет, просит ли пользователь отчёт по прогрессу за месяц."""
    if not text:
        return False
    lowered = text.lower()
    if "прогресс" in lowered and "меся" in lowered:
        return True
    return any(keyword in lowered for keyword in PROGRESS_KEYWORDS)


def maybe_append_progress_report(state, user_input: Optional[str], final_response: str) -> str:
    """Добавляет отчёт о прогрессе, если пользователь его запрашивал."""
    if not is_progress_request(user_input):
        return final_response

    filtered_existing = _filter_progress_sections(final_response)
    if filtered_existing and "## 📈 Прогресс" in filtered_existing:
        return filtered_existing

    progress_report = build_progress_report(state)
    if not progress_report:
        return filtered_existing or final_response

    base_text = filtered_existing.strip()
    if base_text and progress_report.strip() == base_text:
        return base_text

    if base_text:
        return f"{base_text}\n\n{progress_report}".strip()

    return progress_report.strip()


def build_progress_report(state, period_days: int = 30, previous_days: Optional[int] = None) -> Optional[str]:
    """Собирает структурированный отчёт о прогрессе, восстановлении и сне."""
    if state is None:
        return None

    ai_tools = getattr(state, "ai_tools", None)
    if ai_tools is None:
        return None

    previous_days = previous_days or period_days

    sections: List[str] = []
    compare_data: Optional[Dict[str, Any]] = None

    compare_result = ai_tools.execute_tool("compare_periods", period1_days=period_days, period2_days=previous_days)
    if compare_result.get("success"):
        compare_data = compare_result.get("result")
        if compare_data:
            compare_block = format_tool_result("compare_periods", compare_data)
            if compare_block:
                sections.append(compare_block.strip())
    else:
        error_msg = compare_result.get("error")
        if error_msg:
            sections.append(f"ℹ️ **Не удалось сформировать сравнение:** {error_msg}")

    load_data: Optional[Dict[str, Any]] = None
    load_result = ai_tools.execute_tool("analyze_training_load", days=period_days)
    if load_result.get("success"):
        potential_load = load_result.get("result")
        if isinstance(potential_load, dict) and potential_load:
            load_data = potential_load

    hrv_data: Optional[Dict[str, Any]] = None
    hrv_result = ai_tools.execute_tool("analyze_hrv_trends", days=period_days)
    if hrv_result.get("success"):
        potential_hrv = hrv_result.get("result")
        if isinstance(potential_hrv, dict) and potential_hrv:
            hrv_data = potential_hrv

    recovery_section = _format_recovery_section(load_data, hrv_data, period_days)
    if recovery_section:
        sections.append(recovery_section)

    sleep_data: Optional[Dict[str, Any]] = None
    sleep_result = ai_tools.execute_tool("get_sleep_stats", days=period_days)
    if sleep_result.get("success"):
        sleep_data = sleep_result.get("result")
        if isinstance(sleep_data, dict) and sleep_data.get("has_data"):
            sections.append(_format_sleep_section(sleep_data))

    recommendations = _generate_progress_recommendations(compare_data, load_data, hrv_data, sleep_data)
    if recommendations:
        bullet_lines = [f"{idx}. {rec}" for idx, rec in enumerate(recommendations, 1)]
        sections.append("### Что сделать дальше\n" + "\n".join(bullet_lines))

    sections.append("_Хочешь, составлю план на следующую неделю или разберу конкретный вид спорта?_")

    return "\n\n".join(section for section in sections if section and section.strip())


def _format_recovery_section(
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    period_days: int,
) -> str:
    """Формирует блок про нагрузку и восстановление в рамках периода."""
    if not load_data and not hrv_data:
        return ""

    lines: List[str] = [f"### Нагрузка и восстановление ({period_days} дней)"]

    if load_data:
        trend = load_data.get("load_trend", "н/д")
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        total_week_tss = sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown)
        avg_week_tss = total_week_tss / len(weekly_breakdown) if weekly_breakdown else 0.0
        avg_sessions = (
            sum(float(week.get("session_count", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown
            else 0.0
        )
        intensity = load_data.get("intensity_distribution", {})

        lines.append(f"- Тренд нагрузки: {trend}")
        if avg_week_tss > 0:
            lines.append(f"- Средний недельный TSS: {avg_week_tss:.0f} при {avg_sessions:.1f} тренировок/нед")
        if intensity:
            lines.append(
                "- Распределение интенсивности: "
                f"{intensity.get('low_intensity_percent', 0):.0f}% низк · "
                f"{intensity.get('moderate_intensity_percent', 0):.0f}% умер · "
                f"{intensity.get('high_intensity_percent', 0):.0f}% высок"
            )

    if hrv_data:
        current = hrv_data.get("current_rmssd")
        recent_avg = hrv_data.get("recent_avg_7days")
        baseline = hrv_data.get("baseline_median")
        trend = hrv_data.get("trend_direction")
        recovery_state = hrv_data.get("recovery_state")

        trend_text = _describe_hrv_trend(trend)
        recovery_label = _describe_recovery_state(recovery_state)

        lines.append(
            "- HRV (RMSSD): "
            f"{float(current or 0):.1f} мс (7д {float(recent_avg or 0):.1f} мс, "
            f"база {float(baseline or 0):.1f} мс) — {trend_text}, {recovery_label}"
        )

    return "\n".join(lines)


def _describe_hrv_trend(direction: Optional[str]) -> str:
    mapping = {
        "improving": "тренд растёт",
        "declining": "тренд снижается",
        "stable": "тренд стабильный",
    }
    return mapping.get(direction, "тренд не определён")


def _describe_recovery_state(state: Optional[str]) -> str:
    mapping = {
        "excellent": "восстановление отличное",
        "good": "восстановление хорошее",
        "fair": "восстановление умеренное",
        "poor": "восстановление требует внимания",
    }
    return mapping.get(state, "восстановление под контролем")


def _format_sleep_section(sleep_data: Dict[str, Any]) -> str:
    """Формирует блок про сон."""
    stats = sleep_data.get("statistics", {})
    if not stats:
        return ""

    lines = ["### Сон"]

    avg_hours = stats.get("avg_sleep_hours")
    if avg_hours is not None:
        lines.append(f"- Средняя продолжительность: {avg_hours:.1f} ч")

    avg_score = stats.get("avg_sleep_score")
    if avg_score is not None:
        lines.append(f"- Средняя оценка: {avg_score:.0f}/100")

    avg_efficiency = stats.get("avg_sleep_efficiency")
    if avg_efficiency is not None:
        lines.append(f"- Эффективность: {avg_efficiency:.1f}%")

    lines.append(f"- Текущее качество: {stats.get('current_sleep_quality', 'н/д')}")

    return "\n".join(lines)


def _generate_progress_recommendations(
    compare_data: Optional[Dict[str, Any]],
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    sleep_data: Optional[Dict[str, Any]],
) -> List[str]:
    """Создаёт список рекомендуемых действий на основе данных."""
    recs: List[str] = []

    if compare_data:
        comparison = compare_data.get("comparison", {}) or {}
        tss_change = comparison.get("tss_change")
        duration_change = comparison.get("volume_change")
        activity_change = comparison.get("activity_count_change")

        if isinstance(tss_change, (int, float)):
            if tss_change < -40:
                recs.append("Верни одну интервальную сессию средней интенсивности, чтобы остановить спад нагрузки.")
            elif tss_change > 60:
                recs.append("Сохраняй объём, но закладывай лёгкий день после тяжёлых тренировок — нагрузка растёт.")

        if isinstance(duration_change, (int, float)) and duration_change < -120:
            recs.append("Добавь длительную тренировку на выносливость (60–75 мин), чтобы подтянуть объём.")

        if isinstance(activity_change, (int, float)) and activity_change < 0:
            recs.append("Планируй минимум 5 качественных сессий в неделю, чтобы удержать частоту тренировок.")

    if load_data:
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        avg_week_tss = (
            sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown
            else 0.0
        )
        trend = (load_data.get("load_trend") or "").lower()
        intensity = load_data.get("intensity_distribution", {})

        if avg_week_tss > 380:
            recs.append("Нагрузка за месяц высокая — планируй день восстановления после каждой тяжёлой сессии.")
        elif avg_week_tss < 220 and (trend in ("снижение", "низкий") or "decreasing" in trend):
            recs.append("Добавь интервальную работу средней интенсивности, чтобы вернуть растущий тренд нагрузки.")

        high_intensity = intensity.get("high_intensity_percent")
        if isinstance(high_intensity, (int, float)) and high_intensity < 10 and avg_week_tss >= 250:
            recs.append("Увеличь долю высокоинтенсивных блоков до 12–15%, чтобы ускорить прогресс.")

    if hrv_data:
        current = hrv_data.get("current_rmssd")
        baseline = hrv_data.get("baseline_median")
        if isinstance(current, (int, float)) and isinstance(baseline, (int, float)) and baseline > 0:
            deviation = (current - baseline) / baseline * 100
            if deviation < -5:
                recs.append("HRV ниже базы — включи активное восстановление и удлини сон на 30–45 минут.")
            elif deviation > 8:
                recs.append("HRV стабильно высокий — можно добавить качественную интервальную работу.")

    if sleep_data and sleep_data.get("has_data"):
        stats = sleep_data.get("statistics", {})
        avg_hours = stats.get("avg_sleep_hours")
        if isinstance(avg_hours, (int, float)) and avg_hours < 7:
            recs.append("Повысь среднюю продолжительность сна до 7–7.5 ч, это ускорит восстановление.")

    unique_recs: List[str] = []
    seen = set()
    for rec in recs:
        if rec not in seen:
            unique_recs.append(rec)
            seen.add(rec)
        if len(unique_recs) >= 3:
            break

    if not unique_recs:
        unique_recs.append("Готов помочь составить персональный план — просто напомни, какие цели приоритетны.")

    return unique_recs


def _filter_progress_sections(text: str) -> str:
    """Удаляет инструментальные блоки, оставляя только прогресс и свободный текст."""
    if not text or not text.strip():
        return ""

    import re

    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    kept: List[str] = []

    for section in sections:
        stripped = section.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            if "прогресс" in stripped.lower():
                kept.append(stripped)
        else:
            kept.append(stripped)

    return "\n\n".join(kept).strip()


show_ai_coaching = render_ai_coaching_page
show_ai_chat = render_ai_chat_page
