#!/usr/bin/env python3
"""
Тест интегрального индекса готовности
"""

import sys
import os
sys.path.append('..')

try:
    from data.data_processor_phase1 import Phase1DataProcessor
except ImportError:
    sys.path.append('.')
    from data.data_processor_phase1 import Phase1DataProcessor

def test_comprehensive_readiness_calculation():
    """Тестирование расчета комплексного индекса готовности"""
    print("🧪 Тестирование расчета индекса готовности...")
    
    # Тестовые данные - идеальное состояние
    perfect_sleep_data = {
        'sleep_score': 90.0,
        'total_sleep_minutes': 480,
        'sleep_efficiency': 95.0
    }
    
    perfect_hrv_data = {
        'rmssd': 50.0,  # Хороший уровень RMSSD
        'stress_score': 20.0  # Низкий стресс
    }
    
    perfect_health_data = {
        'resting_hr': 45  # Низкий пульс покоя - хорошо
    }
    
    perfect_training_data = {
        'training_readiness': 85.0,
        'vo2_max': 55.0
    }
    
    # Расчет для идеального состояния
    result_perfect = Phase1DataProcessor.calculate_comprehensive_readiness(
        perfect_sleep_data, perfect_hrv_data, perfect_health_data, perfect_training_data
    )
    
    print(f"   Идеальное состояние: {result_perfect}")
    assert result_perfect is not None, "Должен вернуться результат"
    assert 'readiness_score' in result_perfect, "Должен быть рассчитан индекс готовности"
    assert result_perfect['readiness_score'] >= 75, "Идеальное состояние должно дать высокий индекс"
    assert 'factors_used' in result_perfect, "Должны быть указаны использованные факторы"
    assert len(result_perfect['factors_used']) >= 4, "Должны использоваться минимум 4 фактора"
    
    # Тестовые данные - плохое состояние
    poor_sleep_data = {
        'sleep_score': 40.0,
        'total_sleep_minutes': 300,  # Мало сна
        'sleep_efficiency': 70.0
    }
    
    poor_hrv_data = {
        'rmssd': 15.0,  # Низкий RMSSD
        'stress_score': 80.0  # Высокий стресс
    }
    
    poor_health_data = {
        'resting_hr': 75  # Высокий пульс покоя
    }
    
    poor_training_data = {
        'training_readiness': 30.0,
        'vo2_max': 40.0
    }
    
    # Расчет для плохого состояния
    result_poor = Phase1DataProcessor.calculate_comprehensive_readiness(
        poor_sleep_data, poor_hrv_data, poor_health_data, poor_training_data
    )
    
    print(f"   Плохое состояние: {result_poor}")
    assert result_poor is not None, "Должен вернуться результат"
    assert result_poor['readiness_score'] <= 50, "Плохое состояние должно дать низкий индекс"
    
    # Тест с частичными данными
    partial_data = Phase1DataProcessor.calculate_comprehensive_readiness(
        perfect_sleep_data, None, None, None
    )
    print(f"   Частичные данные (только сон): {partial_data}")
    assert partial_data is not None, "Должен работать с частичными данными"
    assert len(partial_data['factors_used']) == 1, "Должен использовать только 1 фактор"
    
    # Тест с пустыми данными
    empty_result = Phase1DataProcessor.calculate_comprehensive_readiness(
        None, None, None, None
    )
    assert empty_result is None, "Без данных должен вернуть None"
    
    print("   ✅ Расчет индекса готовности работает корректно")

def test_sleep_data_processing():
    """Тестирование обработки данных сна"""
    print("\n🧪 Тестирование обработки данных сна...")
    
    # Тестовые сырые данные сна (имитация Garmin API)
    garmin_sleep_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,  # 8 часов
            'sleepStartTimestampLocal': '2024-01-15T23:30:00.000Z',
            'sleepEndTimestampLocal': '2024-01-16T07:30:00.000Z'
        },
        'sleepLevels': [
            {'activityLevel': 'deep', 'durationInSeconds': 7200},    # 2 часа
            {'activityLevel': 'light', 'durationInSeconds': 18000},  # 5 часов  
            {'activityLevel': 'rem', 'durationInSeconds': 3600},     # 1 час
            {'activityLevel': 'awake', 'durationInSeconds': 300},    # 2 пробуждения
            {'activityLevel': 'awake', 'durationInSeconds': 300}
        ]
    }
    
    processed = Phase1DataProcessor.process_sleep_data(garmin_sleep_data)
    print(f"   Обработанные данные сна: {processed}")
    
    assert processed is not None, "Должны быть обработаны данные сна"
    assert processed['total_sleep_minutes'] == 480, "Должно быть 8 часов сна"
    assert processed['deep_sleep_minutes'] == 120, "Должно быть 2 часа глубокого сна"
    assert processed['light_sleep_minutes'] == 300, "Должно быть 5 часов легкого сна"
    assert processed['rem_sleep_minutes'] == 60, "Должен быть 1 час REM сна"
    assert processed['awakenings_count'] == 2, "Должно быть 2 пробуждения"
    assert 'sleep_score' in processed, "Должна быть рассчитана оценка сна"
    assert 'sleep_efficiency' in processed, "Должна быть рассчитана эффективность"
    assert processed['bedtime'] == '23:30', "Время засыпания должно быть корректным"
    assert processed['wakeup_time'] == '07:30', "Время пробуждения должно быть корректным"
    
    # Тест с пустыми данными
    empty_processed = Phase1DataProcessor.process_sleep_data(None)
    assert empty_processed is None, "Пустые данные должны вернуть None"
    
    print("   ✅ Обработка данных сна работает корректно")

