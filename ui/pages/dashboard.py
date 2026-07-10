"""Dashboard page renderer and helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any, Callable

import pandas as pd
import plotly.express as px
import streamlit as st

from models.coach_explainability import build_operational_response_contract
from models.dashboard_summary import (
    build_activity_day_tss as _build_activity_day_tss,
    build_dashboard_explainability_summary as _build_dashboard_explainability_summary,
    build_dashboard_summary as _build_dashboard_v2_summary,
    build_plan_day_lookup as _build_plan_day_lookup,
    calculate_current_status as _calculate_current_status_headless,
    choose_primary_next_step as _choose_primary_next_step,
    get_dashboard_goal_plan as _get_dashboard_goal_plan,
    get_latest_training_status as _get_latest_training_status,
)
from models.planning_checkpoints import (
    build_planning_checkpoint,
    summarize_execution_feedback_transition,
    summarize_planning_checkpoint,
    with_checkpoint_provenance,
)
from models.planning_execution import rebuild_goal_plan_with_adjustment
from services import demo_mode as demo_mode_service
from services.data_cache import load_activities, load_hrv, load_sleep
from state import StateManager
from ui.components.execution_feedback import render_execution_feedback_editor
from ui.plotly_theme import get_plotly_theme


logger = logging.getLogger(__name__)


def _calculate_current_status(
    activities_df: pd.DataFrame | None = None,
    hrv_df: pd.DataFrame | None = None,
    sleep_df: pd.DataFrame | None = None,
    training_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load Streamlit caches when needed, then delegate to the headless builder."""
    if activities_df is None:
        activities_df = load_activities(30)
    if hrv_df is None:
        hrv_df = load_hrv(90)
    if sleep_df is None:
        sleep_df = load_sleep(7)
    return _calculate_current_status_headless(
        activities_df,
        hrv_df,
        sleep_df,
        training_status=training_status,
    )


def render_dashboard_page(
    state: StateManager,
    on_sync: Callable[[int], None],
) -> None:
    """Render the dashboard page."""
    from utils.modern_ui import ModernUI

    database = state.database

    if state.use_custom_theme:
        ModernUI.apply_modern_styles(dark_mode=state.dark_mode)

    activities_df = load_activities(30)
    if activities_df.empty:
        _render_empty_dashboard_state(state, on_sync)
        return

    if demo_mode_service.is_demo_mode(state):
        st.info(
            "🎮 Вы просматриваете демо-режим. Подключите Garmin, чтобы заменить sample data "
            "реальными тренировками и синхронизацией."
        )

    latest_training_status = _get_latest_training_status(database)
    current_status = _calculate_current_status(training_status=latest_training_status)

    _render_dashboard_v2_shell(
        state,
        current_status,
        latest_training_status,
        activities_df,
        on_sync,
    )
















