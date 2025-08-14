"""
Модуль для создания контекста данных пользователя для AI чата
Собирает все доступные данные из БД для полноценного анализа
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from data.database import Database
from models.banister import BanisterModel
from models.hrv_analyzer import HRVAnalyzer
from utils.metrics import MetricsCalculator


class AIDataContext:
    """Класс для создания полного контекста данных пользователя для AI"""
    
    def __init__(self, database: Database):
        self.db = database
        self.banister = BanisterModel()
        self.hrv_analyzer = HRVAnalyzer()
        self.metrics = MetricsCalculator()
    
    def get_full_context(self, days: int = 90) -> Dict[str, Any]:
        """
        Получает полный контекст данных пользователя за N дней
        Включает активности, HRV, метрики, тренды
        """
        context = {
            'period_days': days,
            'data_timestamp': datetime.now().isoformat(),
            'summary': {},
            'activities': {},
            'hrv': {},
            'performance_metrics': {},
            'trends': {},
            'user_profile': {}
        }
        
        # 1. Основная сводка
        context['summary'] = self._get_summary_stats(days)
        
        # 2. Данные активностей
        context['activities'] = self._get_activities_context(days)
        
        # 3. HRV данные
        context['hrv'] = self._get_hrv_context(days)
        
        # 4. Метрики производительности
        context['performance_metrics'] = self._get_performance_metrics(days)
        
        # 5. Тренды и динамика
        context['trends'] = self._get_trends_analysis(days)
        
        # 6. Профиль пользователя
        context['user_profile'] = self._get_user_profile()
        
        return context
    
    def _get_summary_stats(self, days: int) -> Dict[str, Any]:
        """Общая сводка за период"""
        activities_df = self.db.get_activities(days)
        hrv_df = self.db.get_hrv_data(days)
        
        if activities_df.empty:
            return {'has_data': False, 'message': 'Нет данных активностей'}
        
        summary = {
            'has_data': True,
            'period_start': activities_df['date'].min().strftime('%Y-%m-%d'),
            'period_end': activities_df['date'].max().strftime('%Y-%m-%d'),
            'total_activities': len(activities_df),
            'total_days_with_activities': activities_df['date'].nunique(),
            'activity_frequency_per_week': (len(activities_df) / days) * 7,
            'total_duration_hours': activities_df['duration_minutes'].sum() / 60,
            'total_distance_km': activities_df['distance_km'].sum() if 'distance_km' in activities_df.columns else 0,
            'total_elevation_m': activities_df['elevation_gain'].sum() if 'elevation_gain' in activities_df.columns else 0,
            'total_tss': activities_df['tss'].sum() if 'tss' in activities_df.columns else 0,
            'avg_tss_per_session': activities_df['tss'].mean() if 'tss' in activities_df.columns else 0,
            'sports_distribution': activities_df['sport'].value_counts().to_dict() if 'sport' in activities_df.columns else {},
            'hrv_data_points': len(hrv_df),
            'hrv_coverage_percent': (len(hrv_df) / days) * 100 if not hrv_df.empty else 0
        }
        
        return summary
    
    def _get_activities_context(self, days: int) -> Dict[str, Any]:
        """Детальный контекст активностей"""
        activities_df = self.db.get_activities(days)
        
        if activities_df.empty:
            return {'has_data': False}
        
        # Группировка по неделям
        activities_df['date'] = pd.to_datetime(activities_df['date'])
        activities_df['week'] = activities_df['date'].dt.isocalendar().week
        
        weekly_stats = activities_df.groupby('week').agg({
            'tss': ['sum', 'mean', 'count'],
            'duration_minutes': 'sum',
            'distance_km': 'sum'
        }).round(1)
        
        # Последние 10 активностей
        recent_activities = activities_df.head(10)[
            ['date', 'sport', 'duration_minutes', 'distance_km', 'tss', 'avg_hr']
        ].to_dict('records')
        
        # Анализ по видам спорта
        sport_analysis = {}
        for sport in activities_df['sport'].unique():
            sport_data = activities_df[activities_df['sport'] == sport]
            sport_analysis[sport] = {
                'count': len(sport_data),
                'avg_duration': sport_data['duration_minutes'].mean(),
                'avg_tss': sport_data['tss'].mean() if 'tss' in sport_data.columns else 0,
                'total_distance': sport_data['distance_km'].sum() if 'distance_km' in sport_data.columns else 0,
                'avg_hr': sport_data['avg_hr'].mean() if 'avg_hr' in sport_data.columns else 0
            }
        
        return {
            'has_data': True,
            'recent_activities': recent_activities,
            'weekly_summary': weekly_stats.to_dict(),
            'sport_analysis': sport_analysis,
            'intensity_distribution': self._analyze_intensity_distribution(activities_df),
            'training_patterns': self._analyze_training_patterns(activities_df)
        }
    
    def _get_hrv_context(self, days: int) -> Dict[str, Any]:
        """Контекст HRV данных"""
        hrv_df = self.db.get_hrv_data(days)
        
        if hrv_df.empty:
            return {'has_data': False, 'message': 'Нет HRV данных'}
        
        # Статистика HRV
        hrv_stats = {
            'current_rmssd': hrv_df.iloc[0]['rmssd'] if not hrv_df.empty else None,
            'avg_rmssd': hrv_df['rmssd'].mean(),
            'baseline_rmssd': hrv_df['rmssd'].quantile(0.5),  # медиана как базовая линия
            'rmssd_std': hrv_df['rmssd'].std(),
            'trend_7days': self._calculate_hrv_trend(hrv_df, 7),
            'trend_14days': self._calculate_hrv_trend(hrv_df, 14),
            'recovery_state': self._assess_recovery_state(hrv_df)
        }
        
        # Корреляция с тренировками
        correlation_analysis = self._analyze_hrv_training_correlation(hrv_df, days)
        
        return {
            'has_data': True,
            'data_points': len(hrv_df),
            'stats': hrv_stats,
            'correlation_with_training': correlation_analysis,
            'recent_values': hrv_df.head(7)[['date', 'rmssd', 'stress_score', 'recovery_score']].to_dict('records')
        }
    
    def _get_performance_metrics(self, days: int) -> Dict[str, Any]:
        """Метрики производительности и модель Банистера"""
        activities_df = self.db.get_activities(days)
        
        if activities_df.empty:
            return {'has_data': False}
        
        # Подготавливаем данные для модели Банистера
        tss_data = []
        dates = []
        
        for idx, row in activities_df.iterrows():
            tss_val = row.get('tss', 0)
            if pd.isna(tss_val):
                tss_val = 0
            tss_data.append(float(tss_val))
            dates.append(row['date'])
        
        # Получаем метрики Банистера
        banister_metrics = self.banister.get_current_metrics(tss_data, dates)
        
        # Дополнительные метрики
        additional_metrics = {
            'avg_weekly_tss': np.mean([sum(tss_data[i:i+7]) for i in range(0, len(tss_data), 7)]) if len(tss_data) >= 7 else 0,
            'peak_tss_session': max(tss_data) if tss_data else 0,
            'consistency_score': self._calculate_consistency_score(tss_data),
            'training_load_trend': self._calculate_load_trend(tss_data),
            'form_prediction': self._predict_form(banister_metrics)
        }
        
        return {
            'has_data': True,
            'banister_model': banister_metrics,
            'additional_metrics': additional_metrics,
            'tss_history': tss_data[-30:],  # Последние 30 значений
            'recommendations': self._generate_load_recommendations(banister_metrics)
        }
    
    def _get_trends_analysis(self, days: int) -> Dict[str, Any]:
        """Анализ трендов и динамики"""
        activities_df = self.db.get_activities(days)
        hrv_df = self.db.get_hrv_data(days)
        
        trends = {}
        
        if not activities_df.empty:
            # Тренд по объему тренировок
            weekly_volume = activities_df.groupby(
                activities_df['date'].dt.isocalendar().week
            )['duration_minutes'].sum()
            
            # Тренд по интенсивности
            weekly_tss = activities_df.groupby(
                activities_df['date'].dt.isocalendar().week
            )['tss'].sum()
            
            trends['training_volume'] = {
                'direction': 'increasing' if weekly_volume.iloc[-1] > weekly_volume.iloc[0] else 'decreasing',
                'change_percent': ((weekly_volume.iloc[-1] - weekly_volume.iloc[0]) / weekly_volume.iloc[0] * 100) if weekly_volume.iloc[0] > 0 else 0,
                'weekly_values': weekly_volume.tolist()
            }
            
            trends['training_intensity'] = {
                'direction': 'increasing' if weekly_tss.iloc[-1] > weekly_tss.iloc[0] else 'decreasing',
                'change_percent': ((weekly_tss.iloc[-1] - weekly_tss.iloc[0]) / weekly_tss.iloc[0] * 100) if weekly_tss.iloc[0] > 0 else 0,
                'weekly_values': weekly_tss.tolist()
            }
        
        if not hrv_df.empty:
            # Тренд HRV
            hrv_trend = np.polyfit(range(len(hrv_df)), hrv_df['rmssd'], 1)
            trends['hrv'] = {
                'direction': 'improving' if hrv_trend[0] > 0 else 'declining',
                'slope': hrv_trend[0],
                'recent_avg': hrv_df.head(7)['rmssd'].mean(),
                'period_avg': hrv_df['rmssd'].mean()
            }
        
        return trends
    
    def _get_user_profile(self) -> Dict[str, Any]:
        """Профиль пользователя на основе данных"""
        activities_df = self.db.get_activities(90)
        
        if activities_df.empty:
            return {'has_data': False}
        
        # Определяем профиль на основе данных
        primary_sport = activities_df['sport'].mode()[0] if not activities_df['sport'].empty else 'mixed'
        avg_session_duration = activities_df['duration_minutes'].mean()
        sessions_per_week = len(activities_df) / 13  # примерно 90 дней = 13 недель
        
        # Классификация уровня тренированности
        if sessions_per_week >= 6 and avg_session_duration >= 60:
            training_level = 'advanced'
        elif sessions_per_week >= 4 and avg_session_duration >= 45:
            training_level = 'intermediate'
        else:
            training_level = 'beginner'
        
        return {
            'has_data': True,
            'primary_sport': primary_sport,
            'training_level': training_level,
            'avg_session_duration': avg_session_duration,
            'sessions_per_week': sessions_per_week,
            'preferred_training_days': activities_df['date'].dt.day_name().mode().tolist(),
            'training_consistency': len(activities_df) / 90  # процент дней с тренировками
        }
    
    def _analyze_intensity_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ распределения интенсивности тренировок"""
        if 'tss' not in df.columns or df['tss'].isna().all():
            return {'has_data': False}
        
        tss_values = df['tss'].dropna()
        
        return {
            'low_intensity': len(tss_values[tss_values < 50]) / len(tss_values) * 100,
            'moderate_intensity': len(tss_values[(tss_values >= 50) & (tss_values < 100)]) / len(tss_values) * 100,
            'high_intensity': len(tss_values[tss_values >= 100]) / len(tss_values) * 100,
            'avg_tss': tss_values.mean(),
            'peak_tss': tss_values.max()
        }
    
    def _analyze_training_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Анализ паттернов тренировок"""
        df['day_of_week'] = df['date'].dt.day_name()
        df['hour'] = df['date'].dt.hour
        
        return {
            'favorite_days': df['day_of_week'].value_counts().head(3).to_dict(),
            'typical_duration': df['duration_minutes'].quantile([0.25, 0.5, 0.75]).to_dict(),
            'rest_day_pattern': 7 - df['day_of_week'].nunique(),  # сколько дней в неделю отдых
        }
    
    def _calculate_hrv_trend(self, hrv_df: pd.DataFrame, days: int) -> float:
        """Рассчитывает тренд HRV за последние N дней"""
        if len(hrv_df) < days:
            return 0
        
        recent_data = hrv_df.head(days)
        if len(recent_data) < 2:
            return 0
        
        trend = np.polyfit(range(len(recent_data)), recent_data['rmssd'], 1)
        return trend[0]
    
    def _assess_recovery_state(self, hrv_df: pd.DataFrame) -> str:
        """Оценивает состояние восстановления на основе HRV"""
        if len(hrv_df) < 7:
            return 'insufficient_data'
        
        current_avg = hrv_df.head(3)['rmssd'].mean()
        baseline = hrv_df['rmssd'].quantile(0.5)
        
        if current_avg > baseline * 1.1:
            return 'excellent'
        elif current_avg > baseline * 0.95:
            return 'good'
        elif current_avg > baseline * 0.85:
            return 'fair'
        else:
            return 'poor'
    
    def _analyze_hrv_training_correlation(self, hrv_df: pd.DataFrame, days: int) -> Dict[str, Any]:
        """Анализ корреляции HRV с тренировочной нагрузкой"""
        activities_df = self.db.get_activities(days)
        
        if activities_df.empty or hrv_df.empty:
            return {'has_data': False}
        
        # Объединяем данные по дате
        activities_df['date'] = pd.to_datetime(activities_df['date'])
        daily_tss = activities_df.groupby('date')['tss'].sum().reset_index()
        
        merged = pd.merge(hrv_df, daily_tss, on='date', how='left')
        merged['tss'] = merged['tss'].fillna(0)
        
        if len(merged) < 5:
            return {'has_data': False}
        
        # Корреляции
        corr_same_day = merged[['rmssd', 'tss']].corr().iloc[0, 1]
        
        # Корреляция с лагом (HRV следующего дня vs TSS предыдущего)
        merged_shifted = merged.copy()
        merged_shifted['tss_prev'] = merged_shifted['tss'].shift(1)
        corr_lag1 = merged_shifted[['rmssd', 'tss_prev']].corr().iloc[0, 1]
        
        return {
            'has_data': True,
            'same_day_correlation': corr_same_day,
            'lag_1_correlation': corr_lag1,
            'interpretation': self._interpret_hrv_correlation(corr_same_day, corr_lag1)
        }
    
    def _interpret_hrv_correlation(self, same_day: float, lag1: float) -> str:
        """Интерпретирует корреляцию HRV с нагрузкой"""
        if pd.isna(same_day) and pd.isna(lag1):
            return 'insufficient_data'
        
        # Выбираем наиболее значимую корреляцию
        if abs(lag1 or 0) > abs(same_day or 0):
            if lag1 < -0.4:
                return 'strong_negative_delayed'  # Сильная отрицательная корреляция с задержкой
            elif lag1 < -0.2:
                return 'moderate_negative_delayed'
            elif lag1 > 0.2:
                return 'positive_unusual'
            else:
                return 'weak_correlation'
        else:
            if same_day < -0.4:
                return 'strong_negative_immediate'
            elif same_day < -0.2:
                return 'moderate_negative_immediate'
            elif same_day > 0.2:
                return 'positive_unusual'
            else:
                return 'weak_correlation'
    
    def _calculate_consistency_score(self, tss_data: List[float]) -> float:
        """Рассчитывает оценку постоянства тренировок"""
        if len(tss_data) < 7:
            return 0
        
        # Коэффициент вариации (чем меньше, тем стабильнее)
        mean_tss = np.mean(tss_data)
        std_tss = np.std(tss_data)
        
        if mean_tss == 0:
            return 0
        
        cv = std_tss / mean_tss
        # Инвертируем и нормализуем к шкале 0-100
        consistency = max(0, 100 - cv * 100)
        return min(100, consistency)
    
    def _calculate_load_trend(self, tss_data: List[float]) -> str:
        """Определяет тренд тренировочной нагрузки"""
        if len(tss_data) < 14:
            return 'insufficient_data'
        
        # Сравниваем последние 7 дней с предыдущими 7
        recent = np.mean(tss_data[-7:])
        previous = np.mean(tss_data[-14:-7])
        
        change = (recent - previous) / previous * 100 if previous > 0 else 0
        
        if change > 20:
            return 'increasing_rapidly'
        elif change > 5:
            return 'increasing'
        elif change < -20:
            return 'decreasing_rapidly'
        elif change < -5:
            return 'decreasing'
        else:
            return 'stable'
    
    def _predict_form(self, banister_metrics: Dict[str, float]) -> str:
        """Предсказывает форму на основе метрик Банистера"""
        tsb = banister_metrics.get('tsb', 0)
        
        if tsb > 10:
            return 'peaked'
        elif tsb > 0:
            return 'good_form'
        elif tsb > -15:
            return 'maintaining'
        elif tsb > -30:
            return 'building_fitness'
        else:
            return 'overreaching'
    
    def _generate_load_recommendations(self, banister_metrics: Dict[str, float]) -> List[str]:
        """Генерирует рекомендации по нагрузке"""
        recommendations = []
        
        tsb = banister_metrics.get('tsb', 0)
        ctl = banister_metrics.get('ctl', 0)
        atl = banister_metrics.get('atl', 0)
        
        if tsb > 15:
            recommendations.append("Отличная форма! Подходящее время для соревнований или тестовых тренировок")
        elif tsb > 5:
            recommendations.append("Хорошая форма. Можно планировать интенсивные тренировки")
        elif tsb > -10:
            recommendations.append("Нормальное состояние для продолжения планомерных тренировок")
        elif tsb > -25:
            recommendations.append("Период накопления усталости. Хорошо для базового периода")
        else:
            recommendations.append("Высокая усталость. Рассмотрите восстановительную неделю")
        
        if atl > ctl * 1.5:
            recommendations.append("Острая нагрузка высока. Добавьте восстановительные дни")
        
        if ctl < 30:
            recommendations.append("Низкая хроническая нагрузка. Постепенно увеличивайте объем тренировок")
        
        return recommendations
    
    def format_context_for_ai(self, context: Dict[str, Any]) -> str:
        """Форматирует контекст в читаемый текст для AI"""
        if not context['summary']['has_data']:
            return "У пользователя нет данных активностей для анализа."
        
        formatted = f"""
