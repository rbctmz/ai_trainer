"""Training planning page renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from models.banister import BanisterModel
from services.data_cache import load_activities
from state import StateManager
from utils.visualizations import Visualizations


def render_planning_page(state: StateManager) -> None:
    """Render the training planning page."""
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
        compute_phase_schedule,
        create_weekly_tss_plan,
        expand_weekly_to_daily_triathlon,
        flatten_daily_total,
        goal_target_weekly_tss,
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
        t_min, t_max = goal_target_weekly_tss(goal_type, distance)
        st.caption(f"Автонастройка: последняя неделя {auto['last_week']}, среднее 4н {auto['avg_4']}, лучшая 8н {auto['best_8']}")
        target_weekly_tss = st.slider(
            "Целевой недельный TSS к пику:",
            min_value=max(100, t_min),
            max_value=max(300, t_max),
            value=int(auto["suggested"] or int((t_min + t_max) / 2)),
            step=25,
            help="Ориентир под дистанцию; можно скорректировать",
        )

    with st.expander("⚙️ Настроить распределение (фазы, проценты, дни)", expanded=False):
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
        weekly_tss_plan = create_weekly_tss_plan(
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
        weights_overrides = state.planner_weights or None
        daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
            weekly_tss_plan,
            phases,
            distance,
            start_week,
            mix_overrides=mix_overrides,
            weights_overrides=weights_overrides,
        )
        daily_seq = flatten_daily_total(daily_plan)

        state.goal_plan = {
            "goal_type": goal_type,
            "distance": distance,
            "weeks_to_race": weeks_to_race,
            "start_week": start_week,
            "weekly_tss_plan": weekly_tss_plan,
            "phases": phases,
            "daily_plan": daily_plan,
            "weekly_summary": weekly_summary,
        }
        state._just_built_plan = True

        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, daily_seq, start_date=datetime.combine(start_week, datetime.min.time())
        )

        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type} • {distance})")
        st.plotly_chart(fig_future, width="stretch")

        df_plan = pd.DataFrame(weekly_summary)
        df_plan["Неделя от"] = df_plan["week_start"].apply(lambda d: d.strftime("%d.%m"))
        df_plan = df_plan[["Неделя от", "phase", "weekly_tss", "bike", "run", "swim"]]
        df_plan.rename(columns={"phase": "Фаза", "weekly_tss": "Weekly TSS", "bike": "Bike", "run": "Run", "swim": "Swim"}, inplace=True)
        st.dataframe(df_plan, width="stretch", hide_index=True)

        csv_weekly = df_plan.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Экспорт недельного плана (CSV)",
            data=csv_weekly,
            file_name="weekly_plan.csv",
            mime="text/csv",
        )

        daily_rows = []
        for dt, total, parts in daily_plan:
            daily_rows.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "total_tss": total,
                    "run_tss": parts.get("run", 0.0),
                    "bike_tss": parts.get("bike", 0.0),
                    "swim_tss": parts.get("swim", 0.0),
                }
            )
        df_daily = pd.DataFrame(daily_rows)
        csv_daily = df_daily.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Экспорт дневного плана (CSV)",
            data=csv_daily,
            file_name="daily_plan.csv",
            mime="text/csv",
        )

        from models.training_planner import create_ics_from_daily

        ics_content = create_ics_from_daily(daily_plan, title_prefix=f"{goal_type} {distance}")
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        st.rerun()

    if state.goal_plan:
        state.pop("_just_built_plan", None)
        goal_plan = state.goal_plan
        daily_plan = goal_plan["daily_plan"]
        weekly_summary = goal_plan["weekly_summary"]
        start_week = goal_plan["start_week"]
        goal_type_cached = goal_plan.get("goal_type", goal_type)
        distance_cached = goal_plan.get("distance", distance)

        future_dates, future_ctl, future_atl, future_tsb = banister.simulate_variable_load(
            current_metrics, flatten_daily_total(daily_plan), start_date=datetime.combine(start_week, datetime.min.time())
        )
        fig_future = Visualizations.create_banister_chart(
            future_dates, future_ctl, future_atl, future_tsb
        )
        fig_future.update_layout(title=f"Прогноз до старта ({goal_type_cached} • {distance_cached})")
        st.plotly_chart(fig_future, width="stretch")

        df_plan = pd.DataFrame(weekly_summary)
        df_plan["Неделя от"] = df_plan["week_start"].apply(lambda d: d.strftime("%d.%m"))
        df_plan = df_plan[["Неделя от", "phase", "weekly_tss", "bike", "run", "swim"]]
        df_plan.rename(columns={"phase": "Фаза", "weekly_tss": "Weekly TSS", "bike": "Bike", "run": "Run", "swim": "Swim"}, inplace=True)
        st.dataframe(df_plan, width="stretch", hide_index=True)

        csv_weekly = df_plan.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Экспорт недельного плана (CSV)",
            data=csv_weekly,
            file_name="weekly_plan.csv",
            mime="text/csv",
        )

        daily_rows = []
        for dt, total, parts in daily_plan:
            daily_rows.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "total_tss": total,
                    "run_tss": parts.get("run", 0.0),
                    "bike_tss": parts.get("bike", 0.0),
                    "swim_tss": parts.get("swim", 0.0),
                }
            )
        df_daily = pd.DataFrame(daily_rows)
        csv_daily = df_daily.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Экспорт дневного плана (CSV)",
            data=csv_daily,
            file_name="daily_plan.csv",
            mime="text/csv",
        )

        from models.training_planner import create_ics_from_daily

        ics_content = create_ics_from_daily(daily_plan, title_prefix=f"{goal_type_cached} {distance_cached}")
        st.download_button(
            label="📅 Экспорт в календарь (ICS)",
            data=ics_content,
            file_name="training_plan.ics",
            mime="text/calendar",
        )

        st.markdown("### 🧩 Экспорт тренировки (FIT-CSV / FIT / TCX)")
        day_idx = st.number_input("День недели (1=Пн … 7=Вс)", min_value=1, max_value=7, value=1, key="fit_day")
        if st.button("⬇️ Экспортировать выбранный день в FIT-CSV / FIT", key="export_fit_day"):
            from config.settings import Settings
            from models.fit_export import build_steps_for_sport, generate_fit_csv, try_convert_fit_verbose
            from models.tcx_activity_export import generate_tcx_activity
            from models.tcx_export import generate_tcx_workout

            day = daily_plan[day_idx - 1]
            dt, total, parts = day
            sport = "run"
            if parts.get("bike", 0) >= max(parts.get("run", 0), parts.get("swim", 0)):
                sport = "bike"
            elif parts.get("swim", 0) >= max(parts.get("run", 0), parts.get("bike", 0)):
                sport = "swim"
            steps = build_steps_for_sport(total, sport)
            workout_name = f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}"
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
            total_days = len(daily_plan)
            total_weeks = max(1, (total_days + 6) // 7)
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

                csv_zip = io.BytesIO()
                tcx_zip = io.BytesIO()
                with zipfile.ZipFile(csv_zip, "w", zipfile.ZIP_DEFLATED) as csv_archive, zipfile.ZipFile(
                    tcx_zip, "w", zipfile.ZIP_DEFLATED
                ) as tcx_archive:
                    for dt, total, parts in week_days:
                        sport = "run"
                        if parts.get("bike", 0) >= max(parts.get("run", 0), parts.get("swim", 0)):
                            sport = "bike"
                        elif parts.get("swim", 0) >= max(parts.get("run", 0), parts.get("bike", 0)):
                            sport = "swim"
                        steps = build_steps_for_sport(total, sport)
                        csv_text = generate_fit_csv(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
                        csv_archive.writestr(f"workout_{dt.strftime('%Y%m%d')}.csv", csv_text)
                        tcx_text = generate_tcx_workout(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
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
                        for dt, total, parts in week_days:
                            sport = "run"
                            if parts.get("bike", 0) >= max(parts.get("run", 0), parts.get("swim", 0)):
                                sport = "bike"
                            elif parts.get("swim", 0) >= max(parts.get("run", 0), parts.get("bike", 0)):
                                sport = "swim"
                            steps = build_steps_for_sport(total, sport)
                            csv_text = generate_fit_csv(f"{goal_type_cached} {distance_cached} — {dt.strftime('%Y-%m-%d')}", sport, steps, created=dt)
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
