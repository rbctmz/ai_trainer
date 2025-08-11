import pandas as pd
import numpy as np
from datetime import datetime

class ActivityProcessor:
    
    @staticmethod
    def process_activities(activities_data):
        """Преобразование данных активностей в DataFrame"""
        if not activities_data:
            return pd.DataFrame()
        
        processed = []
        
        for activity in activities_data:
            try:
                # Безопасное извлечение данных с проверками
                activity_id = activity.get('activityId', str(datetime.now().timestamp()))
                
                # Парсинг даты
                start_time = activity.get('startTimeLocal', activity.get('startTimeGMT', ''))
                if start_time:
                    try:
                        if 'T' in start_time:
                            date = datetime.fromisoformat(start_time.replace('Z', '+00:00')).date()
                        else:
                            date = datetime.strptime(start_time[:10], '%Y-%m-%d').date()
                    except:
                        date = datetime.now().date()
                else:
                    date = datetime.now().date()
                
                # Извлечение типа активности
                activity_type = activity.get('activityType', {})
                if isinstance(activity_type, dict):
                    sport = activity_type.get('typeKey', 'unknown')
                else:
                    sport = str(activity_type) if activity_type else 'unknown'
                
                # Обработка числовых полей с безопасными значениями по умолчанию
                processed.append({
                    'activity_id': activity_id,
                    'date': date,
                    'sport': sport,
                    'duration_minutes': float(activity.get('duration', 0)) / 60 if activity.get('duration') else 0,
                    'distance_km': float(activity.get('distance', 0)) / 1000 if activity.get('distance') else 0,
                    'avg_hr': activity.get('averageHR') if activity.get('averageHR') else None,
                    'max_hr': activity.get('maxHR') if activity.get('maxHR') else None,
                    'avg_power': activity.get('avgPower') if activity.get('avgPower') else None,
                    'max_power': activity.get('maxPower') if activity.get('maxPower') else None,
                    'elevation_gain': float(activity.get('elevationGain', 0)) if activity.get('elevationGain') else 0,
                    'calories': int(activity.get('calories', 0)) if activity.get('calories') else 0,
                    'training_effect': float(activity.get('aerobicTrainingEffect', 0)) if activity.get('aerobicTrainingEffect') else None,
                    'anaerobic_effect': float(activity.get('anaerobicTrainingEffect', 0)) if activity.get('anaerobicTrainingEffect') else None,
                    'activity_name': activity.get('activityName', ''),
                    'description': activity.get('description', '')
                })
                
            except Exception as e:
                print(f"Ошибка обработки активности {activity.get('activityId', 'unknown')}: {e}")
                continue
        
        if not processed:
            return pd.DataFrame()
        
        df = pd.DataFrame(processed)
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    @staticmethod
    def calculate_tss(activity_data, ftp=None, lthr=None):
        """Расчёт Training Stress Score"""
        duration_minutes = activity_data.get('duration_minutes', 0)
        if duration_minutes <= 0:
            return 0
        
        # TSS на основе мощности (приоритет)
        if ftp and ftp > 0 and activity_data.get('avg_power') and activity_data.get('avg_power') > 0:
            duration_hours = duration_minutes / 60
            intensity_factor = activity_data['avg_power'] / ftp
            tss = duration_hours * intensity_factor ** 2 * 100
            return round(tss, 1)
        
        # hrTSS на основе пульса
        elif lthr and lthr > 0 and activity_data.get('avg_hr') and activity_data.get('avg_hr') > 0:
            duration_hours = duration_minutes / 60
            intensity_factor = activity_data['avg_hr'] / lthr
            hrTSS = duration_hours * intensity_factor ** 2 * 100
            return round(hrTSS, 1)
        
        # Приблизительный TSS на основе времени и типа активности
        else:
            duration_hours = duration_minutes / 60
            # Базовый коэффициент в зависимости от типа активности
            sport = activity_data.get('sport', 'unknown').lower()
            
            if any(word in sport for word in ['running', 'run', 'бег']):
                base_tss = 50  # TSS в час для бега средней интенсивности
            elif any(word in sport for word in ['cycling', 'bike', 'велосипед']):
                base_tss = 60  # TSS в час для велосипеда средней интенсивности
            elif any(word in sport for word in ['swimming', 'плавание']):
                base_tss = 55  # TSS в час для плавания средней интенсивности
            else:
                base_tss = 40  # Общий коэффициент для других активностей
            
            estimated_tss = duration_hours * base_tss
            return round(estimated_tss, 1)
    
    @staticmethod
    def get_sport_translation(sport_key):
        """Перевод типов активностей на русский язык"""
        translations = {
            'running': 'Бег',
            'cycling': 'Велосипед', 
            'swimming': 'Плавание',
            'walking': 'Ходьба',
            'hiking': 'Походы',
            'strength_training': 'Силовая',
            'yoga': 'Йога',
            'unknown': 'Неизвестно'
        }
        return translations.get(sport_key.lower(), sport_key.title())