def _render_dashboard_v2_shell(
    state: StateManager,
    current_status: dict[str, Any],
    latest_training_status: dict[str, Any],
    activities_df: pd.DataFrame,
    on_sync: Callable[[int], None],
) -> None:
    from utils.modern_ui import ModernUI

    summary = _build_dashboard_v2_summary(
        state,
        current_status,
        latest_training_status,
        activities_df,
    )
    sync_status = getattr(state, "last_sync_status", None)
    sync_summary = ""
    if isinstance(sync_status, dict) and sync_status.get("summary"):
        sync_summary = str(sync_status["summary"])
    ModernUI.render_page_hero(
        "Дашборд",
        sync_summary
        or "Короткая сводка состояния, тренировки на сегодня, недельной нагрузки и следующего действия.",
        eyebrow="Training cockpit",
        meta=f"{summary['today']['date']} · CTL {summary['today']['ctl']} · TSB {summary['today']['tsb']}",
    )

    if current_status.get("critical_status"):
        st.error(f"{current_status['critical_status']}: {current_status.get('critical_action', 'снизьте нагрузку')}")

    ModernUI.render_section_title("Сегодня", "Главная интерпретация готовности без лишней диагностики.")
    today_cols = st.columns([1.45, 0.85, 0.85, 0.85])
    with today_cols[0]:
        ModernUI.render_stat_card(
            "Состояние",
            summary["today"]["state_label"],
            f"HRV: {summary['today']['hrv']}" if summary["today"]["hrv"] else "Сводный coaching signal",
            summary["today"]["tone"],
        )
    with today_cols[1]:
        ModernUI.render_stat_card("Readiness", summary["today"]["readiness"], "0-100", summary["today"]["tone"])
    with today_cols[2]:
        ModernUI.render_stat_card("TSB", summary["today"]["tsb"], "форма / усталость", summary["today"]["tone"])
    with today_cols[3]:
        ModernUI.render_stat_card("CTL", summary["today"]["ctl"], "fitness", "neutral")

    top_cols = st.columns([1.15, 0.85])
    with top_cols[0]:
        ModernUI.render_section_title("Тренировка сегодня")
        ModernUI.render_text_card(
            summary["workout"]["title"],
            summary["workout"]["subtitle"],
            eyebrow=f"{summary['workout']['tss']} TSS",
            tone="planned" if summary["workout"]["tss"] else "rest",
        )
        if st.button(summary["workout"]["button"], key="dashboard_v2_workout_cta", type="primary", width="stretch"):
            _handle_quick_action(state, str(summary["workout"]["action"]), on_sync, current_status)

    with top_cols[1]:
        ModernUI.render_section_title("Неделя")
        week_tone = "warning" if "риск" in summary["week"]["status"] else "success"
        week_status_title = {
            "по плану": "Неделя под контролем",
            "цель недели закрыта": "Цель недели закрыта",
            "риск отставания": "Есть риск отставания",
        }.get(str(summary["week"]["status"]), str(summary["week"]["status"]))
        metric_cols = st.columns(2)
        with metric_cols[0]:
            ModernUI.render_stat_card("Факт", f"{summary['week']['actual_tss']} TSS", "уже выполнено", week_tone)
        with metric_cols[1]:
            ModernUI.render_stat_card("План", f"{summary['week']['planned_tss']} TSS", "цель недели", "neutral")
        ModernUI.render_text_card(
            week_status_title,
            f"Осталось {summary['week']['remaining_tss']} TSS · прогноз {summary['week']['forecast_tss']} TSS.",
            tone=week_tone,
        )

    ModernUI.render_section_title("Следующие 7 дней", "Компактный план без длинных workout descriptions.")
    day_cols = st.columns(7)
    for col, day in zip(day_cols, summary["next_days"]):
        with col:
            ModernUI.render_day_chip(
                day["label"],
                f"{day['tss']} TSS",
                f"{day['sport']} · {day['status_label']}",
                day["status"],
            )

    bottom_cols = st.columns([1, 1])
    with bottom_cols[0]:
        ModernUI.render_section_title("План")
        ModernUI.render_text_card(
            summary["plan"]["title"],
            summary["plan"]["subtitle"],
            tone="success" if summary["plan"]["status"] == "active" else "warning",
        )
        if st.button(summary["plan"]["button"], key="dashboard_v2_plan_cta", width="stretch"):
            state.selected_page = "📈 Планирование"
            st.session_state["planning_workspace_mode"] = "Скорректировать выполнение"
            st.rerun()

    with bottom_cols[1]:
        ModernUI.render_section_title("Следующий шаг")
        ModernUI.render_text_card(
            summary["next_action"]["title"],
            summary["next_action"]["desc"],
            eyebrow="Primary action",
            tone="warning" if summary["next_action"]["action"] == "recovery_plan" else "success",
        )
        if st.button(
            f"{summary['next_action']['icon']} {summary['next_action']['button']}",
            key=f"dashboard_v2_next_action_{summary['next_action']['action']}",
            type="primary",
            width="stretch",
        ):
            _handle_quick_action(state, summary["next_action"]["action"], on_sync, current_status)

    with st.expander("Диагностика Dashboard", expanded=False):
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

    provenance = checkpoint_summary.get("provenance") or {}
    st.markdown("### 🗂️ План")
    with st.container(border=True):
        st.markdown(f"**{checkpoint_summary['title']}**")
        if checkpoint_summary["headline"]:
            st.write(checkpoint_summary["headline"])
        summary_bits = [
            checkpoint_summary["plan_adjustment_label"],
            f"пик {checkpoint_summary['peak_tss']} TSS",
            f"сумма {checkpoint_summary['total_tss']} TSS",
        ]
        if provenance.get("label"):
            summary_bits.append(str(provenance["label"]))
        st.caption(" · ".join(summary_bits))
        if checkpoint_summary.get("execution_reconciliation"):
            execution_reconciliation = checkpoint_summary["execution_reconciliation"]
            st.caption(f"Факт окна: {execution_reconciliation['compact_label']}")
        if checkpoint_summary.get("execution_weekly_review"):
            execution_weekly_review = checkpoint_summary["execution_weekly_review"]
            st.caption(f"Weekly review: {execution_weekly_review['headline']}")
        if checkpoint_summary.get("execution_corrective_microcycle"):
            corrective_microcycle = checkpoint_summary["execution_corrective_microcycle"]
            st.caption(f"Microcycle: {corrective_microcycle['headline']}")
            if corrective_microcycle.get("today_action"):
                st.caption(corrective_microcycle["today_action"])
        if checkpoint_summary.get("execution_adaptation_pressure"):
            adaptation_pressure = checkpoint_summary["execution_adaptation_pressure"]
            st.caption(f"После окна: {adaptation_pressure['compact_label']}")
        if checkpoint_summary.get("near_term_edit"):
            st.caption(f"Ручная правка: {checkpoint_summary['near_term_edit']['compact_label']}")
        if checkpoint_summary["created_at_label"]:
            st.caption(f"Сохранён: {checkpoint_summary['created_at_label']}")
        if st.button("Открыть детали в Planning", key="dashboard_open_planning_checkpoint", width="stretch"):
            state.selected_page = "📈 Планирование"
            st.session_state["planning_workspace_mode"] = "Скорректировать выполнение"
            st.rerun()


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

    result = getattr(state, "last_execution_feedback_result", None)
    st.markdown("### ♻️ Сверка выполнения")
    with st.container(border=True):
        st.markdown("**Dashboard показывает только статус. Ручная сверка живёт в Planning.**")
        st.caption(
            "Так главная страница остаётся обзорной: состояние сегодня, следующий шаг и недельная нагрузка. "
            "Подробный plan/fact и сохранение checkpoint открывайте в Planning."
        )
        plan_cols = st.columns([1, 1])
        with plan_cols[0]:
            if st.button(
                "Открыть Planning → корректировка",
                key="dashboard_open_planning_execution_feedback",
                type="primary",
                width="stretch",
            ):
                state.selected_page = "📈 Планирование"
                st.session_state["planning_workspace_mode"] = "Скорректировать выполнение"
                st.rerun()
        with plan_cols[1]:
            st.checkbox(
                "Показать редактор здесь",
                key="dashboard_execution_feedback_editor_visible",
                help="Оставлено как аварийный fallback; основной поток должен идти через Planning.",
            )

    if isinstance(result, dict):
        st.success(
            f"Последний execution checkpoint: {result['plan_adjustment_label']} · "
            f"Сумма {result['total_tss']} TSS ({result['total_delta']:+d}) · "
            f"Пик {result['peak_tss']} TSS ({result['peak_delta']:+d})"
        )
        if result.get("execution_reconciliation"):
            execution_reconciliation = result["execution_reconciliation"]
            st.caption(
                f"Факт окна: {execution_reconciliation['actual_total_tss']} из "
                f"{execution_reconciliation['planned_total_tss']} TSS · "
                f"{execution_reconciliation['changed_day_count']} дн. изменено"
            )
        if result.get("execution_weekly_review"):
            execution_weekly_review = result["execution_weekly_review"]
            st.caption(
                f"Weekly review: {execution_weekly_review['headline']} · "
                f"{execution_weekly_review['selected_response_label']}"
            )
        if result.get("execution_corrective_microcycle"):
            corrective_microcycle = result["execution_corrective_microcycle"]
            st.caption(f"Microcycle: {corrective_microcycle['headline']}")
        if result.get("execution_adaptation_pressure"):
            adaptation_pressure = result["execution_adaptation_pressure"]
            st.caption(f"После окна: {adaptation_pressure['compact_label']}")
            if corrective_microcycle.get("today_action"):
                st.caption(corrective_microcycle["today_action"])
        if result.get("created_at_label"):
            st.caption(f"Сохранён: {result['created_at_label']}")

    if not st.session_state.get("dashboard_execution_feedback_editor_visible"):
        return

    editor_result = render_execution_feedback_editor(
        goal_plan_context,
        key_prefix="dashboard_execution_feedback",
    )
    if editor_result is not None:
        previous_checkpoint = getattr(state, "latest_planning_checkpoint", None)
        updated_goal_plan = rebuild_goal_plan_with_adjustment(
            goal_plan_context,
            editor_result["plan_adjustment"],
        )
        updated_goal_plan = with_checkpoint_provenance(
            updated_goal_plan,
            source="execution_feedback",
            parent_checkpoint_id=(previous_checkpoint or {}).get("id") if isinstance(previous_checkpoint, dict) else None,
        )
        state.goal_plan = updated_goal_plan
        saved_checkpoint = state.database.save_planning_checkpoint(
            build_planning_checkpoint(updated_goal_plan)
        )
        state.latest_planning_checkpoint = saved_checkpoint
        state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
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
