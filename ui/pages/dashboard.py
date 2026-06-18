"""Dashboard page renderer and helpers."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import streamlit as st

from models.coach_explainability import (
    build_coach_explainability_summary,
    build_operational_response_contract,
)
from models.planning_checkpoints import (
    build_planning_checkpoint,
    summarize_execution_feedback_transition,
    summarize_planning_checkpoint,
)
from models.planning_execution import rebuild_goal_plan_with_adjustment
from services import demo_mode as demo_mode_service
from services.data_cache import load_activities, load_hrv, load_sleep
from state import StateManager
from ui.theme import get_plotly_theme


logger = logging.getLogger(__name__)

TRAINING_STATUS_TITLES = {
    "PRODUCTIVE": "Продуктивно",
    "UNPRODUCTIVE": "Непродуктивно",
    "RECOVERY": "Восстановление",
    "MAINTAINING": "Поддержание",
    "DETRAINING": "Потеря формы",
    "PEAK": "Пик",
    "BASE": "База",
    "BUILD": "Билд",
    "OVERREACHING": "Перегрузка",
    "IMPROVING": "Улучшение",
}

TRAINING_STATUS_COLORS = {
    "PRODUCTIVE": "#10B981",
    "MAINTAINING": "#3B82F6",
    "BASE": "#6366F1",
    "BUILD": "#F59E0B",
    "PEAK": "#8B5CF6",
    "RECOVERY": "#22D3EE",
    "OVERREACHING": "#F97316",
    "UNPRODUCTIVE": "#EF4444",
    "DETRAINING": "#F97316",
}

ACWR_STATUS_STYLES = {
    "OPTIMAL": {"label": "Оптимально", "color": "#10B981"},
    "BALANCED": {"label": "Баланс", "color": "#10B981"},
    "LOW": {"label": "Ниже нормы", "color": "#F59E0B"},
    "VERY_LOW": {"label": "Сильно ниже нормы", "color": "#F97316"},
    "HIGH": {"label": "Выше нормы", "color": "#F97316"},
    "VERY_HIGH": {"label": "Сильно выше нормы", "color": "#EF4444"},
}

EXECUTION_FEEDBACK_LABELS = {
    "completed": "Выполнено по плану",
    "skipped": "Пропущены сессии",
    "reduced": "Нагрузка урезана",
    "unavailable": "Неделя ограничена",
}


def render_dashboard_page(
    state: StateManager,
    on_sync: Callable[[int], None],
) -> None:
    """Render the dashboard page."""
    from utils.modern_ui import ModernUI

    database = state.database

    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    ModernUI.show_horizontal_nav("Dashboard")

    theme = ModernUI.get_theme()
    badge_bg_light = "rgba(232,240,255,0.8)"
    badge_bg_dark = theme["surface_light"]
    badge_text_color = theme["text_primary"]
    badge_border = theme["metric_border"]

    activities_df = load_activities(30)
    if activities_df.empty:
        _render_empty_dashboard_state(state, on_sync)
        return

    st.title("🏃‍♂️ Статус тренировок")

    if demo_mode_service.is_demo_mode(state):
        st.info("🎮 Вы просматриваете демо-режим. Подключите Garmin, чтобы заменить sample data реальными тренировками и синхронизацией.")

    current_status = _calculate_current_status()
    latest_training_status = _get_latest_training_status(database)

    training_status_code = (latest_training_status.get("training_status") or "").upper()
    training_status_display = TRAINING_STATUS_TITLES.get(
        training_status_code,
        training_status_code or "Нет данных",
    )
    training_load_7d = latest_training_status.get("training_load_7d")
    training_load_chronic = latest_training_status.get("training_load_chronic")
    garmin_readiness = latest_training_status.get("training_readiness")
    if garmin_readiness is None or pd.isna(garmin_readiness):
        garmin_readiness = None
    acwr_status_value = (latest_training_status.get("acwr_status") or "").upper()
    acwr_percent = latest_training_status.get("acwr_percent")
    training_feedback_text = latest_training_status.get("training_feedback")
    if not training_feedback_text and latest_training_status.get("training_feedback_code"):
        training_feedback_text = latest_training_status["training_feedback_code"].replace("_", " ").title()
    balance_feedback_text = latest_training_status.get("training_balance_feedback")
    if not balance_feedback_text and latest_training_status.get("training_balance_feedback_code"):
        balance_feedback_text = latest_training_status["training_balance_feedback_code"].replace("_", " ").title()
    training_since_date = latest_training_status.get("training_since_date")
    last_primary_sync_date = latest_training_status.get("last_primary_sync_date")

    if current_status.get("critical_status"):
        st.error(f"🚨 {current_status['critical_status']}")
        if current_status.get("critical_action"):
            st.info(f"💡 Рекомендация: {current_status['critical_action']}")

        if current_status["tsb"] < -30:
            st.markdown(
                """
            <div class="critical-alert">
                <h3>🛌 Немедленные действия при переутомлении:</h3>
                <ul>
                    <li>• Полный отдых 2-3 дня (никаких тренировок)</li>
                    <li>• Увеличьте продолжительность сна до 8+ часов</li>
                    <li>• Легкие прогулки или стретчинг максимум</li>
                    <li>• Обратите внимание на питание и гидратацию</li>
                    <li>• Рассмотрите массаж или физиотерапию</li>
                </ul>
            </div>
            """,
                unsafe_allow_html=True,
            )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        tsb_value = current_status.get("tsb", 0)
        fig_tsb = ModernUI.create_circular_indicator(tsb_value, 100, "TSB", f"{tsb_value:.1f}", "#10B981")
        st.plotly_chart(fig_tsb, width="stretch")
        badge_bg = badge_bg_dark if theme["is_dark"] else badge_bg_light
        badge_style = (
            f"background: {badge_bg};"
            f" color: {badge_text_color}; padding: 4px 8px; border-radius: 12px;"
            f" font-size: 11px; display: inline-block;"
        )
        if theme["is_dark"]:
            badge_style += f" border: 1px solid {badge_border};"
        st.markdown(
            f'<div style="text-align: center;"><span style="{badge_style}">Training Stress Balance<br>Тренировочный стресс баланс</span></div>',
            unsafe_allow_html=True,
        )

    with col2:
        ctl_value = current_status.get("ctl", 0)
        fig_ctl = ModernUI.create_circular_indicator(ctl_value, 150, "CTL", f"{ctl_value:.1f}", "#10B981")
        st.plotly_chart(fig_ctl, width="stretch")
        st.markdown(
            f'<div style="text-align: center;"><span style="{badge_style}">Chronic Training Load<br>Хроническая тренировочная нагрузка</span></div>',
            unsafe_allow_html=True,
        )

    with col3:
        status_color = TRAINING_STATUS_COLORS.get(training_status_code, theme["text_primary"])
        load_text = f"{float(training_load_7d):.0f}" if training_load_7d is not None and not pd.isna(training_load_7d) else "—"
        chronic_text = f"{float(training_load_chronic):.0f}" if training_load_chronic is not None and not pd.isna(training_load_chronic) else "—"
        load_ratio_value = latest_training_status.get("load_ratio")
        load_ratio_text = f"{float(load_ratio_value):.2f}" if load_ratio_value is not None and not pd.isna(load_ratio_value) else "—"
        acwr_style = ACWR_STATUS_STYLES.get(acwr_status_value)
        load_ratio_color = acwr_style["color"] if acwr_style else theme["text_primary"]
        acwr_label = acwr_style["label"] if acwr_style else (acwr_status_value.title() if acwr_status_value else "")
        acwr_suffix = f"({float(acwr_percent):.0f}%)" if acwr_percent is not None and not pd.isna(acwr_percent) else ""
        status_date = latest_training_status.get("date")
        caption_parts = _build_status_caption_parts(status_date, training_since_date, last_primary_sync_date)
        feedback_messages = []
        if training_feedback_text:
            feedback_messages.append(training_feedback_text)
        if balance_feedback_text and balance_feedback_text != training_feedback_text:
            feedback_messages.append(balance_feedback_text)
        load_ratio_details = {
            "label": "Load ratio",
            "value": load_ratio_text,
            "color": load_ratio_color,
            "badge": acwr_label,
            "suffix": acwr_suffix,
        }
        ModernUI.training_status_card(
            title="Статус тренировки",
            status_text=training_status_display,
            status_color=status_color,
            metrics=[
                ("Нагрузка 7д", load_text),
                ("Хроническая", chronic_text),
            ],
            load_ratio=load_ratio_details,
            feedback=feedback_messages,
        )
        if caption_parts:
            st.caption(" • ".join(caption_parts))
        ModernUI.training_status_description()

    with col4:
        readiness_fallback = current_status.get("readiness", 0) or 0
        readiness_value = garmin_readiness if garmin_readiness is not None else readiness_fallback
        try:
            readiness_value = float(readiness_value)
        except (ValueError, TypeError):
            readiness_value = 0.0
        readiness_value = max(0.0, min(100.0, readiness_value))
        readiness_source = "Garmin" if garmin_readiness is not None else "AI индекс"
        readiness_subtitle = f"{readiness_value:.0f}% • {readiness_source}"
        readiness_color = "#3B82F6" if garmin_readiness is not None else "#8B5CF6"
        fig_readiness = ModernUI.create_circular_indicator(
            readiness_value,
            100,
            "Readiness",
            readiness_subtitle,
            readiness_color,
        )
        st.plotly_chart(fig_readiness, width="stretch")
        readiness_bg = badge_bg_dark if theme["is_dark"] else "rgba(59,130,246,0.85)"
        readiness_style = (
            f"background: {readiness_bg}; color: {badge_text_color if theme['is_dark'] else '#FFFFFF'};"
            f" padding: 4px 8px; border-radius: 12px; font-size: 11px; display: inline-block;"
        )
        if theme["is_dark"]:
            readiness_style += f" border: 1px solid {badge_border};"
        st.markdown(
            f'<div style="text-align: center;"><span style="{readiness_style}">Готовность</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br><br>", unsafe_allow_html=True)

    recommendations = current_status.get("recommendations", [])
    if recommendations:
        ModernUI.ai_recommendation_panel(recommendations)

    _render_coach_briefing(state, current_status)
    _render_recent_planning_checkpoint(state)
    _render_execution_feedback_loop(state)
    _render_last_sync_handoff(state, current_status, on_sync)
    _render_primary_next_step(state, current_status, on_sync)
    _render_quick_actions(state, current_status, on_sync)
    ModernUI.show_weekly_training_calendar(activities_df)
    _render_compact_analytics(activities_df, latest_training_status)


def _render_empty_dashboard_state(state: StateManager, on_sync: Callable[[int], None]) -> None:
    st.info("👋 Добро пожаловать в AI Trainer!")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🚀 Быстрый старт")
        st.markdown("")
        st.markdown("1. **Подключитесь к Garmin** (уже выполнено ✅)")
        st.markdown("2. **Синхронизируйте данные** - загрузите тренировки")
        st.markdown("3. **Изучите метрики** - TSS, HRV, сон")
        st.markdown("4. **Получите рекомендации** от AI коуча")

        if st.button("🔄 Синхронизировать данные", type="primary", width="stretch"):
            on_sync(30)

    with col2:
        st.markdown("### 💡 Что умеет AI Trainer?")
        st.markdown("")
        st.markdown("- 📊 Анализ тренировочной нагрузки")
        st.markdown("- 💓 Мониторинг восстановления по HRV")
        st.markdown("- 😴 Оценка качества сна")
        st.markdown("- 🤖 Персональные рекомендации AI")
        st.markdown("- 📈 Планирование тренировок")

        if st.button("🎮 Запустить демо-режим", width="stretch"):
            result = demo_mode_service.activate_demo_mode(state)
            st.success(
                "✅ Демо-режим активирован: "
                f"{result['activities']} активностей и sample metrics для dashboard."
            )
            st.rerun()

    st.markdown("---")
    st.caption("💡 **Совет:** Синхронизируйте последние 30 дней тренировок или временно откройте продукт на sample dataset.")


def _calculate_current_status() -> dict[str, Any]:
    activities_df = load_activities(30)
    hrv_df = load_hrv(90)
    sleep_df = load_sleep(7)

    status: dict[str, Any] = {
        "critical_status": None,
        "critical_action": None,
        "recommendations": [],
        "tsb": 0,
        "hrv": 0,
        "readiness": 0,
        "ctl": 0,
        "trends": {},
    }

    if not activities_df.empty:
        from models.banister import BanisterModel

        banister = BanisterModel()
        tss_data = []
        dates = []

        for _, row in activities_df.iterrows():
            tss_val = row.get("tss")
            if pd.isna(tss_val):
                tss_val = 0
            tss_data.append(float(tss_val or 0))
            dates.append(row["date"])

        current_metrics = banister.get_current_metrics(tss_data, dates)
        status["tsb"] = current_metrics.get("tsb", 0)
        status["ctl"] = current_metrics.get("ctl", 0)
        status["atl"] = current_metrics.get("atl", 0)

        if status["tsb"] < -30:
            status["critical_status"] = "Критическое переутомление"
            status["critical_action"] = "Полный отдых 2-3 дня без тренировок"
            status["recommendations"].extend(
                [
                    {
                        "title": "🚨 Немедленный отдых",
                        "description": "TSB критически низкий (-30+). Организм в состоянии переутомления.",
                        "priority": "high",
                    },
                    {
                        "title": "😴 Качество сна",
                        "description": "Увеличьте сон до 8-9 часов, соблюдайте режим.",
                        "priority": "high",
                    },
                    {
                        "title": "💧 Восстановление",
                        "description": "Массаж, баня, легкие прогулки. Никаких интенсивных нагрузок.",
                        "priority": "medium",
                    },
                ]
            )
        elif status["tsb"] < -20:
            status["critical_status"] = "Сильная усталость"
            status["critical_action"] = "Только легкие восстановительные тренировки в Зоне 1"
            status["recommendations"].extend(
                [
                    {
                        "title": "🔄 Активное восстановление",
                        "description": "TSB -20 до -30. Только тренировки в аэробной зоне 1.",
                        "priority": "high",
                    },
                    {
                        "title": "🍎 Питание",
                        "description": "Увеличьте потребление белка и углеводов для восстановления.",
                        "priority": "medium",
                    },
                ]
            )
        elif status["tsb"] > 5:
            status["recommendations"].extend(
                [
                    {
                        "title": "🚀 Пиковая форма!",
                        "description": "TSB выше +5. Отличное время для соревнований или тестов.",
                        "priority": "low",
                    },
                    {
                        "title": "🎯 Интенсивные тренировки",
                        "description": "Можно проводить FTP-тесты, интервалы, темповые работы.",
                        "priority": "low",
                    },
                ]
            )
        else:
            status["recommendations"].append(
                {
                    "title": "💪 Стандартный режим",
                    "description": "TSB в норме. Поддерживайте текущий объем тренировок.",
                    "priority": "low",
                }
            )

    if not hrv_df.empty:
        latest_hrv = hrv_df.iloc[0]["rmssd"] if pd.notna(hrv_df.iloc[0]["rmssd"]) else 0
        baseline_hrv = hrv_df["rmssd"].mean()
        status["hrv"] = latest_hrv

        try:
            from models.hrv_analyzer import HRVAnalyzer

            advanced_score, info = HRVAnalyzer.recovery_score_advanced(hrv_df)
            if advanced_score is not None:
                status["hrv_advanced"] = {"score": advanced_score, "info": info}
        except Exception:
            pass

        if len(hrv_df) >= 3:
            recent_trend = hrv_df.head(3)["rmssd"].ffill().pct_change().mean() * 100
            status["trends"]["hrv"] = recent_trend

        if latest_hrv < baseline_hrv * 0.8 and status["critical_status"] is None:
            status["critical_status"] = "Низкий HRV - стресс или недовосстановление"
            status["critical_action"] = "Проверьте качество сна и уровень стресса"
            status["recommendations"].append(
                {
                    "title": "💓 Низкий HRV",
                    "description": f"HRV ({latest_hrv:.1f}) ниже базового ({baseline_hrv:.1f}) на 20%+",
                    "priority": "medium",
                }
            )

        if latest_hrv < 30:
            status["recommendations"].append(
                {
                    "title": "⚠️ HRV требует внимания",
                    "description": "Низкая вариабельность сердечного ритма. Фокус на восстановлении.",
                    "priority": "medium",
                }
            )
        elif latest_hrv > 50:
            status["recommendations"].append(
                {
                    "title": "✨ Отличный HRV",
                    "description": "Высокая вариабельность - организм готов к нагрузкам.",
                    "priority": "low",
                }
            )

    if not sleep_df.empty or not hrv_df.empty:
        try:
            from data.data_processor_phase1 import Phase1DataProcessor

            latest_sleep = {}
            latest_hrv_entry = {}
            if not sleep_df.empty:
                latest_sleep = sleep_df.sort_values("date", ascending=False).iloc[0].to_dict()
            if not hrv_df.empty:
                latest_hrv_entry = hrv_df.sort_values("date", ascending=False).iloc[0].to_dict()

            readiness_data = Phase1DataProcessor.calculate_comprehensive_readiness(
                latest_sleep,
                latest_hrv_entry,
                {},
                {},
            )

            if readiness_data and "readiness_score" in readiness_data:
                status["readiness"] = readiness_data["readiness_score"]
        except Exception:
            if status["hrv"] > 40 and status["tsb"] > -10:
                status["readiness"] = 80
            elif status["hrv"] > 30 and status["tsb"] > -20:
                status["readiness"] = 60
            else:
                status["readiness"] = 40

    logger.debug("Текущий статус: %s", status)
    return status


def _get_latest_training_status(database: Any) -> dict[str, Any]:
    training_status_df = database.get_training_status_history(days=30)
    if isinstance(training_status_df, pd.DataFrame) and not training_status_df.empty:
        return training_status_df.sort_values("date", ascending=False).iloc[0].to_dict()
    return {}


def _build_status_caption_parts(
    status_date: Any,
    training_since_date: Any,
    last_primary_sync_date: Any,
) -> list[str]:
    caption_parts: list[str] = []

    if status_date is not None and not pd.isna(status_date):
        try:
            caption_parts.append(f"Обновлено: {_format_date(status_date, 'display')}")
        except Exception:
            pass
    if training_since_date:
        try:
            caption_parts.append(f"С {_format_date(training_since_date, 'display')}")
        except Exception:
            caption_parts.append(f"С {training_since_date}")
    if last_primary_sync_date and last_primary_sync_date != status_date:
        try:
            caption_parts.append(f"Синхронизировано: {_format_date(last_primary_sync_date, 'display')}")
        except Exception:
            caption_parts.append(f"Синхронизировано: {last_primary_sync_date}")

    return caption_parts


def _render_quick_actions(
    state: StateManager,
    current_status: dict[str, Any],
    on_sync: Callable[[int], None],
) -> None:
    from utils.modern_ui import ModernUI

    st.markdown("### ⚡ Быстрые действия")

    try:
        tsb_val = float(current_status.get("tsb", 0) or 0)
    except (ValueError, TypeError):
        tsb_val = 0.0

    if tsb_val < -30:
        intensity_status = "danger"
        intensity_label = "🔴 Отдых"
        intensity_desc = "Полный отдых и восстановление — избегайте тренировок."
    elif tsb_val < -20:
        intensity_status = "warning"
        intensity_label = "🟡 Очень легко"
        intensity_desc = "Только восстановительные сессии в Zone 1 и мягкий сон."
    elif tsb_val < -10:
        intensity_status = "warning"
        intensity_label = "🟠 Легко"
        intensity_desc = "Аэробные тренировки в Zone 1-2, избегайте интенсивных блоков."
    elif tsb_val < 5:
        intensity_status = "success"
        intensity_label = "🟢 Средне"
        intensity_desc = "Можно выполнять стандартные тренировки вплоть до Zone 4."
    else:
        intensity_status = "success"
        intensity_label = "🚀 Высоко"
        intensity_desc = "Готовность высокая — подключайте интенсивные интервалы и VO₂max."

    ModernUI.status_card(
        "Интенсивность сегодня",
        intensity_label,
        intensity_status,
        description=intensity_desc,
    )

    primary_action = _choose_primary_next_step(state, current_status)
    primary_action_key = primary_action["action"]
    actions = []

    try:
        tsb_val = float(current_status.get("tsb", 0))
        if tsb_val < -20:
            actions.append(
                {
                    "icon": "😴",
                    "title": "План восстановления",
                    "desc": "Составить программу активного отдыха",
                    "action": "recovery_plan",
                }
            )
        elif tsb_val > 10:
            actions.append(
                {
                    "icon": "🔥",
                    "title": "Интенсивная тренировка",
                    "desc": "Использовать пиковую форму",
                    "action": "intense_workout",
                }
            )
    except (ValueError, TypeError):
        pass

    try:
        hrv_val = float(current_status.get("hrv", 0)) if current_status.get("hrv") else 0
        if hrv_val > 0 and hrv_val < 30:
            actions.append(
                {
                    "icon": "💓",
                    "title": "HRV-анализ",
                    "desc": "Детальный разбор вариабельности",
                    "action": "hrv_analysis",
                }
            )
    except (ValueError, TypeError):
        pass

    actions.extend(
        [
            {"icon": "📊", "title": "Синхронизация", "desc": "Обновить данные", "action": "sync"},
            {"icon": "🤖", "title": "AI Коуч", "desc": "Персональные рекомендации", "action": "ai_chat"},
            {"icon": "📈", "title": "Планирование", "desc": "Настроить тренировки", "action": "planning"},
        ]
    )
    actions = [action for action in actions if action["action"] != primary_action_key]

    st.markdown('<div class="quick-actions-grid">', unsafe_allow_html=True)

    cols = st.columns(3)
    for index, action in enumerate(actions[:6]):
        with cols[index % 3]:
            if st.button(
                f"{action['icon']} {action['title']}",
                help=action["desc"],
                width="stretch",
            ):
                _handle_quick_action(state, action["action"], on_sync, current_status)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_primary_next_step(
    state: StateManager,
    current_status: dict[str, Any],
    on_sync: Callable[[int], None],
) -> None:
    next_step = _choose_primary_next_step(state, current_status)

    st.markdown("### 🎯 Следующий шаг")
    st.info(f"**{next_step['title']}**\n\n{next_step['desc']}\n\n{next_step['reason']}")
    if st.button(
        f"{next_step['icon']} {next_step['button']}",
        key=f"primary_next_step_{next_step['action']}",
        type="primary",
        width="stretch",
    ):
        _handle_quick_action(state, next_step["action"], on_sync, current_status)


def _render_coach_briefing(
    state: StateManager,
    current_status: dict[str, Any],
) -> None:
    briefing = _build_dashboard_explainability_summary(state, current_status)

    st.markdown("### 🧠 Почему сегодня такой фокус")
    with st.container(border=True):
        st.markdown(f"**{briefing['short_title']}**")
        st.write(briefing["description"])
        st.write(f"**Сегодня:** {briefing['today_action']}")
        st.write(f"**Ближайшие 2-3 дня:** {briefing['next_window']}")
        st.write(f"**Следить за:** {briefing['watchout']}")
        if briefing.get("plan_context"):
            st.caption(briefing["plan_context"])
        st.caption(briefing["reason"])
        for signal in briefing["signals"][:5]:
            st.write(f"• {signal}")


def _render_recent_planning_checkpoint(state: StateManager) -> None:
    checkpoint_summary = summarize_planning_checkpoint(getattr(state, "latest_planning_checkpoint", None))
    if checkpoint_summary is None:
        return

    st.markdown("### 🗂️ Последний planning checkpoint")
    with st.container(border=True):
        st.markdown(f"**{checkpoint_summary['title']}**")
        if checkpoint_summary["headline"]:
            st.write(checkpoint_summary["headline"])
        if checkpoint_summary["created_at_label"]:
            st.caption(f"Сохранён: {checkpoint_summary['created_at_label']}")
        st.write(
            f"**Checkpoint:** {checkpoint_summary['plan_adjustment_label']} · "
            f"Пик {checkpoint_summary['peak_tss']} TSS · Сумма {checkpoint_summary['total_tss']} TSS"
        )
        if checkpoint_summary.get("near_term_edit"):
            st.write(f"**Ручная правка:** {checkpoint_summary['near_term_edit']['compact_label']}")
            st.write(f"**Оценка правки:** {checkpoint_summary['near_term_edit']['risk_badge']}")
            if checkpoint_summary["near_term_edit"].get("risk_level") != "low":
                st.caption(checkpoint_summary["near_term_edit"]["risk_guardrail"])
        if checkpoint_summary["plan_adjustment_weeks"] > 0:
            st.write(f"**Горизонт:** {checkpoint_summary['plan_adjustment_weeks']} нед.")
        if checkpoint_summary["interruption_label"] != "Нет":
            st.write(f"**Ограничение:** {checkpoint_summary['interruption_label']}")
        if checkpoint_summary["load_state_label"]:
            st.write(f"**Стартовое состояние:** {checkpoint_summary['load_state_label']}")
        history = [
            item
            for item in (
                summarize_planning_checkpoint(record)
                for record in getattr(state, "planning_checkpoint_history", [])[1:3]
            )
            if item is not None
        ]
        if history:
            st.caption("Недавние checkpoints")
            for item in history:
                when = f" ({item['created_at_label']})" if item["created_at_label"] else ""
                suffix = ""
                if item.get("near_term_edit"):
                    suffix = f" · ручная правка: {item['near_term_edit']['delta_label']}"
                    if item["near_term_edit"].get("risk_level") != "low":
                        suffix += f" · {item['near_term_edit']['risk_badge']}"
                st.write(f"• {item['title']}: {item['plan_adjustment_label']}{suffix}{when}")


def _build_execution_feedback_result(
    previous_checkpoint: dict[str, Any] | None,
    current_checkpoint: dict[str, Any] | None,
) -> dict[str, Any] | None:
    return summarize_execution_feedback_transition(
        previous_checkpoint,
        current_checkpoint,
    )


def _render_execution_feedback_loop(state: StateManager) -> None:
    checkpoint_summary = summarize_planning_checkpoint(getattr(state, "latest_planning_checkpoint", None))
    goal_plan_context = getattr(state, "resolved_goal_plan_context", None)
    if checkpoint_summary is None or not isinstance(goal_plan_context, dict) or not goal_plan_context:
        return

    status_options = list(EXECUTION_FEEDBACK_LABELS.values())
    reverse_labels = {label: key for key, label in EXECUTION_FEEDBACK_LABELS.items()}

    st.markdown("### ♻️ Факт выполнения")
    with st.container(border=True):
        st.caption("Зафиксируйте, как неделя прошла в реальности. AI Trainer локально пересчитает ближайший горизонт и сохранит новый planning checkpoint.")
        status_label = st.selectbox(
            "Что произошло по факту",
            options=status_options,
            index=0,
            key="dashboard_execution_feedback_status",
        )
        status = reverse_labels.get(status_label, "completed")
        weeks = st.slider(
            "Горизонт локального пересчёта",
            min_value=1,
            max_value=2,
            value=1,
            disabled=status == "completed",
            key="dashboard_execution_feedback_weeks",
        )

        missed_sessions = 0
        reduced_load_share = 0.70
        if status == "skipped":
            missed_sessions = st.slider(
                "Сколько сессий реально выпало",
                min_value=1,
                max_value=max(1, int(goal_plan_context.get("constraint_summary", {}).get("available_day_count", 1) or 1)),
                value=1,
                key="dashboard_execution_feedback_missed_sessions",
            )
        elif status == "reduced":
            reduced_percent = st.slider(
                "Сколько % нагрузки реально осталось",
                min_value=35,
                max_value=95,
                value=70,
                step=5,
                key="dashboard_execution_feedback_reduced_percent",
            )
            reduced_load_share = reduced_percent / 100.0
        elif status == "unavailable":
            st.caption("Используйте этот вариант, если неделя фактически сжалась из-за поездки, болезни или жёсткого внешнего ограничения.")
        else:
            st.caption("План сохранит execution checkpoint «выполнено по плану» без дополнительного снижения нагрузки.")

        result = getattr(state, "last_execution_feedback_result", None)
        if isinstance(result, dict):
            st.success(
                f"Последний execution checkpoint: {result['plan_adjustment_label']} · "
                f"Сумма {result['total_tss']} TSS ({result['total_delta']:+d}) · "
                f"Пик {result['peak_tss']} TSS ({result['peak_delta']:+d})"
            )
            if result.get("created_at_label"):
                st.caption(f"Сохранён: {result['created_at_label']}")

        if st.button(
            "♻️ Применить локальный replan",
            key="dashboard_apply_execution_feedback",
            type="primary",
            width="stretch",
        ):
            previous_checkpoint = getattr(state, "latest_planning_checkpoint", None)
            updated_goal_plan = rebuild_goal_plan_with_adjustment(
                goal_plan_context,
                {
                    "status": status,
                    "weeks": weeks if status != "completed" else 1,
                    "missed_sessions": missed_sessions,
                    "reduced_load_share": reduced_load_share,
                },
            )
            state.goal_plan = updated_goal_plan
            saved_checkpoint = state.database.save_planning_checkpoint(
                build_planning_checkpoint(updated_goal_plan)
            )
            state.latest_planning_checkpoint = saved_checkpoint
            state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=3)
            state.last_execution_feedback_result = _build_execution_feedback_result(
                previous_checkpoint,
                saved_checkpoint,
            )
            st.rerun()


def _render_last_sync_handoff(
    state: StateManager,
    current_status: dict[str, Any],
    on_sync: Callable[[int], None],
) -> None:
    sync_status = getattr(state, "last_sync_status", None)
    if not isinstance(sync_status, dict) or not sync_status:
        return

    next_step = _choose_primary_next_step(state, current_status)
    handoff = _build_sync_handoff_copy(sync_status, next_step)
    severity = handoff["severity"]
    message = f"**{handoff['title']}**\n\n{handoff['summary']}"

    if severity == "warning":
        st.warning(message)
    elif severity == "error":
        st.error(message)
    elif severity == "success":
        st.success(message)
    else:
        st.info(message)

    highlights = handoff.get("highlights", [])
    if highlights:
        st.caption("Что обновилось")
        for item in highlights:
            st.markdown(f"- {item}")

    notices = handoff.get("notices", [])
    if notices:
        st.caption("Замечания")
        for item in notices:
            st.markdown(f"- {item}")

    synced_at_label = handoff.get("synced_at_label")
    if synced_at_label:
        st.caption(f"Последняя синхронизация: {synced_at_label}")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button(
            f"{next_step['icon']} {handoff['button_label']}",
            key="post_sync_next_action",
            type="primary",
            width="stretch",
        ):
            state.last_sync_status = None
            _handle_quick_action(state, next_step["action"], on_sync, current_status)
    with col2:
        if st.button(
            "Скрыть",
            key="dismiss_last_sync_status",
            width="stretch",
        ):
            state.last_sync_status = None
            st.rerun()


def _build_sync_handoff_copy(
    sync_status: dict[str, Any],
    next_step: dict[str, str],
) -> dict[str, Any]:
    synced_at = sync_status.get("synced_at")
    synced_at_label = None
    if synced_at:
        try:
            synced_at_label = _format_date(datetime.fromisoformat(str(synced_at)), "display")
        except ValueError:
            synced_at_label = str(synced_at)

    return {
        "severity": sync_status.get("severity", "info"),
        "title": sync_status.get("title", "Последняя синхронизация"),
        "summary": sync_status.get("summary", "Данные Garmin обновлены."),
        "highlights": sync_status.get("highlights", []),
        "notices": sync_status.get("notices", []),
        "synced_at_label": synced_at_label,
        "button_label": next_step["button"],
    }


def _choose_primary_next_step(
    state: StateManager,
    current_status: dict[str, Any],
) -> dict[str, str]:
    summary = _build_dashboard_explainability_summary(state, current_status)
    ai_ready = getattr(state, "ai_coach", None) is not None

    if summary["focus"] == "recovery":
        return {
            "icon": summary["icon"],
            "title": summary["title"],
            "button": summary["dashboard_button"],
            "desc": summary["description"],
            "reason": summary["reason"],
            "action": "recovery_plan",
        }

    if not ai_ready:
        return {
            "icon": "🤖",
            "title": "Подготовьте AI коуча",
            "button": "Открыть AI коучинг",
            "desc": "Данные уже на месте. Следующий полезный шаг — открыть AI coaching и получить персональную интерпретацию текущего состояния.",
            "reason": "Если провайдер уже настроен, коуч подключится автоматически. Иначе вы сразу попадёте в нужное место для настройки.",
            "action": "ai_chat",
        }

    return {
        "icon": summary["icon"],
        "title": "Получите персональную рекомендацию" if summary["focus"] == "form_today" else summary["title"],
        "button": summary["dashboard_button"],
        "desc": summary["description"],
        "reason": summary["reason"],
        "action": "ai_chat",
    }


def _build_dashboard_explainability_summary(
    state: StateManager,
    current_status: dict[str, Any],
) -> dict[str, Any]:
    hrv_val = current_status.get("hrv")
    recovery_state = None
    try:
        if hrv_val and float(hrv_val) < 30:
            recovery_state = "poor"
    except (TypeError, ValueError):
        recovery_state = None

    return build_coach_explainability_summary(
        tsb=current_status.get("tsb"),
        ctl=current_status.get("ctl"),
        atl=current_status.get("atl"),
        readiness=current_status.get("readiness"),
        recovery_state=recovery_state,
        goal_plan=getattr(state, "resolved_goal_plan_context", None),
        execution_feedback=getattr(state, "latest_execution_feedback", None),
    )


def _build_dashboard_ai_handoff(
    state: StateManager,
    current_status: dict[str, Any],
) -> dict[str, Any]:
    summary = _build_dashboard_explainability_summary(state, current_status)
    return {
        "source": "dashboard",
        "icon": summary["icon"],
        "title": summary["title"],
        "button": summary["button"],
        "description": summary["description"],
        "reason": summary["reason"],
        "prompt": summary["prompt"],
        "today_action": summary["today_action"],
        "next_window": summary["next_window"],
        "watchout": summary["watchout"],
        "plan_context": summary.get("plan_context"),
        "signals": list(summary["signals"][:5]),
        "response_contract": build_operational_response_contract(summary),
    }


def _handle_quick_action(
    state: StateManager,
    action: str,
    on_sync: Callable[[int], None],
    current_status: dict[str, Any] | None = None,
) -> None:
    if action == "recovery_plan":
        if current_status is not None:
            state.ai_coach_handoff = _build_dashboard_ai_handoff(state, current_status)
            state.switch_to_chat_tab = True
        state.selected_page = "🤖 AI Коучинг"
        st.rerun()
    elif action == "intense_workout":
        state.selected_page = "📈 Планирование"
        st.rerun()
    elif action == "hrv_analysis":
        state.selected_page = "💓 Анализ HRV"
        st.rerun()
    elif action == "sync":
        on_sync(7)
    elif action == "ai_chat":
        if current_status is not None:
            state.ai_coach_handoff = _build_dashboard_ai_handoff(state, current_status)
            state.switch_to_chat_tab = True
        state.selected_page = "🤖 AI Коучинг"
        st.rerun()
    elif action == "planning":
        state.selected_page = "📈 Планирование"
        st.rerun()


def _render_compact_analytics(
    activities_df: pd.DataFrame,
    training_status_info: dict[str, Any] | None = None,
) -> None:
    with st.expander("📊 Подробная аналитика", expanded=False):
        if activities_df.empty:
            st.info("Нет данных для анализа")
            return

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Активности", len(activities_df))

        with col2:
            st.metric("Дистанция", f"{activities_df['distance_km'].sum():.0f} км")

        with col3:
            st.metric("Время", f"{activities_df['duration_minutes'].sum() / 60:.0f}ч")

        with col4:
            avg_tss = activities_df["tss"].mean() if "tss" in activities_df.columns and activities_df["tss"].notna().any() else 0
            st.metric("Ср. TSS", f"{avg_tss:.0f}")

        col1, col2 = st.columns(2)

        with col1:
            activities_df_copy = activities_df.copy()
            if not pd.api.types.is_datetime64_any_dtype(activities_df_copy["date"]):
                activities_df_copy["date"] = pd.to_datetime(activities_df_copy["date"])

            daily_stats = activities_df_copy.groupby(activities_df_copy["date"].dt.date).agg(
                {"duration_minutes": "sum"}
            ).reset_index()

            from utils.modern_ui import ModernUI

            fig = ModernUI.create_mini_trend_chart(
                daily_stats["duration_minutes"].tolist(),
                "Время тренировок",
            )
            st.plotly_chart(fig, width="stretch")

        with col2:
            sport_dist = activities_df["sport"].value_counts()
            theme = get_plotly_theme()
            fig = px.pie(
                values=sport_dist.values,
                names=sport_dist.index,
                title="Виды спорта",
                template=theme["template"],
            )
            fig.update_layout(
                height=200,
                margin=dict(l=0, r=0, t=30, b=0),
                paper_bgcolor=theme["paper_bgcolor"],
                plot_bgcolor=theme["plot_bgcolor"],
                font_color=theme["font_color"],
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")

        st.markdown("**Последние тренировки:**")
        display_df = activities_df.head(5)[["date", "sport", "duration_minutes", "distance_km", "tss"]].copy()

        if pd.api.types.is_datetime64_any_dtype(display_df["date"]):
            display_df["date"] = display_df["date"].apply(lambda value: _format_date(value, "short"))
        else:
            display_df["date"] = pd.to_datetime(display_df["date"]).apply(lambda value: _format_date(value, "short"))

        display_df["duration_minutes"] = display_df["duration_minutes"].round(0).astype(int)
        display_df["distance_km"] = display_df["distance_km"].round(1)
        display_df.columns = ["Дата", "Спорт", "Мин", "Км", "TSS"]

        st.dataframe(display_df, width="stretch", height=200)

        if training_status_info:
            monthly_rows = []

            monthly_low = training_status_info.get("monthly_load_aerobic_low")
            if monthly_low is not None:
                monthly_rows.append(
                    {
                        "Зона": "Низкоаэробная",
                        "Текущее": _fmt_number(monthly_low),
                        "Цель": _fmt_range(
                            training_status_info.get("monthly_load_aerobic_low_target_min"),
                            training_status_info.get("monthly_load_aerobic_low_target_max"),
                        ),
                    }
                )

            monthly_high = training_status_info.get("monthly_load_aerobic_high")
            if monthly_high is not None:
                monthly_rows.append(
                    {
                        "Зона": "Высокоаэробная",
                        "Текущее": _fmt_number(monthly_high),
                        "Цель": _fmt_range(
                            training_status_info.get("monthly_load_aerobic_high_target_min"),
                            training_status_info.get("monthly_load_aerobic_high_target_max"),
                        ),
                    }
                )

            monthly_ana = training_status_info.get("monthly_load_anaerobic")
            if monthly_ana is not None:
                monthly_rows.append(
                    {
                        "Зона": "Анаэробная",
                        "Текущее": _fmt_number(monthly_ana),
                        "Цель": _fmt_range(
                            training_status_info.get("monthly_load_anaerobic_target_min"),
                            training_status_info.get("monthly_load_anaerobic_target_max"),
                        ),
                    }
                )

            if monthly_rows:
                st.markdown("**Баланс нагрузки Garmin:**")
                monthly_df = pd.DataFrame(monthly_rows)
                st.dataframe(monthly_df, width="stretch", hide_index=True)
                balance_feedback = training_status_info.get("training_balance_feedback")
                if balance_feedback:
                    st.caption(balance_feedback)


def _fmt_number(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_range(min_value: Any, max_value: Any) -> str:
    if min_value is None and max_value is None:
        return "—"
    if min_value is None:
        return f"≤ {_fmt_number(max_value)}"
    if max_value is None:
        return f"≥ {_fmt_number(min_value)}"
    try:
        min_val = float(min_value)
        max_val = float(max_value)
    except (TypeError, ValueError):
        return f"{_fmt_number(min_value)}–{_fmt_number(max_value)}"
    if abs(min_val - max_val) < 1e-3:
        return _fmt_number(min_val)
    return f"{min_val:.0f}–{max_val:.0f}"


def _format_date(date_obj: Any, format_type: str = "display") -> str:
    if pd.isna(date_obj):
        return ""

    if isinstance(date_obj, str):
        try:
            date_obj = pd.to_datetime(date_obj)
        except Exception:
            return date_obj

    if format_type == "display":
        return date_obj.strftime("%d.%m.%Y")
    if format_type == "db":
        return date_obj.strftime("%Y-%m-%d")
    if format_type == "short":
        return date_obj.strftime("%d.%m")
    return str(date_obj)


__all__ = ["render_dashboard_page"]
