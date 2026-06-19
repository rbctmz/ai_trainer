"""Training planning page renderer."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List

import pandas as pd
import streamlit as st

from models.planning_near_term import (
    EDITABLE_NEAR_TERM_HORIZON_MAX,
    EDITABLE_NEAR_TERM_HORIZON_MIN,
    EDITABLE_SESSION_ROLES,
    EDITABLE_SPORTS,
    apply_near_term_day_edits,
    build_near_term_edit_draft_rows,
    build_near_term_edit_rows,
    build_safer_near_term_draft,
    summarize_near_term_draft_rows,
)
from models.planning_execution import rebuild_goal_plan_with_adjustment
from models.planning_summary import (
    NEAR_TERM_EDIT_POST_STRATEGIES,
    NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU,
    summarize_near_term_edit,
)

if TYPE_CHECKING:
    from state import StateManager


def _strategy_label(strategy: str) -> str:
    return "Наверстать аккуратно" if strategy == "catch_up" else "Беречь восстановление"


def _infer_sport_for_export(parts: Dict[str, Any], session_template: Dict[str, Any] | None = None) -> str:
    sport = str((session_template or {}).get("sport") or "").strip().lower()
    if sport and sport != "off":
        return sport
    bike = float(parts.get("bike", 0.0) or 0.0)
    run = float(parts.get("run", 0.0) or 0.0)
    swim = float(parts.get("swim", 0.0) or 0.0)
    if bike >= max(run, swim):
        return "bike"
    if swim >= max(run, bike):
        return "swim"
    return "run"


def _resolve_target_weekly_tss_control(
    auto_suggested: int | float | None,
    t_min: int,
    t_max: int,
    availability_cap_tss: int,
) -> Dict[str, Any]:
    """Resolve a safe UI state for the target weekly TSS control."""
    distance_floor = max(100, int(t_min))
    distance_ceiling = max(distance_floor, int(t_max))
    effective_cap = max(100, int(availability_cap_tss))
    default_target = int(auto_suggested or int((distance_floor + distance_ceiling) / 2))
    resolved_value = max(100, min(default_target, effective_cap, distance_ceiling))
    slider_max = min(max(300, distance_ceiling), effective_cap)

    if slider_max <= distance_floor:
        return {
            "is_fixed": True,
            "value": resolved_value,
            "slider_min": distance_floor,
            "slider_max": slider_max,
            "reason": "availability_cap" if resolved_value < distance_floor else "single_value",
        }

    return {
        "is_fixed": False,
        "value": max(distance_floor, min(slider_max, resolved_value)),
        "slider_min": distance_floor,
        "slider_max": slider_max,
        "reason": "range",
    }


def _resolve_target_weekly_tss_step(slider_min: int, slider_max: int) -> int:
    """Choose a slider step that remains valid for narrow achievable ranges."""
    span = max(0, int(slider_max) - int(slider_min))
    if span <= 10:
        return 1
    if span <= 25:
        return 5
    return 25


def _build_plan_explainability(goal_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Build a concise, UI-friendly explanation for the generated plan."""
    adjusted = [int(round(value)) for value in goal_plan.get("weekly_tss_plan", [])]
    base = [int(round(value)) for value in goal_plan.get("base_weekly_tss_plan", adjusted)]
    phases = goal_plan.get("phases", [])
    weekly_summary = goal_plan.get("weekly_summary", [])
    constraint_summary = goal_plan.get("constraint_summary", {}) or {}
    plan_adjustment = constraint_summary.get("plan_adjustment", {}) or {}

    comparison_rows: List[Dict[str, Any]] = []
    changed_weeks = 0
    for idx, adjusted_value in enumerate(adjusted):
        base_value = base[idx] if idx < len(base) else adjusted_value
        delta = adjusted_value - base_value
        if delta != 0:
            changed_weeks += 1
        phase = phases[idx] if idx < len(phases) else "Base"
        week_start = ""
        if idx < len(weekly_summary):
            week_start_value = weekly_summary[idx].get("week_start")
            if week_start_value is not None:
                week_start = week_start_value.strftime("%d.%m")
        note = "—"
        if idx < len(weekly_summary):
            note = weekly_summary[idx].get("adjustment_note", "—")
        comparison_rows.append(
            {
                "Неделя": f"{idx + 1} • {week_start}" if week_start else str(idx + 1),
                "Фаза": phase,
                "Базовый TSS": base_value,
                "Адаптивный TSS": adjusted_value,
                "Δ TSS": f"{delta:+d}",
                "Почему": note,
            }
        )

    peak_before = max(base) if base else 0
    peak_after = max(adjusted) if adjusted else 0
    total_before = sum(base)
    total_after = sum(adjusted)
    capacity_tss = int(constraint_summary.get("weekly_capacity_tss", peak_after or 0))
    availability_days = ", ".join(constraint_summary.get("available_day_labels", [])) or "Все дни"
    interruption_label = constraint_summary.get("interruption_label", "Нет")
    catch_up_strategy = constraint_summary.get("catch_up_strategy", "protect_recovery")
    recovered_tss = int(constraint_summary.get("recovered_tss", 0))
    capacity_loss = int(constraint_summary.get("capacity_loss_tss", 0))
    interruption_loss = int(constraint_summary.get("interruption_loss_tss", 0))
    interruption_weeks = int(constraint_summary.get("interruption_weeks", 0))
    available_day_count = int(constraint_summary.get("available_day_count", 0))
    recommended_days = int(constraint_summary.get("recommended_days", 0))
    plan_adjustment_label = str(plan_adjustment.get("label", "Нет") or "Нет")
    plan_adjustment_weeks = int(plan_adjustment.get("weeks", 0) or 0)
    plan_adjustment_loss = int(constraint_summary.get("plan_adjustment_loss_tss", 0))
    plan_adjustment_recovered = int(constraint_summary.get("plan_adjustment_recovered_tss", 0))
    near_term_edit = summarize_near_term_edit(constraint_summary)
    summary_notes = list(constraint_summary.get("notes", []))
    first_week_structure = ""
    if weekly_summary:
        first_week_structure = str(weekly_summary[0].get("structure_summary", "") or "")
        if first_week_structure:
            summary_notes = [f"Структура первой недели: {first_week_structure}"] + summary_notes

    if plan_adjustment_loss > 0 and plan_adjustment_recovered > 0:
        headline = "План локально пересчитывает ближайшие недели после сбоя: сначала снимает объём, затем возвращает только безопасную часть в коротком окне."
    elif plan_adjustment_loss > 0:
        headline = "План локально упрощает ближайшие недели после сбоя и не размазывает пропущенный объём по всему циклу."
    elif interruption_loss > 0 and catch_up_strategy == "catch_up":
        headline = "План сначала снижает нагрузку из-за ограничения, затем возвращает только безопасную часть объёма."
    elif interruption_loss > 0:
        headline = "План защищает восстановление: первые недели упрощены, а пропущенный объём не догоняется автоматически."
    elif capacity_loss > 0:
        headline = "План подрезает пик под ваш реальный календарь, чтобы нагрузка оставалась выполнимой."
    else:
        headline = "Текущая доступность позволяет почти не менять базовый план — ограничения скорее подтверждают цель, чем режут её."

    return {
        "headline": headline,
        "peak_before": peak_before,
        "peak_after": peak_after,
        "peak_delta": peak_after - peak_before,
        "total_before": total_before,
        "total_after": total_after,
        "total_delta": total_after - total_before,
        "changed_weeks": changed_weeks,
        "capacity_tss": capacity_tss,
        "availability_days": availability_days,
        "available_hours": constraint_summary.get("available_hours", 0.0),
        "available_day_count": available_day_count,
        "recommended_days": recommended_days,
        "interruption_label": interruption_label,
        "interruption_weeks": interruption_weeks,
        "catch_up_label": _strategy_label(catch_up_strategy),
        "recovered_tss": recovered_tss,
        "plan_adjustment_label": plan_adjustment_label,
        "plan_adjustment_weeks": plan_adjustment_weeks,
        "plan_adjustment_loss_tss": plan_adjustment_loss,
        "plan_adjustment_recovered_tss": plan_adjustment_recovered,
        "near_term_edit": near_term_edit,
        "summary_notes": summary_notes,
        "comparison_rows": comparison_rows,
    }