КОНТЕКСТ ДАННЫХ ПОЛЬЗОВАТЕЛЯ (за {context['period_days']} дней):

=== ОБЩАЯ СВОДКА ===
• Период: {context['summary']['period_start']} — {context['summary']['period_end']}
• Всего тренировок: {context['summary']['total_activities']}
• Частота тренировок: {context['summary']['activity_frequency_per_week']:.1f} раз в неделю
• Общее время: {context['summary']['total_duration_hours']:.1f} часов
• Общий TSS: {context['summary']['total_tss']:.0f}
• Средний TSS за тренировку: {context['summary']['avg_tss_per_session']:.1f}
• Основные виды спорта: {', '.join([f"{k}({v})" for k, v in list(context['summary']['sports_distribution'].items())[:3]])}

=== ТЕКУЩИЕ МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ ===
"""
        
        if context['performance_metrics']['has_data']:
            pm = context['performance_metrics']['banister_model']
            am = context['performance_metrics']['additional_metrics']
            formatted += f"""• CTL (хроническая нагрузка): {pm['ctl']:.1f}
• ATL (острая нагрузка): {pm['atl']:.1f}
• TSB (баланс стресса): {pm['tsb']:.1f}
• Форма: {am['form_prediction']}
• Тренд нагрузки: {am['training_load_trend']}
• Постоянство тренировок: {am['consistency_score']:.0f}/100
"""
        
        if context['hrv']['has_data']:
            hrv = context['hrv']['stats']
            formatted += f"""
