"""Shared execution-feedback editor for planning and dashboard surfaces."""
from __future__ import annotations

from typing import Any, Dict, Mapping

import pandas as pd
import streamlit as st

from models.planning_execution import (
    EXECUTION_DAY_OUTCOME_LABELS,
    EXECUTION_RESPONSE_STRATEGY_LABELS,
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    rebuild_goal_plan_with_adjustment,
    summarize_execution_corrective_microcycle,
    summarize_execution_reconciliation_rows,
    summarize_execution_weekly_review_rows,
)

QUICK_EXECUTION_LABELS = {
    "completed": "Выполнено по плану",
    "skipped": "Пропущены сессии",
    "reduced": "Нагрузка урезана",
    "unavailable": "Неделя ограничена",
}


def _sanitize_actual_tss_value(planned_total_tss: Any, current_value: Any) -> int:
    """Clamp persisted widget state to the current row's allowed TSS range."""
    try:
        planned = int(planned_total_tss or 0)
    except (TypeError, ValueError):
        planned = 0
    try:
        value = int(current_value if current_value is not None else planned)
    except (TypeError, ValueError):
        value = planned
    return max(0, min(planned, value))


def _resolve_actual_tss_value(
    planned_total_tss: Any,
    outcome: str,
    current_value: Any,
) -> int:
    """Resolve the displayed/returned actual TSS for the current outcome."""
    normalized_outcome = str(outcome or "as_planned").strip().lower()
    planned = _sanitize_actual_tss_value(planned_total_tss, planned_total_tss)
    if normalized_outcome == "as_planned":
        return planned
    if normalized_outcome in {"missed", "unavailable"}:
        return 0
    return _sanitize_actual_tss_value(planned_total_tss, current_value)


