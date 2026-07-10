"""Headless Markdown presentation for AI coach tool results."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from utils.product_semantics import (
    TODAY_PARTIAL_NOTE_RU,
    format_date_label,
    sport_emoji,
    sport_label,
    training_status_label,
    trend_label,
)


def format_tool_result(tool_name: str, data: Any) -> str:
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

        activities_text = f"## 🏃‍♂️ Последние {min(5, data['count'])} тренировок:\n\n"
        for i, activity in enumerate(data["activities"][:5], 1):
            sport = activity.get("sport_label") or sport_label(activity.get("sport"))
            emoji = sport_emoji(activity.get("sport"))
            date_text = activity.get("date_label") or format_date_label(activity.get("date"), "weekday_short")
            if activity.get("is_today_partial") and TODAY_PARTIAL_NOTE_RU not in date_text:
                date_text = f"{date_text} {TODAY_PARTIAL_NOTE_RU}"
            description = activity.get("description") or f"{sport} — {activity.get('duration_minutes', 0):.0f} мин"
            activities_text += f"{i}. **{date_text}** {emoji} {description}\n"

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

        rows = []
        for activity in activities[:7]:
            date = activity.get("date_label") or format_date_label(activity.get("date"), "weekday_short")
            sport = activity.get("sport_label") or sport_label(activity.get("sport"))
            emoji = sport_emoji(activity.get("sport"))
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
        trend_direction = data.get("trend_direction")
        trend_text = data.get("trend_direction_label") or trend_label(trend_direction)

        return f"""