def _build_daily_session_rows(goal_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a daily session breakdown with recovery-aware roles and focuses."""
    daily_plan = goal_plan.get("daily_plan", [])
    weekly_summary = goal_plan.get("weekly_summary", [])
    session_templates = goal_plan.get("session_templates", [])
    rows: List[Dict[str, Any]] = []

    for idx, (dt, total, parts) in enumerate(daily_plan):
        week_idx = idx // 7
        day_idx = idx % 7
        week_meta = weekly_summary[week_idx] if week_idx < len(weekly_summary) else {}
        day_roles = week_meta.get("day_roles") or ["—"] * 7
        day_focuses = week_meta.get("day_focuses") or ["—"] * 7
        session_template = session_templates[idx] if idx < len(session_templates) else {}

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "phase": session_template.get("phase", week_meta.get("phase", "—")),
                "sport": session_template.get("sport", "—"),
                "session_role": session_template.get("session_role", day_roles[day_idx] if day_idx < len(day_roles) else "—"),
                "session_focus": session_template.get("session_focus", day_focuses[day_idx] if day_idx < len(day_focuses) else "—"),
                "session_name": session_template.get("export_name", "—"),
                "duration_minutes": session_template.get("duration_minutes", 0),
                "total_tss": total,
                "run_tss": parts.get("run", 0.0),
                "bike_tss": parts.get("bike", 0.0),
                "swim_tss": parts.get("swim", 0.0),
            }
        )

    return rows


def _build_near_term_draft_preview(
    current_goal_plan: Dict[str, Any],
    draft_goal_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize week-level impact and the persisted label for the current draft."""
    return _build_goal_plan_transition_preview(current_goal_plan, draft_goal_plan)


def _build_goal_plan_transition_preview(
    current_goal_plan: Dict[str, Any],
    target_goal_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Summarize week-level impact between two concrete goal plan versions."""
    current_weekly_summary = list(current_goal_plan.get("weekly_summary", []) or [])
    target_weekly_summary = list(target_goal_plan.get("weekly_summary", []) or [])
    weekly_rows: List[Dict[str, Any]] = []

    for idx, target_row in enumerate(target_weekly_summary):
        current_row = current_weekly_summary[idx] if idx < len(current_weekly_summary) else {}
        current_tss = int(current_row.get("weekly_tss", 0) or 0)
        target_tss = int(target_row.get("weekly_tss", current_tss) or 0)
        current_note = str(current_row.get("adjustment_note", "—") or "—")
        target_note = str(target_row.get("adjustment_note", current_note) or "—")

        if current_tss == target_tss and current_note == target_note:
            continue

        week_start_value = target_row.get("week_start") or current_row.get("week_start")
        week_label = str(idx + 1)
        if week_start_value is not None:
            week_label = f"{idx + 1} • {week_start_value.strftime('%d.%m')}"

        weekly_rows.append(
            {
                "Неделя": week_label,
                "Было TSS": current_tss,
                "Станет TSS": target_tss,
                "Δ TSS": f"{target_tss - current_tss:+d}",
                "Почему": target_note,
            }
        )

    return {
        "near_term_edit": summarize_near_term_edit(target_goal_plan.get("constraint_summary", {})),
        "changed_week_count": len(weekly_rows),
        "weekly_rows": weekly_rows,
    }


def _render_near_term_risk_callout(near_term_edit: Dict[str, Any], *, prefix: str) -> None:
    risk_level = str(near_term_edit.get("risk_level") or "low").lower()
    risk_badge = str(near_term_edit.get("risk_badge") or "Риск низкий")
    risk_guardrail = str(near_term_edit.get("risk_guardrail") or "").strip()
    risk_reasons = [
        str(reason).strip()
        for reason in near_term_edit.get("risk_reasons", [])
        if str(reason).strip()
    ]
    body = f"**{prefix}: {risk_badge}.**"
    if risk_guardrail:
        body += f" {risk_guardrail}"

    if risk_level == "high":
        st.error(body)
    elif risk_level == "medium":
        st.warning(body)
    else:
        st.info(body)

    for reason in risk_reasons[:3]:
        st.write(f"• {reason}")


def _render_near_term_editor(
    goal_plan: Dict[str, Any],
    rollback_goal_plan: Dict[str, Any] | None = None,
    rollback_checkpoint_id: int | None = None,
) -> Dict[str, Any] | None:
    """Render an in-place editor for the next 7-10 days of the current plan."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    if len(daily_plan) < EDITABLE_NEAR_TERM_HORIZON_MIN:
        return None

    max_horizon = min(EDITABLE_NEAR_TERM_HORIZON_MAX, len(daily_plan))
    plan_revision = str(goal_plan.get("plan_revision") or goal_plan.get("start_week") or "current-plan")
    edit_version = int(goal_plan.get("near_term_edit_version", 0) or 0)
    key_prefix = f"{plan_revision}:{edit_version}"

    role_labels = {
        "off": "Отдых",
        "recovery": "Восстановление",
        "easy": "Лёгкая",
        "quality": "Качество",
        "long": "Длительная",
    }
    sport_labels = {
        "run": "бег",
        "bike": "вело",
        "swim": "плавание",
        "off": "отдых",
    }
    role_labels_reverse = {label: code for code, label in role_labels.items()}
    sport_labels_reverse = {label: code for code, label in sport_labels.items()}
    strategy_labels = {
        code: NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU[code]
        for code in NEAR_TERM_EDIT_POST_STRATEGIES
    }
    strategy_labels_reverse = {label: code for code, label in strategy_labels.items()}

    st.markdown("### ✍️ Редактировать ближайшие 7-10 дней")
    with st.expander("Открыть редактор ближайших дней", expanded=False):
        st.caption(
            "Этот редактор меняет только ближайшие дни текущего плана. Остальной цикл не перестраивается, "
            "а checkpoint, explainability и экспорты обновятся только после явного применения черновика."
        )
        saved_summary = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
        if saved_summary is not None:
            st.info(
                "Сейчас в сохранённом checkpoint уже есть ручная правка: "
                f"{saved_summary['compact_label']}."
            )
        default_strategy = "keep"
        if saved_summary is not None:
            default_strategy = str(saved_summary.get("post_edit_strategy") or "keep")
        st.session_state.setdefault(
            f"near_term_strategy_{key_prefix}",
            strategy_labels.get(default_strategy, strategy_labels["keep"]),
        )
        horizon_days = st.slider(
            "Сколько дней открыть для правки:",
            min_value=EDITABLE_NEAR_TERM_HORIZON_MIN,
            max_value=max_horizon,
            value=min(EDITABLE_NEAR_TERM_HORIZON_MIN, max_horizon),
            step=1,
            key=f"near_term_horizon_{key_prefix}",
        )
        editable_rows = build_near_term_edit_rows(goal_plan, horizon_days=horizon_days)
        for row in editable_rows:
            st.session_state.setdefault(
                f"near_term_role_{key_prefix}_{row['index']}",
                role_labels[row["current_role"]],
            )
            st.session_state.setdefault(
                f"near_term_sport_{key_prefix}_{row['index']}",
                sport_labels[row["current_sport"]],
            )
            st.session_state.setdefault(
                f"near_term_tss_{key_prefix}_{row['index']}",
                int(round(row["current_total_tss"])),
            )

        overrides_by_index = {
            int(row["index"]): {
                "session_role": role_labels_reverse[
                    st.session_state[f"near_term_role_{key_prefix}_{row['index']}"]
                ],
                "sport": sport_labels_reverse[
                    st.session_state[f"near_term_sport_{key_prefix}_{row['index']}"]
                ],
                "total_tss": st.session_state[f"near_term_tss_{key_prefix}_{row['index']}"],
            }
            for row in editable_rows
        }
        draft_rows = build_near_term_edit_draft_rows(
            editable_rows,
            goal_type=str(goal_plan.get("goal_type") or ""),
            distance=str(goal_plan.get("distance") or ""),
            overrides_by_index=overrides_by_index,
        )
        draft_rows_by_index = {
            int(row["index"]): row
            for row in draft_rows
        }
        draft_summary = summarize_near_term_draft_rows(draft_rows)
        selected_strategy_label = st.selectbox(
            "Что делать с этой дельтой в следующих 1-2 нед.:",
            options=[strategy_labels[code] for code in NEAR_TERM_EDIT_POST_STRATEGIES],
            key=f"near_term_strategy_{key_prefix}",
            disabled=not draft_summary["has_changes"],
        )
        selected_post_edit_strategy = strategy_labels_reverse[selected_strategy_label]
        draft_preview = None
        if draft_summary["has_changes"]:
            draft_preview = _build_near_term_draft_preview(
                goal_plan,
                apply_near_term_day_edits(
                    goal_plan,
                    draft_rows,
                    horizon_days=horizon_days,
                    post_edit_strategy=selected_post_edit_strategy,
                ),
            )
        safer_draft = None
        soften_clicked = False
        rollback_clicked = False
        rollback_preview = None
        if rollback_goal_plan is not None:
            rollback_preview = _build_goal_plan_transition_preview(goal_plan, rollback_goal_plan)

        st.markdown("#### Черновик правок")
        if draft_summary["has_changes"]:
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("Правок дней", draft_summary["changed_day_count"])
            with metric_cols[1]:
                st.metric(
                    "TSS окна",
                    draft_summary["target_total_tss"],
                    delta=f"{draft_summary['total_delta_tss']:+d}",
                )
            with metric_cols[2]:
                st.metric("Дней отдыха", draft_summary["off_day_count"])
            with metric_cols[3]:
                st.metric("Качественных дней", draft_summary["quality_day_count"])
            st.caption(
                "Это пока только черновик. Сохранённый checkpoint, explainability и экспорты "
                "обновятся после нажатия «Применить правки ближнего горизонта»."
            )
            st.dataframe(
                pd.DataFrame(draft_summary["changed_rows"]),
                width="stretch",
                hide_index=True,
            )
            if draft_preview and draft_preview["near_term_edit"] is not None:
                st.caption(
                    "После применения сохранённый checkpoint покажет: "
                    f"{draft_preview['near_term_edit']['compact_label']}."
                )
                st.caption(draft_preview["near_term_edit"]["follow_up_description"])
                _render_near_term_risk_callout(
                    draft_preview["near_term_edit"],
                    prefix="Оценка правки",
                )
                safer_draft = build_safer_near_term_draft(
                    goal_plan,
                    draft_rows,
                    horizon_days=horizon_days,
                    post_edit_strategy=selected_post_edit_strategy,
                )
                if safer_draft is not None:
                    st.caption(
                        "Можно смягчить черновик одним кликом: "
                        f"{safer_draft['description']}."
                    )
                    st.caption(
                        "Более безопасный вариант даст: "
                        f"{safer_draft['near_term_edit']['compact_label']}."
                    )
                    _render_near_term_risk_callout(
                        safer_draft["near_term_edit"],
                        prefix="Если смягчить",
                    )
                    soften_clicked = st.button(
                        "🛟 Смягчить черновик",
                        key=f"near_term_soften_{key_prefix}",
                        width="stretch",
                    )
            if draft_preview and draft_preview["weekly_rows"]:
                st.markdown("##### Как изменятся недели")
                st.dataframe(
                    pd.DataFrame(draft_preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
        else:
            st.info(
                "Черновик совпадает с текущим ближним горизонтом: "
                f"{draft_summary['horizon_days']} дн. · {draft_summary['current_total_tss']} TSS."
            )

        if rollback_goal_plan is not None:
            st.markdown("#### ↩️ Откат последней сохранённой правки")
            current_saved_edit = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
            if current_saved_edit is not None:
                st.caption(
                    "Текущий checkpoint хранит ручную правку: "
                    f"{current_saved_edit['compact_label']}."
                )
            if rollback_preview and rollback_preview["near_term_edit"] is not None:
                st.caption(
                    "После отката активной станет версия: "
                    f"{rollback_preview['near_term_edit']['compact_label']}."
                )
            else:
                st.caption("После отката ручная правка ближнего горизонта исчезнет из сохранённого checkpoint.")
            if rollback_preview and rollback_preview["weekly_rows"]:
                st.dataframe(
                    pd.DataFrame(rollback_preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
            rollback_clicked = st.button(
                "↩️ Откатить последнюю ручную правку",
                key=f"near_term_rollback_{key_prefix}",
                width="stretch",
            )

        for row in editable_rows:
            draft_row = draft_rows_by_index[int(row["index"])]
            with st.container(border=True):
                st.markdown(f"**{row['date_label']} • {row['phase']}**")
                st.caption(
                    f"Сейчас: {draft_row['current_summary']} · ~{row['current_duration_minutes']} мин"
                )
                if draft_row["changed"]:
                    st.caption(
                        f"Черновик: {draft_row['target_summary']} · "
                        f"~{draft_row['target_duration_minutes']} мин · "
                        f"Δ {int(round(float(draft_row['delta_tss'] or 0.0))):+d} TSS"
                    )
                else:
                    st.caption("Черновик пока совпадает с сохранённым днём.")
                col1, col2, col3 = st.columns([1.2, 1, 1])
                with col1:
                    st.selectbox(
                        "Роль дня",
                        options=[role_labels[role] for role in EDITABLE_SESSION_ROLES],
                        index=EDITABLE_SESSION_ROLES.index(draft_row["session_role"]),
                        key=f"near_term_role_{key_prefix}_{row['index']}",
                    )
                with col2:
                    st.selectbox(
                        "Основной спорт",
                        options=[sport_labels[sport] for sport in EDITABLE_SPORTS],
                        index=EDITABLE_SPORTS.index(draft_row["sport"]),
                        key=f"near_term_sport_{key_prefix}_{row['index']}",
                    )
                with col3:
                    st.number_input(
                        "TSS",
                        min_value=0,
                        max_value=max(180, int(round(row["current_total_tss"])) + 80),
                        value=int(round(float(draft_row["total_tss"] or 0.0))),
                        step=5,
                        key=f"near_term_tss_{key_prefix}_{row['index']}",
                    )

        action_cols = st.columns([1, 1.4])
        with action_cols[0]:
            reset_clicked = st.button(
                "↺ Сбросить черновик",
                key=f"near_term_reset_{key_prefix}",
                disabled=not draft_summary["has_changes"],
                width="stretch",
            )
        with action_cols[1]:
            apply_clicked = st.button(
                "💾 Применить правки ближнего горизонта",
                key=f"near_term_apply_{key_prefix}",
                type="primary",
                disabled=not draft_summary["has_changes"],
                width="stretch",
            )

        if reset_clicked:
            for row in editable_rows:
                st.session_state[f"near_term_role_{key_prefix}_{row['index']}"] = role_labels[row["current_role"]]
                st.session_state[f"near_term_sport_{key_prefix}_{row['index']}"] = sport_labels[row["current_sport"]]
                st.session_state[f"near_term_tss_{key_prefix}_{row['index']}"] = int(round(row["current_total_tss"]))
            st.rerun()

        if rollback_clicked and rollback_goal_plan is not None:
            restored_goal_plan = dict(rollback_goal_plan)
            restored_goal_plan["plan_revision"] = datetime.now().isoformat()
            restored_goal_plan["_transient_planning_action"] = "rollback_near_term_edit"
            restored_goal_plan["_transient_restore_checkpoint_id"] = rollback_checkpoint_id
            return restored_goal_plan

        if soften_clicked and safer_draft is not None:
            st.session_state[f"near_term_strategy_{key_prefix}"] = strategy_labels[safer_draft["post_edit_strategy"]]
            for row in safer_draft["draft_rows"]:
                row_index = int(row["index"])
                st.session_state[f"near_term_role_{key_prefix}_{row_index}"] = role_labels[row["session_role"]]
                st.session_state[f"near_term_sport_{key_prefix}_{row_index}"] = sport_labels[row["sport"]]
                st.session_state[f"near_term_tss_{key_prefix}_{row_index}"] = int(round(float(row["total_tss"] or 0.0)))
            st.rerun()

        if apply_clicked:
            return apply_near_term_day_edits(
                goal_plan,
                draft_rows,
                horizon_days=horizon_days,
                post_edit_strategy=selected_post_edit_strategy,
            )

    return None


def _render_planning_version_history(
    goal_plan: Dict[str, Any],
    latest_checkpoint: Dict[str, Any] | None,
    checkpoint_history: List[Dict[str, Any]] | None,
) -> Dict[str, Any] | None:
    """Render recent saved plan versions with compare + restore actions."""
    from models.planning_checkpoints import (
        restore_goal_plan_from_checkpoint,
        summarize_planning_checkpoint,
    )

    current_summary = summarize_planning_checkpoint(latest_checkpoint)
    if current_summary is None:
        return None

    latest_checkpoint_id = current_summary.get("checkpoint_id")
    history_records = [
        record
        for record in (checkpoint_history or [])
        if isinstance(record, dict) and record.get("id") != latest_checkpoint_id
    ][:4]
    if not history_records:
        return None

    st.markdown("### 🗂️ История версий плана")
    st.caption("Сравните текущую версию с недавними checkpoint и при необходимости восстановите любую из них.")

    current_provenance = current_summary.get("provenance") or {}
    with st.container(border=True):
        st.markdown(
            f"**Сейчас активна:** checkpoint #{current_summary['checkpoint_id']} · "
            f"{current_provenance.get('label', 'Текущая версия')}"
        )
        if current_summary["created_at_label"]:
            st.caption(f"Сохранён: {current_summary['created_at_label']}")
        if current_provenance.get("detail"):
            st.caption(current_provenance["detail"])
        st.write(
            f"**Checkpoint:** {current_summary['plan_adjustment_label']} · "
            f"Пик {current_summary['peak_tss']} TSS · Сумма {current_summary['total_tss']} TSS"
        )
        if current_summary.get("execution_reconciliation"):
            execution_reconciliation = current_summary["execution_reconciliation"]
            st.caption(
                f"Факт окна: {execution_reconciliation['actual_total_tss']} из "
                f"{execution_reconciliation['planned_total_tss']} TSS · "
                f"{execution_reconciliation['changed_day_count']} дн. изменено"
            )

    for record in history_records:
        summary = summarize_planning_checkpoint(record)
        restored_goal_plan = restore_goal_plan_from_checkpoint(record)
        if summary is None or not isinstance(restored_goal_plan, dict) or not restored_goal_plan.get("daily_plan"):
            continue

        preview = _build_goal_plan_transition_preview(goal_plan, restored_goal_plan)
        provenance = summary.get("provenance") or {}
        with st.container(border=True):
            st.markdown(
                f"**Checkpoint #{summary['checkpoint_id']} · {provenance.get('label', 'Сохранённая версия')}**"
            )
            if summary["created_at_label"]:
                st.caption(f"Сохранён: {summary['created_at_label']}")
            if provenance.get("detail"):
                st.caption(provenance["detail"])
            st.write(
                f"**Checkpoint:** {summary['plan_adjustment_label']} · "
                f"Пик {summary['peak_tss']} TSS · Сумма {summary['total_tss']} TSS"
            )
            if summary.get("execution_reconciliation"):
                execution_reconciliation = summary["execution_reconciliation"]
                st.caption(
                    f"Факт окна: {execution_reconciliation['actual_total_tss']} из "
                    f"{execution_reconciliation['planned_total_tss']} TSS · "
                    f"{execution_reconciliation['changed_day_count']} дн. изменено"
                )
            if summary.get("near_term_edit"):
                st.caption(f"Ручная правка: {summary['near_term_edit']['compact_label']}")
            if preview["weekly_rows"]:
                st.dataframe(
                    pd.DataFrame(preview["weekly_rows"]),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("По недельной структуре эта версия совпадает с текущей.")
            if st.button(
                "↩️ Восстановить эту версию",
                key=f"restore_planning_checkpoint_{summary['checkpoint_id']}",
                width="stretch",
            ):
                restored_goal_plan = dict(restored_goal_plan)
                restored_goal_plan["plan_revision"] = datetime.now().isoformat()
                restored_goal_plan["_transient_planning_action"] = "restore_checkpoint_version"
                restored_goal_plan["_transient_restore_checkpoint_id"] = summary["checkpoint_id"]
                return restored_goal_plan

    return None


def _render_plan_explainability(goal_plan: Dict[str, Any]) -> pd.DataFrame:
    explain = _build_plan_explainability(goal_plan)

    st.markdown("### 🧠 Почему план такой")
    with st.container(border=True):
        st.markdown(f"**{explain['headline']}**")
        for note in explain["summary_notes"]:
            st.write(f"• {note}")

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("Пик TSS", explain["peak_after"], delta=f"{explain['peak_delta']:+d} к базе")
    with metric_cols[1]:
        st.metric("Сумма TSS", explain["total_after"], delta=f"{explain['total_delta']:+d} к базе")
    with metric_cols[2]:
        st.metric("Недель с коррекцией", explain["changed_weeks"])
    with metric_cols[3]:
        st.metric("Стратегия", explain["catch_up_label"])

    scenario_col, planner_col = st.columns(2)
    with scenario_col:
        with st.container(border=True):
            st.markdown("#### Сценарий")
            st.write(f"• Доступно часов: {explain['available_hours']:.1f}")
            st.write(
                f"• Дни: {explain['availability_days']} "
                f"({explain['available_day_count']} из {explain['recommended_days']})"
            )
            if explain["interruption_weeks"] > 0 and explain["interruption_label"] != "Нет":
                st.write(
                    f"• Ограничение: {explain['interruption_label']} "
                    f"на {explain['interruption_weeks']} нед."
                )
            else:
                st.write("• Ограничение: нет")
            if explain["plan_adjustment_label"] != "Нет":
                weeks_suffix = (
                    f" на {explain['plan_adjustment_weeks']} нед."
                    if explain["plan_adjustment_weeks"] > 0
                    else ""
                )
                st.write(f"• Checkpoint: {explain['plan_adjustment_label']}{weeks_suffix}")
            else:
                st.write("• Checkpoint: без локальной перепланировки")
    with planner_col:
        with st.container(border=True):
            st.markdown("#### Решение Планировщика")
            st.write(f"• Мягкий потолок: {explain['capacity_tss']} TSS/нед")
            if explain["recovered_tss"] > 0:
                st.write(f"• Возвращено нагрузки: {explain['recovered_tss']} TSS")
            else:
                st.write("• Возврат нагрузки: не применялся")
            if explain["plan_adjustment_recovered_tss"] > 0:
                st.write(f"• Локально возвращено: {explain['plan_adjustment_recovered_tss']} TSS")
            elif explain["plan_adjustment_loss_tss"] > 0:
                st.write("• Локальный возврат: не применялся")
            if explain["near_term_edit"] is not None:
                st.write(f"• Ручная правка: {explain['near_term_edit']['compact_label']}")
                st.write(f"• После окна: {explain['near_term_edit']['follow_up_description']}")
                st.write(f"• Оценка правки: {explain['near_term_edit']['risk_badge']}")
                st.write(f"• Guardrail: {explain['near_term_edit']['risk_guardrail']}")
            st.write(f"• Пик базового плана: {explain['peak_before']} → {explain['peak_after']}")

    comparison_df = pd.DataFrame(explain["comparison_rows"])
    st.markdown("### ↔️ До / После По Неделям")
    st.dataframe(comparison_df, width="stretch", hide_index=True)
    return comparison_df


def render_planning_page(state: "StateManager") -> None:
    """Render the training planning page."""
    from models.banister import BanisterModel
    from services import intervals_icu
    from services.data_cache import load_activities
    from utils.visualizations import Visualizations

    st.header("📈 Планирование тренировок")

    activities_df = load_activities(90)

    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return

    banister = BanisterModel()

    tss_data = []
    dates = []

    for _, row in activities_df.iterrows():
        tss_val = row["tss"] if "tss" in row and pd.notna(row["tss"]) else 0
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row["date"])

    current_metrics = banister.get_current_metrics(tss_data, dates)

    st.subheader("🎯 Текущее состояние")
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        st.metric("CTL (Фитнес)", current_metrics["ctl"])
    with col2:
        st.metric("ATL (Усталость)", current_metrics["atl"])
    with col3:
        st.metric("TSB (Форма)", current_metrics["tsb"])
    with col4:
        form_color = {
            "Отличная форма": "🟢",
            "Хорошая форма": "🟡",
            "Усталость": "🟠",
            "Переутомление": "🔴",
            "Недостаточно данных": "⚫",
        }
        form_status = current_metrics["form"] if "form" in current_metrics else "Недостаточно данных"
        st.metric("Состояние", f"{form_color.get(form_status, '⚫')} {form_status}")

    st.subheader("📊 Анализ фитнеса и усталости")

    dates_full, ctl_values, atl_values, tsb_values = banister.calculate_ctl_atl_tsb(tss_data, dates)

    if dates_full and ctl_values:
        fig_banister = Visualizations.create_banister_chart(dates_full, ctl_values, atl_values, tsb_values)
        st.plotly_chart(fig_banister, width="stretch")

    st.subheader("💡 Рекомендации по тренировкам")
    recommendation = banister.get_training_recommendation(current_metrics)

    intensity_colors = {
        "Высокая": "🔴",
        "Умеренная": "🟡",
        "Низкая": "🟢",
        "Очень низкая/Отдых": "🔵",
    }

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            f"""
        **{recommendation['recommendation']}**

        {recommendation['description']}

        **Рекомендуемый диапазон TSS:** {recommendation['suggested_tss']}
        """
        )

    with col2:
        st.markdown(
            f"""
        **Интенсивность:** {intensity_colors.get(recommendation['intensity'], '⚫')} {recommendation['intensity']}
        """
        )

    st.subheader("🎲 Симулятор планирования")

    col1, col2 = st.columns(2)

    with col1:
        planned_weekly_tss = st.slider(
            "Планируемый недельный TSS:",
            min_value=0,
            max_value=1000,
            value=int((current_metrics["ctl"] if "ctl" in current_metrics else 50) * 7),
            step=50,
            help="Планируемая тренировочная нагрузка на неделю",
        )

    with col2:
        simulation_weeks = st.slider(
            "Период симуляции (недели):",
            min_value=1,
            max_value=12,
            value=4,
            step=1,
        )

    if st.button("🚀 Показать прогноз"):
        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_training_load(
            current_metrics, planned_weekly_tss, simulation_weeks
        )

        if future_dates:
            fig_future = Visualizations.create_banister_chart(
                future_dates, future_ctl, future_atl, future_tsb
            )
            fig_future.update_layout(title="Прогноз при планируемой нагрузке")
            st.plotly_chart(fig_future, width="stretch")

            final_tsb = future_tsb[-1]
            if final_tsb > 5:
                forecast_message = "🟢 Отличный прогноз! Вы будете в пиковой форме."
            elif final_tsb > -10:
                forecast_message = "🟡 Хорошая нагрузка для поддержания формы."
            elif final_tsb > -30:
                forecast_message = "🟠 Внимание: возможно накопление усталости."
            else:
                forecast_message = "🔴 Предупреждение: высокий риск переутомления!"

            st.info(f"**Прогноз через {simulation_weeks} недель:** TSB = {final_tsb:.1f} - {forecast_message}")

    st.subheader("🎯 План под цель (дата старта)")

    from models.training_planner import (
        WEEKDAY_LABELS_RU,
        apply_planning_constraints,
        compute_phase_schedule,
        create_weekly_tss_plan,
        estimated_tss_per_hour,
        expand_weekly_to_daily_triathlon,
        flatten_daily_total,
        goal_target_weekly_tss,
        summarize_availability,
        suggest_target_weekly_tss,
        weeks_until,
    )

    colg1, colg2, colg3 = st.columns(3)
    with colg1:
        goal_type = st.selectbox(
            "Тип цели:",
            ["Триатлон", "Бег", "Вело"],
            index=0,
        )
        if goal_type == "Триатлон":
            distance_options = ["Спринт", "Олимпийка", "Half (70.3)", "Ironman"]
            default_index = 1
        elif goal_type == "Бег":
            distance_options = ["5 км", "10 км", "Полумарафон", "Марафон", "Ультра"]
            default_index = 2
        else:
            distance_options = ["40 км TT", "100 км", "100 миль", "200 км (бревет)", "Этапная гонка"]
            default_index = 1
        distance = st.selectbox("Дистанция:", distance_options, index=default_index)
    with colg2:
        goal_date = st.date_input(
            "Дата старта:",
            value=datetime.now().date() + timedelta(weeks=8),
        )
        weeks_to_race = weeks_until(goal_date)
        st.caption(f"До старта: ~{weeks_to_race} нед.")
    with colg3:
        start_weekly_tss_guess = int(current_metrics.get("ctl", 50) * 7)
        auto = suggest_target_weekly_tss(goal_type, distance, activities_df)
        st.caption(f"Автонастройка: последняя неделя {auto['last_week']}, среднее 4н {auto['avg_4']}, лучшая 8н {auto['best_8']}")

    t_min, t_max = goal_target_weekly_tss(goal_type, distance)
    default_hours = max(
        3.0,
        min(
            20.0,
            round((float(auto["suggested"] or int((t_min + t_max) / 2)) / estimated_tss_per_hour(goal_type)) * 2) / 2,
        ),
    )

    st.markdown("#### 🧭 Сценарий и ограничения")
    cola1, cola2, cola3 = st.columns([1, 1.3, 1])
    with cola1:
        available_hours = st.slider(
            "Доступно часов в неделю:",
            min_value=3.0,
            max_value=20.0,
            value=float(default_hours),
            step=0.5,
            help="Используется как мягкий потолок weekly TSS под ваш реальный календарь.",
        )
    with cola2:
        available_day_labels = st.multiselect(
            "Доступные дни для тренировок:",
            options=WEEKDAY_LABELS_RU,
            default=WEEKDAY_LABELS_RU,
            help="Нагрузка будет перераспределена только на выбранные дни.",
        )
    with cola3:
        interruption_label = st.selectbox(
            "Ближайшее ограничение:",
            ["Нет", "Ограниченная доступность", "Отпуск", "Болезнь", "Травма"],
            index=0,
        )

    interruption_key_map = {
        "Нет": "none",
        "Ограниченная доступность": "limited",
        "Отпуск": "holiday",
        "Болезнь": "illness",
        "Травма": "injury",
    }
    plan_adjustment_key_map = {
        "Нет": "none",
        "Выполнено по плану": "completed",
        "Пропущены сессии": "skipped",
        "Нагрузка урезана": "reduced",
        "Неделя ограничена": "unavailable",
    }
    selected_day_indices = [
        WEEKDAY_LABELS_RU.index(label)
        for label in available_day_labels
        if label in WEEKDAY_LABELS_RU
    ] or list(range(7))

    colb1, colb2 = st.columns([1, 1.5])
    with colb1:
        interruption_weeks = st.slider(
            "Сколько недель продлится:",
            min_value=0,
            max_value=min(4, weeks_to_race),
            value=1 if interruption_label != "Нет" and weeks_to_race > 0 else 0,
            step=1,
            disabled=interruption_label == "Нет",
        )
    with colb2:
        catch_up_label = st.radio(
            "После пропуска:",
            ["Беречь восстановление", "Наверстать аккуратно"],
            horizontal=True,
            help="«Беречь восстановление» не пытается автоматически вернуть весь пропущенный объём. «Наверстать аккуратно» возвращает только часть нагрузки и с ограничением по усталости.",
        )

    catch_up_strategy = "catch_up" if catch_up_label == "Наверстать аккуратно" else "protect_recovery"
    availability_preview = summarize_availability(goal_type, available_hours, selected_day_indices)
    availability_cap_tss = int(availability_preview["weekly_capacity_tss"])

    st.markdown("#### ♻️ Локальная перепланировка")
    adjustment_col1, adjustment_col2, adjustment_col3 = st.columns([1.3, 1, 1])
    with adjustment_col1:
        plan_adjustment_label = st.selectbox(
            "Что произошло в реальном выполнении:",
            ["Нет", "Выполнено по плану", "Пропущены сессии", "Нагрузка урезана", "Неделя ограничена"],
            index=0,
            help="Этот checkpoint меняет только ближайший горизонт, а не перестраивает весь цикл вслепую.",
        )

    plan_adjustment_status = plan_adjustment_key_map.get(plan_adjustment_label, "none")
    max_adjustment_weeks = min(2, max(1, weeks_to_race))
    with adjustment_col2:
        plan_adjustment_weeks = st.slider(
            "Горизонт пересчёта:",
            min_value=1,
            max_value=max_adjustment_weeks,
            value=1,
            step=1,
            disabled=plan_adjustment_status in {"none", "completed"},
            help="План меняет только ближайшие 7-14 дней и короткое окно safe catch-up после них.",
        )

    plan_adjustment_missed_sessions = 0
    plan_adjustment_reduced_share = 0.70
    with adjustment_col3:
        if plan_adjustment_status == "skipped":
            max_missed_sessions = max(1, min(4, int(availability_preview["available_day_count"])))
            plan_adjustment_missed_sessions = st.slider(
                "Сколько сессий выпало:",
                min_value=1,
                max_value=max_missed_sessions,
                value=min(2, max_missed_sessions),
                step=1,
            )
        elif plan_adjustment_status == "reduced":
            reduced_percent = st.slider(
                "Сколько % нагрузки реально осталось:",
                min_value=35,
                max_value=95,
                value=70,
                step=5,
            )
            plan_adjustment_reduced_share = reduced_percent / 100.0
        elif plan_adjustment_status == "unavailable":
            st.caption("План временно упростит 1-2 недели и вернёт нагрузку только в коротком безопасном окне.")
        elif plan_adjustment_status == "completed":
            st.caption("Checkpoint фиксирует, что неделя закрыта по плану. Дополнительная коррекция не нужна.")
        else:
            st.caption("Если реальная неделя пошла не по плану, отметьте это здесь — локально, без полной перестройки цикла.")

    plan_adjustment_payload = {
        "status": plan_adjustment_status,
        "weeks": 0 if plan_adjustment_status == "none" else plan_adjustment_weeks,
        "missed_sessions": plan_adjustment_missed_sessions,
        "reduced_load_share": plan_adjustment_reduced_share,
    }

    target_control = _resolve_target_weekly_tss_control(
        auto_suggested=auto["suggested"],
        t_min=t_min,
        t_max=t_max,
        availability_cap_tss=availability_cap_tss,
    )

    with st.container(border=True):
        preview_cols = st.columns(5)
        with preview_cols[0]:
            st.metric("Часы / нед", f"{availability_preview['available_hours']}")
        with preview_cols[1]:
            st.metric("Доступных дней", availability_preview["available_day_count"])
        with preview_cols[2]:
            st.metric("Ограничение", interruption_label)
        with preview_cols[3]:
            st.metric("Checkpoint", plan_adjustment_label)
        with preview_cols[4]:
            st.metric("Реакция", _strategy_label(catch_up_strategy))
        st.caption(
            "Доступность сейчас ≈ "
            f"{availability_preview['available_hours']} ч/нед, "
            f"{availability_preview['available_day_count']} дн. из рекомендованных {availability_preview['recommended_days']} "
            f"→ мягкий потолок около {availability_cap_tss} TSS/нед."
        )
        if plan_adjustment_status in {"skipped", "reduced", "unavailable"}:
            st.caption(
                f"Локальная перепланировка активна: {plan_adjustment_label.lower()} "
                f"на {plan_adjustment_weeks} нед. План изменит только ближайший горизонт и короткое окно возврата нагрузки."
            )
    if availability_cap_tss < int(auto["suggested"] or 0):
        st.warning(
            f"Текущая доступность ограничивает план примерно до {availability_cap_tss} TSS/нед. "
            "Пик выше этого значения будет автоматически урезан."
        )

    if target_control["is_fixed"]:
        target_weekly_tss = int(target_control["value"])
        st.metric("Целевой недельный TSS к пику", target_weekly_tss)
        if target_control["reason"] == "availability_cap":
            st.caption(
                "Под текущую доступность реалистичный пик уже зафиксирован. "
                "Он ниже типового диапазона для этой цели, поэтому план будет строиться от достижимого потолка."
            )
        else:
            st.caption("Для этой цели и текущей доступности доступен один реалистичный пик нагрузки.")
    else:
        target_slider_step = _resolve_target_weekly_tss_step(
            int(target_control["slider_min"]),
            int(target_control["slider_max"]),
        )
        target_weekly_tss = st.slider(
            "Целевой недельный TSS к пику:",
            min_value=int(target_control["slider_min"]),
            max_value=int(target_control["slider_max"]),
            value=int(target_control["value"]),
            step=target_slider_step,
            help="Ориентир под дистанцию и доступность; фактический план дальше дополнительно учитывает ограничения и стратегию возврата нагрузки.",
        )

    with st.expander("⚙️ Продвинутые настройки распределения", expanded=False):
        st.caption("Обычно этот блок не нужен. Используйте его, только если хотите вручную управлять миксом дисциплин и днями внутри недели.")
        phases_all = ["Base", "Build", "Peak", "Taper"]
        if "planner_mix" not in state:
            state.planner_mix = {}
        if "planner_weights" not in state:
            state.planner_weights = {}

        prev_goal = state.planner_goal_type
        if prev_goal != goal_type:
            state.planner_goal_type = goal_type
            state.planner_mix = {}
            state.planner_weights = {}
            for phase in phases_all:
                for key in (f"mix_bike_{phase}", f"mix_run_{phase}", f"mix_swim_{phase}"):
                    state.pop(key, None)
                for i in range(7):
                    for key in (f"w_run_{phase}_{i}", f"w_bike_{phase}_{i}", f"w_swim_{phase}_{i}"):
                        state.pop(key, None)

        tabs = st.tabs(phases_all)
        from models.training_planner import daily_weights_for_phase, triathlon_weekly_mix

        for phase, tab in zip(phases_all, tabs):
            with tab:
                st.caption("Проценты TSS по видам спорта (нормализуются автоматически)")
                if goal_type == "Бег":
                    default_mix = {"run": 1.0, "bike": 0.0, "swim": 0.0}
                elif goal_type == "Вело":
                    default_mix = {"run": 0.0, "bike": 1.0, "swim": 0.0}
                else:
                    default_mix = triathlon_weekly_mix(distance, phase)
                stored_mix = state.planner_mix.get(phase, default_mix)
                bike = st.slider(
                    f"{phase} • Bike %",
                    0,
                    100,
                    int(round(stored_mix.get("bike", default_mix["bike"]) * 100)),
                    key=f"mix_bike_{phase}",
                )
                run = st.slider(
                    f"{phase} • Run %",
                    0,
                    100,
                    int(round(stored_mix.get("run", default_mix["run"]) * 100)),
                    key=f"mix_run_{phase}",
                )
                swim = st.slider(
                    f"{phase} • Swim %",
                    0,
                    100,
                    int(round(stored_mix.get("swim", default_mix["swim"]) * 100)),
                    key=f"mix_swim_{phase}",
                )
                total = bike + run + swim
                if total == 0:
                    mix_norm = default_mix
                else:
                    mix_norm = {"bike": bike / total, "run": run / total, "swim": swim / total}
                state.planner_mix[phase] = mix_norm
                st.caption(f"Сумма: {bike + run + swim}% → будет нормализовано до 100%")

                st.divider()
                st.caption("Дневные веса (Пн..Вс) для каждого вида спорта. Значения нормализуются к 100% на неделю.")
                default_w = daily_weights_for_phase(phase)
                stored_w = state.planner_weights.get(phase, default_w)
                days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                cols_run = st.columns(7)
                run_vals = []
                for i, col in enumerate(cols_run):
                    with col:
                        val = col.number_input(
                            f"Run {days[i]}",
                            min_value=0.0,
                            max_value=1.0,
                            step=0.05,
                            value=float(stored_w.get("run", default_w["run"])[i]),
                            key=f"w_run_{phase}_{i}",
                        )
                        run_vals.append(val)
                cols_bike = st.columns(7)
                bike_vals = []
                for i, col in enumerate(cols_bike):
                    with col:
                        val = col.number_input(
                            f"Bike {days[i]}",
                            min_value=0.0,
                            max_value=1.0,
                            step=0.05,
                            value=float(stored_w.get("bike", default_w["bike"])[i]),
                            key=f"w_bike_{phase}_{i}",
                        )
                        bike_vals.append(val)
                cols_swim = st.columns(7)
                swim_vals = []
                for i, col in enumerate(cols_swim):
                    with col:
                        val = col.number_input(
                            f"Swim {days[i]}",
                            min_value=0.0,
                            max_value=1.0,
                            step=0.05,
                            value=float(stored_w.get("swim", default_w["swim"])[i]),
                            key=f"w_swim_{phase}_{i}",
                        )
                        swim_vals.append(val)
                state.planner_weights[phase] = {"run": run_vals, "bike": bike_vals, "swim": swim_vals}

    if st.button("🧭 Построить план до старта"):
        from models.planning_checkpoints import build_planning_checkpoint, with_checkpoint_provenance
        from models.training_planner import build_daily_session_templates

        base_weekly_tss_plan = create_weekly_tss_plan(
            start_weekly_tss=start_weekly_tss_guess,
            weeks_total=weeks_to_race,
            target_weekly_tss=target_weekly_tss,
            deload_every=4,
            taper_weeks=2,
            max_ramp=0.10,
        )

        today = datetime.now().date()
        start_week = today - timedelta(days=today.weekday())
        phases = compute_phase_schedule(weeks_to_race)
        mix_overrides = state.planner_mix or None
        if not mix_overrides:
            if goal_type == "Бег":
                mix_overrides = {phase: {"run": 1.0, "bike": 0.0, "swim": 0.0} for phase in phases}
            elif goal_type == "Вело":
                mix_overrides = {phase: {"run": 0.0, "bike": 1.0, "swim": 0.0} for phase in phases}
        weekly_tss_plan, constraint_details, constraint_summary = apply_planning_constraints(
            base_weekly_tss_plan,
            phases,
            goal_type,
            available_hours=available_hours,
            available_day_indices=selected_day_indices,
            interruption_type=interruption_key_map.get(interruption_label, "none"),
            interruption_weeks=interruption_weeks if interruption_label != "Нет" else 0,
            catch_up_strategy=catch_up_strategy,
            current_tsb=float(current_metrics.get("tsb", 0.0)) if current_metrics.get("tsb") is not None else None,
            current_ctl=float(current_metrics.get("ctl", 0.0)) if current_metrics.get("ctl") is not None else None,
            current_atl=float(current_metrics.get("atl", 0.0)) if current_metrics.get("atl") is not None else None,
            plan_adjustment=plan_adjustment_payload,
        )
        weights_overrides = state.planner_weights or None
        daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
            weekly_tss_plan,
            phases,
            distance,
            start_week,
            mix_overrides=mix_overrides,
            weights_overrides=weights_overrides,
            available_day_indices=selected_day_indices,
            goal_type=goal_type,
            load_state=str(constraint_summary.get("load_state", "balanced")),
        )
        daily_seq = flatten_daily_total(daily_plan)
        for week_row, detail in zip(weekly_summary, constraint_details):
            week_row["capacity_tss"] = detail.get("capacity_tss")
            week_row["adjustment_note"] = detail.get("adjustment_note", "—")
        session_templates = build_daily_session_templates(
            daily_plan,
            weekly_summary,
            goal_type=goal_type,
            distance=distance,
        )

        goal_plan_payload = with_checkpoint_provenance(
            {
            "goal_type": goal_type,
            "distance": distance,
            "weeks_to_race": weeks_to_race,
            "start_week": start_week,
            "weekly_tss_plan": weekly_tss_plan,
            "base_weekly_tss_plan": base_weekly_tss_plan,
            "phases": phases,
            "daily_plan": daily_plan,
            "session_templates": session_templates,
            "weekly_summary": weekly_summary,
            "constraint_summary": constraint_summary,
            "planner_mix": mix_overrides,
            "planner_weights": weights_overrides,
            "plan_revision": datetime.now().isoformat(),
            "near_term_edit_version": 0,
            "near_term_edit_rollback_target_checkpoint_id": None,
            },
            source="initial_plan",
        )
        state.goal_plan = goal_plan_payload
        state.last_execution_feedback_result = None
        saved_checkpoint = state.database.save_planning_checkpoint(
            build_planning_checkpoint(goal_plan_payload)
        )
        state.latest_planning_checkpoint = saved_checkpoint
        state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
        st.rerun()

    if state.goal_plan:
        from models.planning_checkpoints import (
            build_planning_checkpoint,
            get_near_term_edit_rollback_target_checkpoint_id,
            restore_goal_plan_from_checkpoint,
            summarize_execution_feedback_transition,
            with_checkpoint_provenance,
        )
        from ui.components.execution_feedback import render_execution_feedback_editor

        goal_plan = state.goal_plan
        flash_message = st.session_state.pop("planning_near_term_flash", None)
        if flash_message:
            st.success(flash_message)

        execution_feedback_result = render_execution_feedback_editor(
            goal_plan,
            key_prefix="planning_execution_feedback",
            title="### ♻️ Факт выполнения по дням",
        )
        if execution_feedback_result is not None:
            latest_checkpoint = getattr(state, "latest_planning_checkpoint", None)
            updated_goal_plan = rebuild_goal_plan_with_adjustment(
                goal_plan,
                execution_feedback_result["plan_adjustment"],
            )
            updated_goal_plan = with_checkpoint_provenance(
                updated_goal_plan,
                source="execution_feedback",
                parent_checkpoint_id=(latest_checkpoint or {}).get("id") if isinstance(latest_checkpoint, dict) else None,
            )
            state.goal_plan = updated_goal_plan
            saved_checkpoint = state.database.save_planning_checkpoint(
                build_planning_checkpoint(updated_goal_plan)
            )
            state.latest_planning_checkpoint = saved_checkpoint
            state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
            state.last_execution_feedback_result = summarize_execution_feedback_transition(
                latest_checkpoint,
                saved_checkpoint,
            )
            execution_reconciliation = execution_feedback_result["plan_adjustment"].get("execution_reconciliation")
            if isinstance(execution_reconciliation, dict) and execution_reconciliation.get("changed_day_count", 0) > 0:
                st.session_state["planning_near_term_flash"] = (
                    "Execution checkpoint сохранён: "
                    f"{execution_reconciliation['compact_label']}."
                )
            else:
                st.session_state["planning_near_term_flash"] = "Execution checkpoint сохранён."
            st.rerun()

        rollback_goal_plan = None
        latest_checkpoint = getattr(state, "latest_planning_checkpoint", None)
        rollback_target_checkpoint_id = get_near_term_edit_rollback_target_checkpoint_id(latest_checkpoint)
        if rollback_target_checkpoint_id is not None:
            rollback_checkpoint = state.database.get_planning_checkpoint(rollback_target_checkpoint_id)
            rollback_goal_plan = restore_goal_plan_from_checkpoint(rollback_checkpoint)
            if not isinstance(rollback_goal_plan, dict) or not rollback_goal_plan.get("daily_plan"):
                rollback_goal_plan = None

        updated_goal_plan = _render_near_term_editor(
            goal_plan,
            rollback_goal_plan=rollback_goal_plan,
            rollback_checkpoint_id=rollback_target_checkpoint_id,
        )
        if updated_goal_plan is None:
            updated_goal_plan = _render_planning_version_history(
                goal_plan,
                latest_checkpoint,
                getattr(state, "planning_checkpoint_history", []),
            )
        if updated_goal_plan is not None:
            planning_action = str(updated_goal_plan.pop("_transient_planning_action", "") or "")
            restored_from_checkpoint_id = updated_goal_plan.pop("_transient_restore_checkpoint_id", None)
            near_term_summary = summarize_near_term_edit(updated_goal_plan.get("constraint_summary", {}))
            latest_checkpoint_id = (latest_checkpoint or {}).get("id") if isinstance(latest_checkpoint, dict) else None
            if planning_action in {"rollback_near_term_edit", "restore_checkpoint_version"}:
                updated_goal_plan = with_checkpoint_provenance(
                    updated_goal_plan,
                    source="restore_version",
                    parent_checkpoint_id=latest_checkpoint_id,
                    restored_from_checkpoint_id=restored_from_checkpoint_id,
                )
            else:
                updated_goal_plan = with_checkpoint_provenance(
                    updated_goal_plan,
                    source="manual_edit",
                    parent_checkpoint_id=latest_checkpoint_id,
                )
                if near_term_summary is not None and latest_checkpoint_id is not None:
                    updated_goal_plan["near_term_edit_rollback_target_checkpoint_id"] = latest_checkpoint_id
                elif near_term_summary is None:
                    updated_goal_plan.pop("near_term_edit_rollback_target_checkpoint_id", None)

            state.goal_plan = updated_goal_plan
            state.last_execution_feedback_result = None
            saved_checkpoint = state.database.save_planning_checkpoint(
                build_planning_checkpoint(updated_goal_plan)
            )
            state.latest_planning_checkpoint = saved_checkpoint
            state.planning_checkpoint_history = state.database.get_recent_planning_checkpoints(limit=6)
            if planning_action == "rollback_near_term_edit":
                if near_term_summary is not None:
                    st.session_state["planning_near_term_flash"] = (
                        "Откат выполнен. Активная версия: "
                        f"{near_term_summary['compact_label']}."
                    )
                else:
                    st.session_state["planning_near_term_flash"] = "Последняя ручная правка ближнего горизонта откатана."
            elif planning_action == "restore_checkpoint_version":
                if restored_from_checkpoint_id is not None:
                    st.session_state["planning_near_term_flash"] = (
                        f"Версия checkpoint #{int(restored_from_checkpoint_id)} восстановлена."
                    )
                else:
                    st.session_state["planning_near_term_flash"] = "Сохранённая версия плана восстановлена."
            else:
                if near_term_summary is not None:
                    st.session_state["planning_near_term_flash"] = (
                        "Ближний горизонт обновлён: "
                        f"{near_term_summary['compact_label']}."
                    )
                    if near_term_summary["risk_level"] != "low":
                        st.session_state["planning_near_term_flash"] += (
                            f" Оценка: {near_term_summary['risk_badge']}."
                        )
                else:
                    st.session_state["planning_near_term_flash"] = "Ближний горизонт обновлён."
            st.rerun()
            return

        goal_plan = state.goal_plan
        daily_plan = goal_plan["daily_plan"]
        weekly_summary = goal_plan["weekly_summary"]
        start_week = goal_plan["start_week"]
        goal_type_cached = goal_plan.get("goal_type", goal_type)
        distance_cached = goal_plan.get("distance", distance)
        session_templates = goal_plan.get("session_templates", [])

        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, flatten_daily_total(daily_plan), start_date=datetime.combine(start_week, datetime.min.time())
        )
        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type_cached} • {distance_cached})")
        st.plotly_chart(fig_future, width="stretch")

        comparison_df = _render_plan_explainability(goal_plan)
        daily_session_rows = _build_daily_session_rows(goal_plan)
        df_plan = pd.DataFrame(weekly_summary)
        df_plan["Неделя от"] = df_plan["week_start"].apply(lambda d: d.strftime("%d.%m"))
        plan_columns = ["Неделя от", "phase", "weekly_tss", "bike", "run", "swim"]
        if "capacity_tss" in df_plan.columns:
            plan_columns.append("capacity_tss")
        if "adjustment_note" in df_plan.columns:
            plan_columns.append("adjustment_note")
        if "structure_summary" in df_plan.columns:
            plan_columns.append("structure_summary")
        if "key_sessions" in df_plan.columns:
            plan_columns.append("key_sessions")
        if "recovery_days" in df_plan.columns:
            plan_columns.append("recovery_days")
        df_plan = df_plan[plan_columns]
        df_plan.rename(
            columns={
                "phase": "Фаза",
                "weekly_tss": "Weekly TSS",
                "bike": "Bike",
                "run": "Run",
                "swim": "Swim",
                "capacity_tss": "Потолок TSS",
                "adjustment_note": "Коррекция",
                "structure_summary": "Структура недели",
                "key_sessions": "Ключевые сессии",
                "recovery_days": "Восстановление",
            },
            inplace=True,
        )
        with st.expander("📋 Подробная Разбивка По Неделям И Дисциплинам", expanded=False):
            st.dataframe(df_plan, width="stretch", hide_index=True)

        df_daily = pd.DataFrame(daily_session_rows)
        with st.expander("🗓️ Структура Дней И Восстановления", expanded=False):
            st.dataframe(df_daily, width="stretch", hide_index=True)

        near_term_export_summary = summarize_near_term_edit(goal_plan.get("constraint_summary", {}))
        if near_term_export_summary is not None:
            st.caption(
                "Экспорты и sync уже используют вручную обновлённый ближний горизонт: "
                f"{near_term_export_summary['compact_label']}."
            )

        export_cols = st.columns(3)
        with export_cols[0]:
            csv_weekly = comparison_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Сравнение до/после (CSV)",
                data=csv_weekly,
                file_name="weekly_plan_comparison.csv",
                mime="text/csv",
            )
        with export_cols[1]:
            weekly_detail_csv = df_plan.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Детали по неделям (CSV)",
                data=weekly_detail_csv,
                file_name="weekly_plan.csv",
                mime="text/csv",
            )

        with export_cols[2]:
            csv_daily = df_daily.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Дневной план (CSV)",
                data=csv_daily,
                file_name="daily_plan.csv",
                mime="text/csv",
            )

        from models.training_planner import create_ics_from_daily

        ics_content = create_ics_from_daily(
            daily_plan,
            title_prefix=f"{goal_type_cached} {distance_cached}",
            session_templates=session_templates,
        )
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        total_days = len(daily_plan)
        total_weeks = max(1, (total_days + 6) // 7)

        st.markdown("### 📤 Intervals.icu")
        intervals_info = intervals_icu.connection_info()
        if intervals_info.get("configured"):
            st.caption(
                "Personal API key найден: "
                f"athlete_id={intervals_info.get('athlete_id', '0')} · {intervals_info.get('base_url', 'https://intervals.icu')}"
            )

            col_int_1, col_int_2, col_int_3 = st.columns([1.2, 1, 1])
            with col_int_1:
                if st.button("🔎 Проверить подключение", key="intervals_test_connection"):
                    try:
                        result = intervals_icu.test_connection()
                        calendar_count = result.get("calendar_count")
                        if calendar_count is None:
                            st.success("Intervals.icu ответил корректно.")
                        else:
                            st.success(f"Intervals.icu подключён. Найдено календарей: {calendar_count}.")
                    except intervals_icu.IntervalsICUError as exc:
                        st.error(str(exc))

            with col_int_2:
                intervals_day_number = st.number_input(
                    "День плана",
                    min_value=1,
                    max_value=total_days,
                    value=1,
                    key="intervals_day_number",
                )

            with col_int_3:
                intervals_week_number = st.number_input(
                    "Неделя плана",
                    min_value=1,
                    max_value=total_weeks,
                    value=1,
                    key="intervals_week_number",
                )

            col_int_4, col_int_5 = st.columns(2)

            with col_int_4:
                if st.button("📤 Отправить день в Intervals.icu", key="intervals_push_day"):
                    day_index = int(intervals_day_number) - 1
                    selected_day = [daily_plan[day_index]]
                    selected_templates = session_templates[day_index:day_index + 1]
                    events = intervals_icu.build_planned_events(
                        selected_day,
                        goal_type_cached,
                        distance_cached,
                        session_templates=selected_templates,
                    )
                    if not events:
                        st.warning("Выбранный день не содержит достаточной тренировочной нагрузки для отправки.")
                    else:
                        try:
                            created = intervals_icu.push_planned_events(events)
                            event_name = events[0].get("name", "planned workout")
                            created_count = len(created)
                            st.success(f"Отправлено {created_count} событие: {event_name}.")
                        except intervals_icu.IntervalsICUError as exc:
                            st.error(str(exc))

            with col_int_5:
                if st.button("📤 Отправить неделю в Intervals.icu", key="intervals_push_week"):
                    start_idx = (int(intervals_week_number) - 1) * 7
                    end_idx = min(start_idx + 7, total_days)
                    selected_days = daily_plan[start_idx:end_idx]
                    selected_templates = session_templates[start_idx:end_idx]
                    events = intervals_icu.build_planned_events(
                        selected_days,
                        goal_type_cached,
                        distance_cached,
                        session_templates=selected_templates,
                    )
                    if not events:
                        st.warning("В выбранной неделе нет дней с достаточной нагрузкой для отправки.")
                    else:
                        try:
                            created = intervals_icu.push_planned_events(events)
                            st.success(
                                f"Отправлено {len(created)} planned workouts в Intervals.icu "
                                f"за неделю {int(intervals_week_number)}."
                            )
                        except intervals_icu.IntervalsICUError as exc:
                            st.error(str(exc))
        else:
            st.info(
                "Чтобы отправлять planned workouts в Intervals.icu, укажите "
                "`INTERVALS_ICU_API_KEY` в `.env`. `INTERVALS_ICU_ATHLETE_ID=0` подходит для персонального аккаунта."
            )

        st.markdown("### 🧩 Экспорт тренировки (FIT-CSV / FIT / TCX)")
        day_idx = st.number_input("День недели (1=Пн … 7=Вс)", min_value=1, max_value=7, value=1, key="fit_day")
        if st.button("⬇️ Экспортировать выбранный день в FIT-CSV / FIT", key="export_fit_day"):
            from config.settings import Settings
            from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
            from models.tcx_activity_export import generate_tcx_activity
            from models.tcx_export import generate_tcx_workout

            day_index = day_idx - 1
            day = daily_plan[day_index]
            dt, total, parts = day
            session_template = session_templates[day_index] if day_index < len(session_templates) else {}
            sport = _infer_sport_for_export(parts, session_template)
            steps = build_steps_for_sport(
                total,
                sport,
                session_role=str(session_template.get("session_role", "easy")),
                phase=session_template.get("phase"),
            )
            workout_name = str(
                session_template.get("export_name")
                or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
            )
            csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
            csv_bytes = csv_text.encode("utf-8")

            colf1, colf2, colf3, colf4 = st.columns(4)
            with colf1:
                st.download_button(
                    label="💾 Скачать FIT-CSV",
                    data=csv_bytes,
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            with colf2:
                jar = Settings.FIT_SDK_JAR
                fit_bytes, out_s, err_s, rc = try_convert_fit_verbose(csv_bytes, "java", jar) if jar else (None, "", "FIT_SDK_JAR не задан", 127)
                if fit_bytes and rc == 0:
                    st.download_button(
                        label="💾 Скачать FIT",
                        data=fit_bytes,
                        file_name=f"workout_{dt.strftime('%Y%m%d')}.fit",
                        mime="application/octet-stream",
                    )
                else:
                    if rc != 0:
                        st.warning("FIT не собран. Логи FitCSVTool:")
                        if out_s:
                            st.code(out_s)
                        if err_s:
                            st.code(err_s)
                    else:
                        st.info("Чтобы собрать .FIT внутри приложения, укажите путь к FitCSVTool.jar в переменной окружения FIT_SDK_JAR.")
            with colf3:
                tcx_text = generate_tcx_workout(workout_name, sport, steps, created=dt)
                st.download_button(
                    label="💾 Скачать TCX",
                    data=tcx_text.encode("utf-8"),
                    file_name=f"workout_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                )
            with colf4:
                tcx_act = generate_tcx_activity(workout_name, sport, steps, start_time=datetime.combine(dt.date(), datetime.min.time()))
                st.download_button(
                    label="💾 TCX Activity (импорт)",
                    data=tcx_act.encode("utf-8"),
                    file_name=f"activity_{dt.strftime('%Y%m%d')}.tcx",
                    mime="application/vnd.garmin.tcx+xml",
                    help="Используйте этот файл на странице Импорт данных в Garmin Connect",
                )

        with st.expander("📦 Экспорт всей недели (ZIP)", expanded=False):
            week_idx = st.number_input("Номер недели (1=первая)", min_value=1, max_value=total_weeks, value=1, key="fit_week_idx")
            if st.button("⬇️ Собрать ZIP с FIT-CSV/FIT/TCX", key="export_fit_week_zip"):
                import io
                import zipfile

                from config.settings import Settings
                from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
                from models.tcx_export import generate_tcx_workout

                jar = Settings.FIT_SDK_JAR

                start = (week_idx - 1) * 7
                end = min(start + 7, total_days)
                week_days = daily_plan[start:end]
                week_templates = session_templates[start:end]

                csv_zip = io.BytesIO()
                tcx_zip = io.BytesIO()
                with zipfile.ZipFile(csv_zip, "w", zipfile.ZIP_DEFLATED) as csv_archive, zipfile.ZipFile(
                    tcx_zip, "w", zipfile.ZIP_DEFLATED
                ) as tcx_archive:
                    for day_offset, (dt, total, parts) in enumerate(week_days):
                        session_template = week_templates[day_offset] if day_offset < len(week_templates) else {}
                        sport = _infer_sport_for_export(parts, session_template)
                        steps = build_steps_for_sport(
                            total,
                            sport,
                            session_role=str(session_template.get("session_role", "easy")),
                            phase=session_template.get("phase"),
                        )
                        workout_name = str(
                            session_template.get("export_name")
                            or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
                        )
                        csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
                        csv_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.csv", csv_text)
                        tcx_text = generate_tcx_workout(workout_name, sport, steps, created=dt)
                        tcx_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.tcx", tcx_text)
                st.download_button(
                    label="💾 Скачать все FIT-CSV (ZIP)",
                    data=csv_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_fitcsv.zip",
                    mime="application/zip",
                    key="dl_fitcsv_week_zip",
                )
                st.download_button(
                    label="💾 Скачать все TCX (ZIP)",
                    data=tcx_zip.getvalue(),
                    file_name=f"week_{week_idx:02d}_tcx.zip",
                    mime="application/zip",
                    key="dl_tcx_week_zip",
                )

                if jar:
                    fit_zip = io.BytesIO()
                    failed_days = 0
                    with zipfile.ZipFile(fit_zip, "w", zipfile.ZIP_DEFLATED) as fit_archive:
                        for day_offset, (dt, total, parts) in enumerate(week_days):
                            session_template = week_templates[day_offset] if day_offset < len(week_templates) else {}
                            sport = _infer_sport_for_export(parts, session_template)
                            steps = build_steps_for_sport(
                                total,
                                sport,
                                session_role=str(session_template.get("session_role", "easy")),
                                phase=session_template.get("phase"),
                            )
                            workout_name = str(
                                session_template.get("export_name")
                                or f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
                            )
                            csv_text = generate_fit_csv(workout_name, sport, steps, created=dt)
                            fit_bytes, _, _, rc = try_convert_fit_verbose(csv_text.encode("utf-8"), "java", jar)
                            if fit_bytes and rc == 0:
                                fit_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.fit", fit_bytes)
                            else:
                                failed_days += 1
                    if fit_zip.getbuffer().nbytes > 0:
                        st.download_button(
                            label="💾 Скачать все FIT (ZIP)",
                            data=fit_zip.getvalue(),
                            file_name=f"week_{week_idx:02d}_fit.zip",
                            mime="application/zip",
                            key="dl_fit_week_zip",
                        )
                    if failed_days:
                        st.info(f"Не удалось собрать FIT для {failed_days} дн. Проверьте FIT_SDK_JAR/Java или структуру CSV.")

        if st.button("♻️ Сбросить план"):
            state.reset_planner_overrides()
            st.success("План сброшен")
            st.rerun()

    st.subheader("📈 Дополнительная статистика")

    col1, col2 = st.columns(2)

    with col1:
        if not activities_df.empty and "tss" in activities_df.columns:
            fig_tss_dist = Visualizations.create_tss_distribution_chart(activities_df)
            st.plotly_chart(fig_tss_dist, width="stretch")

    with col2:
        if not activities_df.empty:
            fig_weekly = Visualizations.create_weekly_tss_chart(activities_df)
            st.plotly_chart(fig_weekly, width="stretch")