def render_execution_feedback_editor(
    goal_plan: Mapping[str, Any] | None,
    *,
    key_prefix: str,
    title: str = "### ♻️ Факт выполнения",
) -> Dict[str, Any] | None:
    """Render a shared editor that converts execution facts into a local-replan payload."""
    if not isinstance(goal_plan, Mapping) or not goal_plan:
        return None

    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    if not daily_plan:
        return None

    max_weeks = min(2, max(1, (len(daily_plan) + 6) // 7))
    status_by_label = {label: code for code, label in QUICK_EXECUTION_LABELS.items()}
    strategy_by_label = {label: code for code, label in EXECUTION_RESPONSE_STRATEGY_LABELS.items()}

    st.markdown(title)
    with st.container(border=True):
        st.caption(
            "Зафиксируйте, как ближайшее окно прошло в реальности. "
            "AI Trainer пересчитает только ближний горизонт и короткое окно возврата нагрузки."
        )
        mode = st.radio(
            "Как зафиксировать факт",
            ["По дням", "Быстро"],
            horizontal=True,
            key=f"{key_prefix}_mode",
        )
        weeks = st.slider(
            "Горизонт локального пересчёта",
            min_value=1,
            max_value=max_weeks,
            value=1,
            step=1,
            key=f"{key_prefix}_weeks",
            help="Реальное окно влияния ограничено ближайшими 7-14 днями.",
        )

        plan_adjustment_payload: Dict[str, Any]
        execution_summary: Dict[str, Any] | None = None

        if mode == "Быстро":
            status_label = st.selectbox(
                "Что произошло по факту",
                options=list(QUICK_EXECUTION_LABELS.values()),
                index=0,
                key=f"{key_prefix}_quick_status",
            )
            status = status_by_label.get(status_label, "completed")
            missed_sessions = 0
            reduced_load_share = 0.70

            if status == "skipped":
                max_missed_sessions = max(
                    1,
                    int((goal_plan.get("constraint_summary", {}) or {}).get("available_day_count", 1) or 1),
                )
                missed_sessions = st.slider(
                    "Сколько сессий реально выпало",
                    min_value=1,
                    max_value=max_missed_sessions,
                    value=min(2, max_missed_sessions),
                    key=f"{key_prefix}_quick_missed_sessions",
                )
            elif status == "reduced":
                reduced_percent = st.slider(
                    "Сколько % нагрузки реально осталось",
                    min_value=35,
                    max_value=95,
                    value=70,
                    step=5,
                    key=f"{key_prefix}_quick_reduced_percent",
                )
                reduced_load_share = reduced_percent / 100.0
            elif status == "unavailable":
                st.caption(
                    "Используйте этот вариант, если ближайшая неделя реально сжалась из-за поездки, болезни или внешнего ограничения."
                )
            else:
                st.caption(
                    "Checkpoint сохранит, что окно выполнено по плану, без дополнительного снижения нагрузки."
                )

            plan_adjustment_payload = {
                "status": status,
                "weeks": weeks if status != "none" else 0,
                "missed_sessions": missed_sessions,
                "reduced_load_share": reduced_load_share,
            }
        else:
            editable_rows = build_execution_reconciliation_rows(goal_plan, weeks=weeks)
            current_response_strategy = str(
                ((goal_plan.get("constraint_summary", {}) or {}).get("catch_up_strategy") or "protect_recovery")
            ).strip().lower()
            if current_response_strategy not in EXECUTION_RESPONSE_STRATEGY_LABELS:
                current_response_strategy = "protect_recovery"
            response_strategy_key = f"{key_prefix}_response_strategy"
            st.session_state.setdefault(
                response_strategy_key,
                EXECUTION_RESPONSE_STRATEGY_LABELS[current_response_strategy],
            )
            edited_rows = []
            for row in editable_rows:
                row_index = int(row["index"])
                outcome_key = f"{key_prefix}_outcome_{row_index}"
                actual_tss_key = f"{key_prefix}_actual_tss_{row_index}"
                actual_tss_widget_key = f"{actual_tss_key}_widget"
                st.session_state.setdefault(
                    outcome_key,
                    EXECUTION_DAY_OUTCOME_LABELS["as_planned"],
                )
                outcome_label = str(st.session_state.get(outcome_key) or EXECUTION_DAY_OUTCOME_LABELS["as_planned"])
                outcome_code = next(
                    (
                        code
                        for code, label in EXECUTION_DAY_OUTCOME_LABELS.items()
                        if label == outcome_label
                    ),
                    "as_planned",
                )
                resolved_actual_tss = _resolve_actual_tss_value(
                    row["planned_total_tss"],
                    outcome_code,
                    st.session_state.get(
                        actual_tss_widget_key,
                        st.session_state.get(actual_tss_key),
                    ),
                )
                st.session_state[actual_tss_key] = resolved_actual_tss
                st.session_state[actual_tss_widget_key] = resolved_actual_tss

                with st.container(border=True):
                    st.markdown(f"**{row['date_label']} • {row['phase']}**")
                    st.caption(
                        f"План: {row['session_name']} · {row['sport']} · {row['session_role']} · "
                        f"{int(row['planned_total_tss'])} TSS · ~{int(row['planned_duration_minutes'])} мин"
                    )
                    col1, col2 = st.columns([1.4, 1])
                    with col1:
                        outcome_label = st.selectbox(
                            "Факт",
                            options=list(EXECUTION_DAY_OUTCOME_LABELS.values()),
                            key=outcome_key,
                        )
                    outcome_code = next(
                        (
                            code
                            for code, label in EXECUTION_DAY_OUTCOME_LABELS.items()
                            if label == outcome_label
                        ),
                        "as_planned",
                    )
                    resolved_actual_tss = _resolve_actual_tss_value(
                        row["planned_total_tss"],
                        outcome_code,
                        st.session_state.get(
                            actual_tss_widget_key,
                            st.session_state.get(actual_tss_key),
                        ),
                    )
                    st.session_state[actual_tss_key] = resolved_actual_tss
                    st.session_state[actual_tss_widget_key] = resolved_actual_tss
                    with col2:
                        actual_tss_value = st.number_input(
                            "Факт TSS",
                            min_value=0,
                            max_value=int(row["planned_total_tss"]),
                            value=int(resolved_actual_tss),
                            step=5,
                            key=actual_tss_widget_key,
                            disabled=outcome_code != "reduced",
                        )
                    st.session_state[actual_tss_key] = _resolve_actual_tss_value(
                        row["planned_total_tss"],
                        outcome_code,
                        actual_tss_value,
                    )

                edited_rows.append(
                    {
                        **row,
                        "outcome": outcome_code,
                        "actual_total_tss": int(st.session_state[actual_tss_key]),
                    }
                )

            execution_summary = summarize_execution_reconciliation_rows(edited_rows)
            selected_response_label = st.radio(
                "Как реагировать после этого окна",
                options=list(EXECUTION_RESPONSE_STRATEGY_LABELS.values()),
                key=response_strategy_key,
                horizontal=True,
            )
            selected_response_strategy = strategy_by_label.get(
                selected_response_label,
                current_response_strategy,
            )
            weekly_review = summarize_execution_weekly_review_rows(
                edited_rows,
                current_response_strategy=selected_response_strategy,
            )
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("Правок дней", execution_summary["changed_day_count"])
            with metric_cols[1]:
                st.metric(
                    "План TSS",
                    execution_summary["planned_total_tss"],
                )
            with metric_cols[2]:
                st.metric(
                    "Факт TSS",
                    execution_summary["actual_total_tss"],
                    delta=f"{execution_summary['delta_tss']:+d}",
                )
            with metric_cols[3]:
                st.metric("Статус", execution_summary["status_label"])

            st.caption(execution_summary["description"])
            with st.container(border=True):
                st.markdown(
                    f"**{weekly_review['review_badge']}** · {weekly_review['headline']}"
                )
                if weekly_review["deviations"]:
                    for item in weekly_review["deviations"]:
                        detail = f": {item['detail']}" if item.get("detail") else ""
                        st.write(f"• {item['label']}{detail}")
                else:
                    st.write("• Критичных отклонений в недельной структуре не видно.")
                st.caption(
                    "Рекомендуемая реакция: "
                    f"{weekly_review['recommended_response_label']}."
                )
                if weekly_review["recommended_response_reason"]:
                    st.caption(weekly_review["recommended_response_reason"])
                if selected_response_strategy != weekly_review["recommended_response_strategy"]:
                    if st.button(
                        f"Принять рекомендацию: {weekly_review['recommended_response_label']}",
                        key=f"{key_prefix}_accept_recommended_response",
                        width="stretch",
                    ):
                        st.session_state[response_strategy_key] = weekly_review["recommended_response_label"]
                        st.rerun()
            if execution_summary["changed_rows"]:
                st.dataframe(
                    pd.DataFrame(execution_summary["changed_rows"]),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("Ближнее окно пока совпадает с планом: локальный replan не потребуется.")

            plan_adjustment_payload = build_execution_plan_adjustment(
                goal_plan,
                edited_rows,
                weeks=weeks,
                response_strategy_override=selected_response_strategy,
            )
            projected_goal_plan = rebuild_goal_plan_with_adjustment(
                goal_plan,
                plan_adjustment_payload,
            )
            corrective_microcycle = summarize_execution_corrective_microcycle(
                (
                    (
                        (projected_goal_plan.get("constraint_summary", {}) or {}).get("plan_adjustment", {})
                        or {}
                    ).get("execution_corrective_microcycle")
                )
            )
            if corrective_microcycle:
                with st.container(border=True):
                    st.markdown(f"**{corrective_microcycle['headline']}**")
                    if corrective_microcycle["summary"]:
                        st.caption(corrective_microcycle["summary"])
                    for item in corrective_microcycle["sessions"]:
                        delta_text = (
                            f" · {item['delta_label']}"
                            if item.get("delta_tss")
                            else ""
                        )
                        st.write(
                            f"• {item['date_label']} · {item['action_label']} · "
                            f"{item['session_name']} ({item['planned_total_tss']} TSS{delta_text})"
                        )
                    if corrective_microcycle["guardrail"]:
                        st.caption(corrective_microcycle["guardrail"])

        if st.button(
            "♻️ Применить локальный replan",
            key=f"{key_prefix}_apply",
            type="primary",
            width="stretch",
        ):
            return {
                "plan_adjustment": plan_adjustment_payload,
                "execution_summary": execution_summary,
                "weeks": weeks,
                "mode": mode,
            }

    return None


__all__ = ["render_execution_feedback_editor"]