=== HRV И ВОССТАНОВЛЕНИЕ ===
• Текущий RMSSD: {hrv['current_rmssd']:.1f} мс
• Средний RMSSD: {hrv['avg_rmssd']:.1f} мс
• Базовый уровень: {hrv['baseline_rmssd']:.1f} мс
• Тренд за 7 дней: {hrv['trend_7days']:+.2f} мс/день
• Состояние восстановления: {hrv['recovery_state']}
"""
        
        if context['trends']:
            formatted += f"""
=== ТРЕНДЫ ===
"""
            if 'training_volume' in context['trends']:
                tv = context['trends']['training_volume']
                formatted += f"• Объем тренировок: {tv['direction']} ({tv['change_percent']:+.1f}%)\n"
            
            if 'hrv' in context['trends']:
                hrv_trend = context['trends']['hrv']
                formatted += f"• HRV: {hrv_trend['direction']} (недавнее среднее: {hrv_trend['recent_avg']:.1f})\n"
        
        if context['user_profile']['has_data']:
            up = context['user_profile']
            formatted += f"""
=== ПРОФИЛЬ СПОРТСМЕНА ===
• Основной спорт: {up['primary_sport']}
• Уровень тренированности: {up['training_level']}
• Средняя длительность тренировки: {up['avg_session_duration']:.0f} минут
• Тренировок в неделю: {up['sessions_per_week']:.1f}
• Постоянство тренировок: {up['training_consistency']*100:.0f}%
"""
        
        return formatted.strip()