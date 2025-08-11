from openai import OpenAI
import json
from datetime import datetime, timedelta
from config.settings import Settings

class AICoach:
    def __init__(self, api_key=None):
        self.api_key = api_key or Settings.OPENAI_API_KEY
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
            
        self.system_prompt = """
        Ты опытный тренер по выносливости с глубокими знаниями физиологии.
        Анализируй предоставленные данные тренировок и давай персонализированные рекомендации.
        Учитывай: TSS, CTL, ATL, TSB, HRV данные, тип активности.
        Отвечай кратко и практично на русском языке.
        """
    
    def analyze_training_data(self, training_summary):
        """Анализ тренировочных данных"""
        if not self.client:
            return "Ошибка: не настроен API ключ OpenAI"
        
        user_prompt = f"""
        Данные тренировок за последние 7 дней:
        - Общий TSS: {training_summary.get('weekly_tss', 0)}
        - CTL: {training_summary.get('ctl', 0)}
        - ATL: {training_summary.get('atl', 0)}
        - TSB: {training_summary.get('tsb', 0)}
        - HRV Score: {training_summary.get('hrv_score', 'нет данных')}
        - Количество тренировок: {training_summary.get('workout_count', 0)}
        - Основной вид спорта: {training_summary.get('primary_sport', 'неизвестно')}
        
        Дай рекомендации на следующую неделю.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Ошибка получения рекомендаций: {e}"