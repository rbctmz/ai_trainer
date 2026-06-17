"""Entry guidance and handoff helpers for the AI coaching page."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import streamlit as st

from models.coach_explainability import build_coach_explainability_summary
from models.coach_explainability import build_operational_response_contract
from models.planning_checkpoints import summarize_planning_checkpoint
from state import StateManager


WELCOME_MESSAGE = """
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


def _build_ai_coach_explainability_summary(
    data_context: Optional[Dict[str, Any]],
    goal_plan: Optional[Dict[str, Any]] = None,
    execution_feedback: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not data_context or not data_context.get("summary", {}).get("has_data", False):
        return None

    performance_metrics = data_context.get("performance_metrics", {})
    banister_model = performance_metrics.get("banister_model", {}) if performance_metrics.get("has_data") else {}
    hrv_context = data_context.get("hrv", {})
    hrv_stats = hrv_context.get("stats", {}) if hrv_context.get("has_data") else {}
    sleep_context = data_context.get("sleep", {})
    training_status = data_context.get("training_status", {})
    training_latest = training_status.get("latest", {}) if training_status.get("has_data") else {}

    return build_coach_explainability_summary(
        tsb=banister_model.get("tsb"),
        ctl=banister_model.get("ctl"),
        atl=banister_model.get("atl"),
        readiness=training_latest.get("training_readiness"),
        recovery_state=hrv_stats.get("recovery_state"),
        sleep_quality=sleep_context.get("sleep_quality"),
        goal_plan=goal_plan,
        execution_feedback=execution_feedback,
    )


def _choose_recommended_first_prompt(
    data_context: Optional[Dict[str, Any]],
    goal_plan: Optional[Dict[str, Any]] = None,
    execution_feedback: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    summary = _build_ai_coach_explainability_summary(
        data_context,
        goal_plan,
        execution_feedback,
    )
    if summary is None:
        return {
            "icon": "🧭",
            "title": "Начните с обзора доступных данных",
            "button": "Спросить, что AI уже видит",
            "description": "Если данных пока мало или контекст ещё пустой, лучший стартовый вопрос — уточнить, какие метрики уже доступны и что стоит загрузить дальше.",
            "reason": "Это быстрее всего проясняет, на чём AI может строить рекомендации прямо сейчас.",
            "prompt": "Какие данные у меня уже доступны для анализа, каких данных не хватает и с какого вопроса лучше начать работу с AI тренером?",
        }

    return {
        "icon": summary["icon"],
        "title": summary["title"],
        "button": summary["button"],
        "description": summary["description"],
        "reason": summary["reason"],
        "prompt": summary["prompt"],
        "response_contract": build_operational_response_contract(summary),
    }


def _normalize_ai_coach_handoff(handoff: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(handoff, dict):
        return None

    prompt = str(handoff.get("prompt") or "").strip()
    if not prompt:
        return None

    raw_signals = handoff.get("signals", [])
    signals = []
    if isinstance(raw_signals, list):
        signals = [str(signal) for signal in raw_signals if signal]

    return {
        "source": str(handoff.get("source") or "dashboard"),
        "icon": str(handoff.get("icon") or "🤖"),
        "title": str(handoff.get("title") or "Рекомендация с дашборда"),
        "button": str(handoff.get("button") or "Отправить вопрос"),
        "description": str(handoff.get("description") or ""),
        "reason": str(handoff.get("reason") or ""),
        "prompt": prompt,
        "today_action": str(handoff.get("today_action") or ""),
        "next_window": str(handoff.get("next_window") or ""),
        "watchout": str(handoff.get("watchout") or ""),
        "plan_context": str(handoff.get("plan_context") or ""),
        "signals": signals[:5],
        "response_contract": handoff.get("response_contract") if isinstance(handoff.get("response_contract"), dict) else None,
    }


def _resolve_ai_coach_entry_prompt(
    data_context: Optional[Dict[str, Any]],
    goal_plan: Optional[Dict[str, Any]] = None,
    handoff: Any = None,
    execution_feedback: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    normalized_handoff = _normalize_ai_coach_handoff(handoff)
    if normalized_handoff is not None:
        return {
            "icon": normalized_handoff["icon"],
            "title": normalized_handoff["title"],
            "button": normalized_handoff["button"],
            "description": normalized_handoff["description"] or normalized_handoff["today_action"],
            "reason": normalized_handoff["reason"] or "Этот старт уже выбран на дашборде как следующий логичный шаг.",
            "prompt": normalized_handoff["prompt"],
            "source": normalized_handoff["source"],
            "response_contract": normalized_handoff.get("response_contract"),
        }

    prompt = _choose_recommended_first_prompt(
        data_context,
        goal_plan,
        execution_feedback,
    )
    prompt["source"] = "default"
    return prompt


def render_dashboard_handoff(
    state: StateManager,
    handoff: Dict[str, Any],
    on_prompt_selected: Callable[[str], None],
) -> None:
    """Render a persisted dashboard -> AI coach handoff."""
    st.markdown("### 📥 Переход с дашборда")
    with st.container(border=True):
        st.markdown(f"**{handoff['title']}**")
        if handoff["description"]:
            st.write(handoff["description"])
        if handoff["today_action"]:
            st.write(f"**Сегодня:** {handoff['today_action']}")
        if handoff["next_window"]:
            st.write(f"**Ближайшие 2-3 дня:** {handoff['next_window']}")
        if handoff["watchout"]:
            st.write(f"**Следить за:** {handoff['watchout']}")
        if handoff["plan_context"]:
            st.caption(handoff["plan_context"])
        if handoff["reason"]:
            st.caption(handoff["reason"])
        if isinstance(handoff.get("response_contract"), dict) and handoff["response_contract"].get("preview_label"):
            st.caption(handoff["response_contract"]["preview_label"])
        for signal in handoff["signals"]:
            st.write(f"• {signal}")

        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(
                f"{handoff['icon']} {handoff['button']}",
                key="dashboard_handoff_prompt",
                type="primary",
                width="stretch",
            ):
                state.pending_ai_response_contract = handoff.get("response_contract")
                state.ai_coach_handoff = None
                on_prompt_selected(handoff["prompt"])
        with col2:
            if st.button(
                "Скрыть",
                key="dismiss_dashboard_handoff",
                width="stretch",
            ):
                state.ai_coach_handoff = None
                st.rerun()


def render_empty_ai_chat_guidance(
    state: StateManager,
    dashboard_handoff: Optional[Dict[str, Any]],
    on_prompt_selected: Callable[[str], None],
) -> None:
    """Render the first-run AI coach guidance when the current chat is empty."""
    with st.chat_message("assistant"):
        st.markdown(WELCOME_MESSAGE)

    goal_plan_context = getattr(state, "resolved_goal_plan_context", None)
    execution_feedback = getattr(state, "latest_execution_feedback", None)
    checkpoint_summary = summarize_planning_checkpoint(getattr(state, "latest_planning_checkpoint", None))

    if checkpoint_summary is not None:
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

    explain_summary = _build_ai_coach_explainability_summary(
        state.data_context,
        goal_plan_context,
        execution_feedback,
    )
    if explain_summary is not None:
        st.markdown("### 🧠 Почему такой старт")
        with st.container(border=True):
            st.markdown(f"**{explain_summary['short_title']}**")
            st.write(explain_summary["description"])
            st.write(f"**Сегодня:** {explain_summary['today_action']}")
            st.write(f"**Ближайшие 2-3 дня:** {explain_summary['next_window']}")
            st.write(f"**Следить за:** {explain_summary['watchout']}")
            if explain_summary.get("plan_context"):
                st.caption(explain_summary["plan_context"])
            st.caption(explain_summary["reason"])
            for signal in explain_summary["signals"][:5]:
                st.write(f"• {signal}")

    recommended_prompt = _resolve_ai_coach_entry_prompt(
        state.data_context,
        goal_plan_context,
        dashboard_handoff,
        execution_feedback,
    )
    if dashboard_handoff is None:
        st.markdown("### 🎯 Рекомендованный старт")
        st.info(
            f"**{recommended_prompt['title']}**\n\n"
            f"{recommended_prompt['description']}\n\n"
            f"{recommended_prompt['reason']}"
        )
        if isinstance(recommended_prompt.get("response_contract"), dict) and recommended_prompt["response_contract"].get("preview_label"):
            st.caption(recommended_prompt["response_contract"]["preview_label"])
        if st.button(
            f"{recommended_prompt['icon']} {recommended_prompt['button']}",
            key="recommended_ai_first_prompt",
            type="primary",
            width="stretch",
        ):
            state.pending_ai_response_contract = recommended_prompt.get("response_contract")
            on_prompt_selected(recommended_prompt["prompt"])


__all__ = [
    "_build_ai_coach_explainability_summary",
    "_choose_recommended_first_prompt",
    "_normalize_ai_coach_handoff",
    "_resolve_ai_coach_entry_prompt",
    "render_dashboard_handoff",
    "render_empty_ai_chat_guidance",
]
