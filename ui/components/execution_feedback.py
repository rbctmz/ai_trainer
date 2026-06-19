"""Shared execution-feedback editor for planning and dashboard surfaces."""
from __future__ import annotations

from typing import Any, Dict, Mapping

import pandas as pd
import streamlit as st

from models.planning_execution import (
    EXECUTION_DAY_OUTCOME_LABELS,
    build_execution_plan_adjustment,
    build_execution_reconciliation_rows,
    summarize_execution_reconciliation_rows,
)

QUICK_EXECUTION_LABELS = {
    "completed": "Выполнено по плану",
    "skipped": "Пропущены сессии",
    "reduced": "Нагрузка урезана",
    "unavailable": "Неделя ограничена",
}


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
            edited_rows = []
            for row in editable_rows:
                row_index = int(row["index"])
                outcome_key = f"{key_prefix}_outcome_{row_index}"
                actual_tss_key = f"{key_prefix}_actual_tss_{row_index}"
                st.session_state.setdefault(
                    outcome_key,
                    EXECUTION_DAY_OUTCOME_LABELS["as_planned"],
                )
                st.session_state.setdefault(
                    actual_tss_key,
                    int(row["planned_total_tss"]),
                )

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
                    with col2:
                        st.number_input(
                            "Факт TSS",
                            min_value=0,
                            max_value=int(row["planned_total_tss"]),
                            value=int(st.session_state[actual_tss_key]),
                            step=5,
                            key=actual_tss_key,
                            disabled=outcome_label != EXECUTION_DAY_OUTCOME_LABELS["reduced"],
                        )

                edited_rows.append(
                    {
                        **row,
                        "outcome": next(
                            code
                            for code, label in EXECUTION_DAY_OUTCOME_LABELS.items()
                            if label == st.session_state[outcome_key]
                        ),
                        "actual_total_tss": int(st.session_state[actual_tss_key]),
                    }
                )

            execution_summary = summarize_execution_reconciliation_rows(edited_rows)
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
            )

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