def test_health_data_processing():
    """Тестирование обработки данных здоровья"""
    print("\n🧪 Тестирование обработки данных здоровья...")
    
    # Тестовые данные активности за день
    health_data = {
        'totalSteps': 12000,
        'totalDistanceMeters': 8500,
        'activeKilocalories': 450,
        'bmrKilocalories': 1600,
        'vigorousIntensityMinutes': 20,
        'moderateIntensityMinutes': 35,
        'floorsAscended': 15
    }
    
    # Данные пульса покоя
    resting_hr_data = {'restingHeartRate': 52}
    
    processed = Phase1DataProcessor.process_daily_health_data(health_data, resting_hr_data)
    print(f"   Обработанные данные здоровья: {processed}")
    
    assert processed is not None, "Должны быть обработаны данные здоровья"
    assert processed['steps'] == 12000, "Шаги должны быть корректными"
    assert processed['distance_meters'] == 8500, "Дистанция должна быть корректной"
    assert processed['calories_active'] == 450, "Активные калории должны быть корректными"
    assert processed['calories_bmr'] == 1600, "BMR калории должны быть корректными"
    assert processed['active_minutes'] == 55, "Активные минуты = интенсивные + умеренные"
    assert processed['intensity_minutes'] == 20, "Интенсивные минуты должны быть корректными"
    assert processed['floors_climbed'] == 15, "Этажи должны быть корректными"
    assert processed['resting_hr'] == 52, "Пульс покоя должен быть корректным"
    
    print("   ✅ Обработка данных здоровья работает корректно")

def test_training_status_processing():
    """Тестирование обработки статуса тренированности"""
    print("\n🧪 Тестирование обработки статуса тренированности...")
    
    # Данные статуса тренированности
    status_data = {
        'trainingStatusKey': 'PRODUCTIVE',
        'load7Day': 350.5,
        'loadRatio': 1.2,
        'recoveryTimeHours': 18
    }
    
    # VO2 max данные
    vo2_data = {
        'vo2MaxValue': 52.5,
        'fitnessAge': 28
    }
    
    # Готовность к тренировке
    readiness_data = {'readinessScore': 75.8}
    
    processed = Phase1DataProcessor.process_training_status_data(
        status_data, vo2_data, readiness_data
    )
    print(f"   Обработанные данные статуса: {processed}")
    
    assert processed is not None, "Должны быть обработаны данные статуса"
    assert processed['training_status'] == 'PRODUCTIVE', "Статус тренированности должен быть корректным"
    assert processed['training_load_7d'] == 350.5, "7-дневная нагрузка должна быть корректной"
    assert processed['load_ratio'] == 1.2, "Соотношение нагрузки должно быть корректным"
    assert processed['recovery_time_hours'] == 18, "Время восстановления должно быть корректным"
    assert processed['vo2_max'] == 52.5, "VO2 max должен быть корректным"
    assert processed['fitness_age'] == 28, "Фитнес-возраст должен быть корректным"
    assert processed['training_readiness'] == 75.8, "Готовность должна быть корректной"
    
    print("   ✅ Обработка статуса тренированности работает корректно")

def main():
    """Основная функция тестирования"""
    print("🚀 Тестирование обработки данных и индекса готовности Фазы 1\n")
    
    try:
        test_sleep_data_processing()
        test_health_data_processing()
        test_training_status_processing()
        test_comprehensive_readiness_calculation()
        
        print("\n🎉 Все тесты обработки данных прошли успешно!")
        print("\n📋 Проверенные компоненты:")
        print("   ✅ Phase1DataProcessor.process_sleep_data()")
        print("   ✅ Phase1DataProcessor.process_daily_health_data()")
        print("   ✅ Phase1DataProcessor.process_training_status_data()")
        print("   ✅ Phase1DataProcessor.calculate_comprehensive_readiness()")
        print("\n🔧 Функции работают с:")
        print("   ✅ Обработкой сырых данных Garmin API")
        print("   ✅ Расчетом оценок качества сна")
        print("   ✅ Нормализацией показателей здоровья")
        print("   ✅ Комплексным индексом готовности")
        print("   ✅ Обработкой частичных и пустых данных")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тестах: {e}")
        raise

if __name__ == "__main__":
    main()