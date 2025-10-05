#!/usr/bin/env python3
"""
Специализированные prompts для AI анализа тренировочных данных
"""

from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta


class TrainingPrompts:
    """Класс с специализированными prompts для анализа тренировок"""
    
    @staticmethod
    def get_system_prompt() -> str:
        """Базовый системный prompt для AI тренера"""
        return """Ты - персональный AI тренер по выносливости с экспертными знаниями в:
- Физиологии спорта и тренировочного процесса
- Анализе данных HRV, TSS, пульсовых зон
- Планировании тренировок на основе данных
- Принципах восстановления и адаптации

СТИЛЬ ОТВЕТОВ:
- Конкретные, практичные рекомендации
- Научно обоснованные советы
- Персонализированный подход
- Максимум 300 слов на русском языке
- Структурированный формат с эмодзи

КЛЮЧЕВЫЕ ПРИНЦИПЫ:
- TSS (Training Stress Score) отражает тренировочную нагрузку
- HRV RMSSD показывает готовность к нагрузкам 
- CTL/ATL определяют тренировочную форму
- Индивидуальность каждого спортсмена"""

    @staticmethod
    def analyze_recent_training(
        activities_df: pd.DataFrame, 
        hrv_df: pd.DataFrame,
        days: int = 7
    ) -> str:
        """Анализ недавних тренировок"""
        
        if activities_df.empty and hrv_df.empty:
            return "Данные тренировок недоступны для анализа."
        
        # Собираем статистику за период
        stats = TrainingPrompts._get_training_stats(activities_df, hrv_df, days)
        
        prompt = f"""АНАЛИЗ ТРЕНИРОВОК ЗА {days} ДНЕЙ:

📊 СТАТИСТИКА:
{stats}

Проанализируй данные и дай рекомендации по структуре:

**🎯 ТЕКУЩЕЕ СОСТОЯНИЕ** (1-2 предложения)
- Оценка тренировочной нагрузки и восстановления

**📈 ДИНАМИКА** (1-2 предложения)  
- Тренды HRV, нагрузки, адаптации

**🏃 СЛЕДУЮЩАЯ ТРЕНИРОВКА** (2-3 предложения)
- Конкретные рекомендации по интенсивности
- Тип тренировки (восстановительная/развивающая/интенсивная)

**💡 ОБЩИЕ СОВЕТЫ** (1-2 предложения)
- Ключевые моменты для оптимизации"""

        return prompt

    @staticmethod
    def analyze_workout(activity: Dict) -> str:
        """Анализ конкретной тренировки"""
        
        workout_summary = TrainingPrompts._format_activity(activity)
        
        prompt = f"""АНАЛИЗ КОНКРЕТНОЙ ТРЕНИРОВКИ:

📋 ДАННЫЕ ТРЕНИРОВКИ:
{workout_summary}

Проанализируй эту тренировку:

**⭐ ОЦЕНКА ВЫПОЛНЕНИЯ** (1-2 предложения)
- Качество тренировки, соответствие целям

**📊 ТЕХНИЧЕСКИЙ АНАЛИЗ** (2-3 предложения)
- Пульсовые зоны, темп, эффективность
- Что получилось хорошо, что можно улучшить

**🔄 ВОССТАНОВЛЕНИЕ** (1-2 предложения)
- Рекомендации по восстановлению после этой нагрузки

**📅 СЛЕДУЮЩИЕ ШАГИ** (1 предложение)
- Как использовать опыт этой тренировки"""

        return prompt

    @staticmethod
    def hrv_analysis(hrv_df: pd.DataFrame, period_days: int = 14) -> str:
        """Специализированный анализ HRV данных"""
        
        if hrv_df.empty:
            return "HRV данные недоступны для анализа."
        
        hrv_stats = TrainingPrompts._get_hrv_stats(hrv_df, period_days)
        
        prompt = f"""ЭКСПЕРТНЫЙ АНАЛИЗ HRV ЗА {period_days} ДНЕЙ:

💓 HRV ДАННЫЕ:
{hrv_stats}

Как эксперт по HRV, проанализируй:

**🔍 СОСТОЯНИЕ АВТОНОМНОЙ НЕРВНОЙ СИСТЕМЫ** (2-3 предложения)
- Интерпретация текущих значений RMSSD
- Баланс симпатической/парасимпатической активности

**📈 ТРЕНД ВОССТАНОВЛЕНИЯ** (1-2 предложения)
- Динамика HRV, признаки утомления/адаптации

**⚖️ ГОТОВНОСТЬ К НАГРУЗКАМ** (2-3 предложения)
- Рекомендации по интенсивности тренировок
- Когда планировать тяжелые/легкие дни

**🎯 ОПТИМИЗАЦИЯ** (1-2 предложения)
- Факторы для улучшения HRV (сон, стресс, питание)"""

        return prompt

    @staticmethod
    def weekly_planning(
        activities_df: pd.DataFrame,
        hrv_df: pd.DataFrame,
        goals: str = "Улучшение выносливости"
    ) -> str:
        """Планирование тренировочной недели"""
        
        current_stats = TrainingPrompts._get_training_stats(activities_df, hrv_df, 7)
        
        prompt = f"""ПЛАНИРОВАНИЕ ТРЕНИРОВОЧНОЙ НЕДЕЛИ:

🎯 ЦЕЛЬ: {goals}

📊 ТЕКУЩИЕ ДАННЫЕ:
{current_stats}

Составь план тренировок на неделю:

**📅 СТРУКТУРА НЕДЕЛИ** (3-4 предложения)
- Распределение нагрузки по дням
- Соотношение легких/средних/тяжелых тренировок
- Дни восстановления

**🏃 ТИПЫ ТРЕНИРОВОК** (2-3 предложения)
- Конкретные виды тренировок (темповые, интервалы, база)
- Пульсовые зоны и продолжительность

**⚡ ИНТЕНСИВНОСТЬ** (1-2 предложения) 
- Рекомендуемый TSS на неделю
- Как учесть текущее состояние HRV

**🔄 АДАПТАЦИЯ** (1-2 предложения)
- Как корректировать план в зависимости от самочувствия"""

        return prompt

    @staticmethod
    def _get_training_stats(activities_df: pd.DataFrame, hrv_df: pd.DataFrame, days: int) -> str:
        """Подготовка статистики тренировок"""
        stats = []
        
        if not activities_df.empty:
            total_workouts = len(activities_df)
            total_distance = activities_df['distance_km'].sum()
            total_time = activities_df['duration_minutes'].sum()
            avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns else 0
            
            stats.append(f"Тренировок: {total_workouts}")
            stats.append(f"Дистанция: {total_distance:.1f} км")  
            stats.append(f"Время: {total_time/60:.1f} часов")
            stats.append(f"Средний TSS: {avg_tss:.0f}")
            
            # Типы тренировок
            sports = activities_df['sport'].value_counts().to_dict()
            sports_str = ", ".join([f"{k}: {v}" for k, v in sports.items()])
            stats.append(f"Виды спорта: {sports_str}")
        
        if not hrv_df.empty:
            current_rmssd = hrv_df['rmssd'].iloc[0] if pd.notna(hrv_df['rmssd'].iloc[0]) else None
            avg_rmssd = hrv_df['rmssd'].mean()
            
            if current_rmssd:
                stats.append(f"Текущий RMSSD: {current_rmssd:.1f} мс")
            if pd.notna(avg_rmssd):
                stats.append(f"Средний RMSSD: {avg_rmssd:.1f} мс")
            
            # Стресс и восстановление
            latest_stress = hrv_df['stress_score'].iloc[0] if 'stress_score' in hrv_df.columns and pd.notna(hrv_df['stress_score'].iloc[0]) else None
            latest_recovery = hrv_df['recovery_score'].iloc[0] if 'recovery_score' in hrv_df.columns and pd.notna(hrv_df['recovery_score'].iloc[0]) else None
            
            if latest_stress:
                stats.append(f"Уровень стресса: {latest_stress:.0f}")
            if latest_recovery:
                stats.append(f"Восстановление: {latest_recovery:.0f}%")
        
        return "\n".join([f"• {stat}" for stat in stats]) if stats else "Данные недоступны"

    @staticmethod 
    def _get_hrv_stats(hrv_df: pd.DataFrame, days: int) -> str:
        """Статистика HRV данных"""
        if hrv_df.empty:
            return "HRV данные отсутствуют"
        
        valid_data = hrv_df[hrv_df['rmssd'].notna()]
        if valid_data.empty:
            return "Валидные RMSSD данные отсутствуют"
        
        stats = []
        
        # Основные метрики
        current = valid_data['rmssd'].iloc[0]
        avg = valid_data['rmssd'].mean()
        min_val = valid_data['rmssd'].min()
        max_val = valid_data['rmssd'].max()
        
        stats.append(f"Текущий RMSSD: {current:.1f} мс")
        stats.append(f"Средний RMSSD: {avg:.1f} мс (диапазон: {min_val:.1f}-{max_val:.1f})")
        
        # Тренд
        if len(valid_data) >= 3:
            import numpy as np
            x = np.arange(len(valid_data))
            y = valid_data['rmssd'].to_numpy()
            trend = np.polyfit(x, y, 1)[0]  # Линейный тренд
            
            if abs(trend) > 0.1:
                direction = "растет" if trend > 0 else "снижается"
                stats.append(f"Тренд: {direction} ({trend:+.2f} мс/день)")
            else:
                stats.append("Тренд: стабильный")
        
        # Вариабельность
        cv = (valid_data['rmssd'].std() / avg) * 100 if avg > 0 else 0
        stats.append(f"Вариабельность: {cv:.1f}%")
        
        return "\n".join([f"• {stat}" for stat in stats])

    @staticmethod
    def _format_activity(activity: Dict) -> str:
        """Форматирование данных активности"""
        formatted = []
        
        sport = activity.get('sport', 'Неизвестно')
        distance = activity.get('distance_km', 0)
        duration = activity.get('duration_minutes', 0)
        tss = activity.get('tss', 0)
        
        formatted.append(f"Вид спорта: {sport}")
        formatted.append(f"Дистанция: {distance:.1f} км")
        formatted.append(f"Время: {duration:.0f} мин ({duration/60:.1f} ч)")
        formatted.append(f"TSS: {tss:.0f}")
        
        # Дополнительные метрики если есть
        if activity.get('avg_hr'):
            formatted.append(f"Средний пульс: {activity['avg_hr']:.0f} уд/мин")
        if activity.get('avg_power'):
            formatted.append(f"Средняя мощность: {activity['avg_power']:.0f} Вт")
        
        return "\n".join([f"• {item}" for item in formatted])


# Примеры использования специализированных prompts
def get_analysis_prompt(analysis_type: str, **kwargs) -> tuple:
    """Получить специализированный prompt для анализа"""
    
    system_prompt = TrainingPrompts.get_system_prompt()
    
    if analysis_type == "recent_training":
        user_prompt = TrainingPrompts.analyze_recent_training(
            kwargs.get('activities_df', pd.DataFrame()),
            kwargs.get('hrv_df', pd.DataFrame()),
            kwargs.get('days', 7)
        )
    elif analysis_type == "workout":
        user_prompt = TrainingPrompts.analyze_workout(kwargs.get('activity', {}))
    elif analysis_type == "hrv":
        user_prompt = TrainingPrompts.hrv_analysis(
            kwargs.get('hrv_df', pd.DataFrame()),
            kwargs.get('period_days', 14)
        )
    elif analysis_type == "weekly_plan":
        user_prompt = TrainingPrompts.weekly_planning(
            kwargs.get('activities_df', pd.DataFrame()),
            kwargs.get('hrv_df', pd.DataFrame()),
            kwargs.get('goals', "Улучшение выносливости")
        )
    else:
        user_prompt = "Проанализируй тренировочные данные и дай рекомендации."
    
    return system_prompt, user_prompt