**💓 Анализ HRV:**
• Текущий RMSSD: {data['current_rmssd']:.1f} мс
• Среднее за 7 дней: {data['recent_avg_7days']:.1f} мс
• Базовый уровень: {data['baseline_median']:.1f} мс
• Тренд: {trend_emoji.get(trend_direction, '')} {trend_text}
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
            date_str = entry.get("date_label") or format_date_label(entry.get("date"), "weekday_short")
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
• Статус Garmin: {latest.get('training_status_label') or training_status_label(latest.get('training_status'))}
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
        trend = data.get("trend_steps_label") or trend_label(data.get("trend_steps"))
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
            date = entry.get("date_label") or format_date_label(entry.get("date"), "weekday_short")
            if entry.get("is_today_partial") and TODAY_PARTIAL_NOTE_RU not in date:
                date = f"{date} {TODAY_PARTIAL_NOTE_RU}"
            steps = fmt_number(entry.get("steps"), ".0f")
            resting_hr = fmt_number(entry.get("resting_hr"), ".0f")
            active_minutes = fmt_number(entry.get("active_minutes"), ".0f")
            recent_lines.append(f"• {date}: шаги {steps}, ЧСС покоя {resting_hr}, активность {active_minutes} мин")

        averages_note = (
            " — без сегодняшнего неполного дня"
            if data.get("aggregates_exclude_today")
            else ""
        )

        return f"""
## 🏥 Ежедневные показатели здоровья ({data.get('period_days', 30)} дней)

### 📊 Средние значения{averages_note}:
• Шаги: {fmt_number(stats.get('avg_steps'), '.0f')} в день
• ЧСС покоя: {fmt_number(stats.get('avg_resting_hr'), '.1f')} уд/мин
• Активные минуты: {fmt_number(stats.get('avg_active_minutes'), '.1f')} мин/день
• Активные калории: {fmt_number(stats.get('avg_calories_active'), '.0f')} ккал/день

### 📈 Тренд шагов: {trend}

### 🗓️ Последние дни:
{chr(10).join(recent_lines) if recent_lines else "• Нет свежих записей"}
"""

    elif tool_name == "get_active_plan":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if not data.get("has_plan"):
            return f"ℹ️ **{data.get('message', 'Активный план не найден')}**"

        goal = data.get("goal", {}) or {}
        timeline = data.get("timeline", {}) or {}
        current = data.get("current_week")
        totals = data.get("totals", {}) or {}
        weeks = data.get("weeks_preview", []) or []
        events = [event for event in data.get("events", []) or [] if isinstance(event, dict)]

        goal_line = " ".join(part for part in [goal.get("goal_type"), goal.get("distance")] if part) or "н/д"
        race_date = goal.get("event_date") or timeline.get("plan_end")
        race_label = format_date_label(race_date, "weekday_short") if race_date else "н/д"
        weeks_remaining = timeline.get("weeks_remaining", goal.get("weeks_to_race", "н/д"))
        if events:
            event_lines = [
                f"• {str(event.get('priority') or '—').upper()} · "
                f"{event.get('label') or 'Старт'} — "
                f"{format_date_label(event.get('date'), 'weekday_short')}"
                for event in events
            ]
            events_block = "\n".join(event_lines)
        else:
            events_block = "• Нет сохранённых стартов"

        if current:
            current_block = (
                f"### 📍 Текущая неделя: {current.get('index', 'н/д')} из {totals.get('total_weeks', 'н/д')}\n"
                f"• Даты: {format_date_label(current.get('week_start'), 'weekday_short')} — "
                f"{format_date_label(current.get('week_end'), 'weekday_short')}\n"
                f"• Фаза: {current.get('phase') or 'н/д'}\n"
                f"• Плановый TSS: **{current.get('weekly_tss', 'н/д')}**"
            )
        elif timeline.get("status") == "not_started":
            start_label = format_date_label(timeline.get("plan_start"), "weekday_short")
            current_block = f"### 📍 План ещё не начался (старт {start_label})"
        elif timeline.get("status") == "completed":
            current_block = "### 📍 План завершён"
        else:
            current_block = "### 📍 Текущая неделя не определена"

        if weeks:
            table_rows = ["| Неделя | Старт недели | Фаза | TSS |", "| --- | --- | --- | --- |"]
            for week in weeks:
                marker = " ← текущая" if week.get("is_current") else ""
                table_rows.append(
                    f"| {week.get('week', '—')}{marker} | {format_date_label(week.get('week_start'), 'weekday_short')} | "
                    f"{week.get('phase') or '—'} | {week.get('weekly_tss', 0)} |"
                )
            weeks_section = "\n".join(table_rows)
        else:
            weeks_section = "Нет разбивки по неделям."

        return f"""
## 🗓️ Активный план

### 🎯 Цель:
• {goal_line}
• Старт: {race_label}
• До старта: **{weeks_remaining} нед.**

### 🏁 Старты:
{events_block}

{current_block}

### 📅 Недели плана:
{weeks_section}

### 📊 Итого:
• Недель в плане: {totals.get('total_weeks', 'н/д')}
• Общий TSS: {totals.get('total_tss', 'н/д')}
• Пик TSS/нед: {totals.get('peak_tss', 'н/д')}
"""

    elif tool_name == "get_upcoming_workouts":
        if not isinstance(data, dict):
            return f"ℹ️ **{data}**"
        if not data.get("has_plan"):
            return f"ℹ️ **{data.get('message', 'Активный план не найден')}**"

        sessions = data.get("sessions", []) or []
        if not sessions:
            return f"ℹ️ **{data.get('message', 'Нет плановых тренировок в ближайшие дни')}**"

        session_lines = []
        for session in sessions:
            date = session.get("date_label") or format_date_label(session.get("date"), "weekday_short")
            sport = session.get("sport_label") or sport_label(session.get("sport"))
            phase = f", фаза: {session['phase']}" if session.get("phase") else ""
            session_lines.append(
                f"• {date}: **{session.get('name', 'Сессия')}** — {sport}, TSS {session.get('tss', 'н/д')}{phase}"
            )

        return f"""
## 📅 Ближайшие плановые тренировки ({data.get('days', 7)} дней)

{chr(10).join(session_lines)}
"""

    elif tool_name == "propose_plan_build":
        preview = data.get("preview", {}) if isinstance(data, dict) else {}
        params = data.get("params", {}) if isinstance(data, dict) else {}
        goal = preview.get("goal", {}) if isinstance(preview, dict) else {}

        return f"""
## 🧭 Предложение нового плана

### 🎯 Цель:
• Вид спорта: {goal.get('goal_type') or params.get('goal_type') or 'н/д'}
• Дистанция: {goal.get('distance') or params.get('distance') or 'н/д'}
• Старт: {goal.get('event_date') or params.get('event_date') or 'н/д'}
• Часов в неделю: {params.get('available_hours', 'н/д')}

### 📈 Что получилось:
• Недель в плане: {preview.get('total_weeks', 'н/д')}
• Целевой недельный TSS: {preview.get('target_weekly_tss', 'н/д')}
• Пик TSS/нед: {preview.get('peak_tss', 'н/д')}
• Общий TSS: {preview.get('total_tss', 'н/д')}

### ✅ Дальше:
Подтверди карточку ниже, если хочешь сохранить именно этот план в активный.
"""

    elif tool_name == "propose_plan_adjustment":
        preview = data.get("preview", {}) if isinstance(data, dict) else {}
        params = data.get("params", {}) if isinstance(data, dict) else {}
        is_noop = (
            isinstance(data, dict)
            and (data.get("status") == "noop" or data.get("is_proposal") is False)
        )
        completion = preview.get("completion_share")
        completion_pct = (
            f"{round(float(completion or 0) * 100):.0f}%"
            if completion is not None
            else "н/д"
        )

        if is_noop:
            return f"""
## ✅ Корректировка плана не нужна

### 📋 Проверка выполнения:
• Недель проверено: {params.get('weeks', 'н/д')}
• Статус: {preview.get('adjustment_label') or preview.get('adjustment_status') or 'н/д'}
• Пропущено сессий: {preview.get('missed_sessions', 'н/д')}
• Выполнение: {completion_pct}

### 📈 Текущий план:
• Пик TSS/нед: {preview.get('peak_tss', 'н/д')}
• Общий TSS: {preview.get('total_tss', 'н/д')}

### ✅ Дальше:
План можно оставить без изменений; подтверждение не требуется.
"""

        return f"""
## 🔧 Предложение корректировки плана

### 📋 Основание:
• Недель для пересборки: {params.get('weeks', 'н/д')}
• Пропущено сессий: {preview.get('missed_sessions', 'н/д')}
• Выполнение: {completion_pct}

### 📈 Что изменится:
• Статус: {preview.get('adjustment_label') or preview.get('adjustment_status') or 'н/д'}
• Новый пик TSS/нед: {preview.get('peak_tss', 'н/д')}
• Новый общий TSS: {preview.get('total_tss', 'н/д')}

### ✅ Дальше:
Подтверди карточку ниже, если хочешь применить именно эту корректировку.
"""

    elif tool_name == "create_plan_constraint":
        constraint = data.get("constraint", {}) if isinstance(data, dict) else {}
        application = data.get("constraint_application", {}) if isinstance(data, dict) else {}
        applied_count = int(application.get("applied_count") or 0)
        status = (
            "сохранено и применено к активному плану"
            if applied_count > 0
            else "сохранено; активный план не изменён"
        )

        return f"""
## 🧩 Ограничение плана

• Дата: {constraint.get('date', 'н/д')}
• Тип: {constraint.get('kind', 'н/д')}
• Заметка: {constraint.get('note') or '—'}
• Статус: {status}
"""

    elif tool_name == "get_activities_by_date_range":
        if data["count"] == 0:
            return f"📭 **Нет тренировок в период {data['period']}**"

        stats = data["statistics"]

        sports_text = []
        for sport, count in stats["sports_distribution"].items():
            emoji = sport_emoji(sport)
            sports_text.append(f"{emoji} {sport}: {count}")

        activities_preview = ""
        if "activities" in data and data["activities"]:
            activities_preview = "\n\n**📋 Некоторые тренировки:**"
            for i, activity in enumerate(data["activities"][:5], 1):
                sport_icon = sport_emoji(activity.get("sport"))
                date_formatted = activity.get("date_label") or format_date_label(activity.get("date"), "weekday_short")
                activity_sport = activity.get("sport_label") or sport_label(activity.get("sport"))
                activities_preview += (
                    f"\n{i}. **{date_formatted}** {sport_icon} {activity_sport} - "
                    f"{activity['duration_minutes']:.0f} мин (TSS: {activity['tss']:.0f})"
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
