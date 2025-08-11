"""
Универсальный AI коуч с поддержкой разных провайдеров
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json

from models.ai_providers import AIProvider, AIProviderFactory


class UniversalAICoach:
    """Универсальный AI коуч для анализа тренировок"""
    
    def __init__(self, provider: AIProvider = None):
        """
        Инициализация коуча
        
        Args:
            provider: AI провайдер (если None, будет выбран первый доступный)
        """
        self.provider = provider or AIProviderFactory.get_first_available()
        
        # Базовый системный промпт для всех провайдеров
        self.system_prompt = """
        Ты опытный тренер по выносливости и спортивный физиолог с глубокими знаниями в области тренировочной науки.
        
        Твои специализации:
        - Анализ тренировочных данных (TSS, CTL, ATL, TSB)
        - Планирование тренировочных циклов
        - Интерпретация показателей HRV и восстановления
        - Профилактика перетренированности
        - Оптимизация спортивной формы
        
        Стиль общения:
        - Дружелюбный и мотивирующий
        - Используй простой язык для объяснения сложных концепций
        - Давай конкретные, практичные советы
        - Всегда учитывай безопасность и здоровье спортсмена
        
        Отвечай на русском языке, используй эмодзи для наглядности.
        """
    
    def set_provider(self, provider: AIProvider):
        """Установить AI провайдера"""
        self.provider = provider
    
    def analyze_current_state(self, metrics: Dict) -> str:
        """
        Анализ текущего состояния спортсмена
        
        Args:
            metrics: Словарь с метриками (CTL, ATL, TSB, и т.д.)
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        prompt = f"""
        Проанализируй текущее состояние спортсмена на основе следующих данных:
        
        📊 Метрики тренировочной нагрузки:
        - CTL (Хроническая нагрузка): {metrics.get('ctl', 0):.1f}
        - ATL (Острая нагрузка): {metrics.get('atl', 0):.1f}
        - TSB (Баланс формы): {metrics.get('tsb', 0):.1f}
        
        📈 Последние тренировки:
        - Количество за неделю: {metrics.get('week_activities', 0)}
        - Общий недельный TSS: {metrics.get('week_tss', 0):.1f}
        - Средний TSS за тренировку: {metrics.get('avg_tss', 0):.1f}
        
        🏃 Основной вид спорта: {metrics.get('primary_sport', 'смешанный')}
        
        Дай оценку текущего состояния спортсмена:
        1. Интерпретируй показатели простым языком
        2. Оцени риск перетренированности
        3. Определи готовность к интенсивным нагрузкам
        4. Дай краткие рекомендации (2-3 предложения)
        
        Ответ должен быть структурированным и понятным.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def generate_weekly_plan(self, metrics: Dict, goals: str = "") -> str:
        """
        Генерация недельного плана тренировок
        
        Args:
            metrics: Текущие метрики
            goals: Цели спортсмена
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        prompt = f"""
        Создай недельный план тренировок на основе данных:
        
        📊 Текущие показатели:
        - CTL: {metrics.get('ctl', 0):.1f}
        - ATL: {metrics.get('atl', 0):.1f}
        - TSB: {metrics.get('tsb', 0):.1f}
        - Текущая форма: {metrics.get('form', 'неизвестно')}
        
        🎯 Цели: {goals if goals else 'поддержание формы'}
        
        📋 Требования к плану:
        1. Распредели нагрузку на 7 дней
        2. Укажи тип тренировки для каждого дня
        3. Предложи примерный TSS для каждой тренировки
        4. Включи дни отдыха/восстановления
        5. Учти принцип прогрессии и восстановления
        
        Формат ответа:
        День 1 (Понедельник): [Тип тренировки] - TSS: [значение]
        Описание: [краткое описание]
        
        В конце добавь общие рекомендации по выполнению плана.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def analyze_workout(self, workout_data: Dict, subjective_feel: str = "") -> str:
        """
        Анализ конкретной тренировки
        
        Args:
            workout_data: Данные тренировки
            subjective_feel: Субъективные ощущения
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        prompt = f"""
        Проанализируй выполненную тренировку:
        
        🏃 Данные тренировки:
        - Вид спорта: {workout_data.get('sport', 'неизвестно')}
        - Продолжительность: {workout_data.get('duration_minutes', 0):.0f} минут
        - Дистанция: {workout_data.get('distance_km', 0):.1f} км
        - TSS: {workout_data.get('tss', 0):.1f}
        - Средний пульс: {workout_data.get('avg_hr', 'н/д')} уд/мин
        - Максимальный пульс: {workout_data.get('max_hr', 'н/д')} уд/мин
        - Средняя мощность: {workout_data.get('avg_power', 'н/д')} Вт
        - Набор высоты: {workout_data.get('elevation_gain', 0):.0f} м
        
        💭 Субъективные ощущения: {subjective_feel if subjective_feel else 'не указаны'}
        
        Дай анализ тренировки:
        1. Оцени интенсивность и объём
        2. Определи тренировочный эффект
        3. Отметь сильные стороны выполнения
        4. Предложи, что можно улучшить
        5. Дай рекомендации по восстановлению
        
        Будь конкретным и практичным.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def predict_performance(self, metrics: Dict, race_date: str, race_type: str) -> str:
        """
        Прогноз готовности к соревнованию
        
        Args:
            metrics: Текущие метрики
            race_date: Дата соревнования
            race_type: Тип соревнования
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        # Вычисляем дни до старта
        try:
            race_dt = datetime.strptime(race_date, "%Y-%m-%d")
            days_to_race = (race_dt - datetime.now()).days
        except:
            days_to_race = "неизвестно"
        
        prompt = f"""
        Оцени готовность к предстоящему соревнованию:
        
        🏁 Соревнование:
        - Тип: {race_type}
        - Дата: {race_date}
        - Дней до старта: {days_to_race}
        
        📊 Текущие показатели:
        - CTL: {metrics.get('ctl', 0):.1f}
        - ATL: {metrics.get('atl', 0):.1f}
        - TSB: {metrics.get('tsb', 0):.1f}
        - Прогноз TSB на дату старта: {metrics.get('race_tsb', 'н/д')}
        
        📈 Тренд последних недель:
        - Средний недельный TSS: {metrics.get('avg_weekly_tss', 0):.1f}
        - Тренд CTL: {metrics.get('ctl_trend', 'стабильный')}
        
        Проанализируй:
        1. Текущий уровень готовности (в %)
        2. Оптимальна ли текущая форма для пика к соревнованию
        3. Что нужно скорректировать в подготовке
        4. Стратегия подводки (taper) к старту
        5. Целевой TSB для дня соревнования
        
        Дай конкретные рекомендации по оставшемуся периоду подготовки.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def explain_metrics(self, metric_name: str) -> str:
        """
        Объяснение метрик простым языком
        
        Args:
            metric_name: Название метрики для объяснения
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        prompt = f"""
        Объясни метрику "{metric_name}" простым языком:
        
        1. Что это такое (в 2-3 предложениях)
        2. Как она рассчитывается (упрощённо)
        3. Какие значения считаются нормальными
        4. Как использовать для планирования тренировок
        5. Приведи практический пример
        
        Используй аналогии из повседневной жизни для лучшего понимания.
        Избегай сложных технических терминов.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def recovery_recommendations(self, metrics: Dict, hrv_data: Dict = None) -> str:
        """
        Рекомендации по восстановлению
        
        Args:
            metrics: Метрики тренировочной нагрузки
            hrv_data: Данные HRV (если есть)
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        prompt = f"""
        Дай рекомендации по восстановлению на основе данных:
        
        📊 Тренировочная нагрузка:
        - TSB: {metrics.get('tsb', 0):.1f}
        - ATL (острая усталость): {metrics.get('atl', 0):.1f}
        - Последний TSS: {metrics.get('last_tss', 0):.1f}
        
        💓 HRV данные (если доступны):
        - RMSSD: {hrv_data.get('rmssd', 'н/д') if hrv_data else 'н/д'}
        - Тренд: {hrv_data.get('trend', 'н/д') if hrv_data else 'н/д'}
        
        Предложи:
        1. Оценку текущего уровня восстановления
        2. Конкретные методы восстановления на сегодня
        3. Рекомендации по питанию
        4. Советы по сну и отдыху
        5. Когда можно проводить следующую интенсивную тренировку
        
        Учитывай практичность и доступность рекомендаций.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)
    
    def answer_question(self, question: str, context: Dict = None) -> str:
        """
        Ответ на произвольный вопрос о тренировках
        
        Args:
            question: Вопрос пользователя
            context: Контекст (метрики, данные)
        """
        if not self.provider or not self.provider.is_available():
            return "❌ AI провайдер не доступен. Проверьте настройки."
        
        context_str = ""
        if context:
            context_str = f"""
            Контекст пользователя:
            - CTL: {context.get('ctl', 'н/д')}
            - ATL: {context.get('atl', 'н/д')}
            - TSB: {context.get('tsb', 'н/д')}
            - Основной спорт: {context.get('sport', 'н/д')}
            """
        
        prompt = f"""
        Вопрос от спортсмена: {question}
        
        {context_str}
        
        Дай полезный, практичный ответ. Если вопрос касается здоровья или медицинских аспектов,
        обязательно упомяни о необходимости консультации с врачом.
        """
        
        return self.provider.generate_response(prompt, self.system_prompt)