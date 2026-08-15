#!/usr/bin/env python3
"""
Тест новых методов синхронизации для Фазы 1
"""

import sys
import os
sys.path.append('..')

try:
    from data.database import Database
except ImportError:
    sys.path.append('.')
    from data.database import Database

from datetime import datetime, timedelta

def test_sleep_data_sync():
    """Тестирование синхронизации данных сна"""
    print("🧪 Тестирование синхронизации данных сна...")
    
    # Создаем тестовую БД
    db = Database("test_sleep_sync.db")
    
    # Тестовые данные сна (используем текущие даты)
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    test_sleep_data = {
        today: {
            'total_sleep_minutes': 480,
            'deep_sleep_minutes': 120,
            'light_sleep_minutes': 300,
            'rem_sleep_minutes': 60,
            'awakenings_count': 3,
            'sleep_score': 85.5,
            'bedtime': '23:30',
            'wakeup_time': '07:30',
            'sleep_efficiency': 92.3
        },
        yesterday: {
            'total_sleep_minutes': 420,
            'deep_sleep_minutes': 90,
            'light_sleep_minutes': 270,
            'rem_sleep_minutes': 60,
            'awakenings_count': 2,
            'sleep_score': 78.2,
            'bedtime': '23:45',
            'wakeup_time': '06:45',
            'sleep_efficiency': 88.7
        }
    }
    
    # Первая синхронизация
    result1 = db.sync_sleep_data(test_sleep_data)
    print(f"   Первая синхронизация: {result1}")
    assert result1['new'] == 2, "Должно быть добавлено 2 записи"
    assert result1['updated'] == 0, "Обновлений быть не должно"
    
    # Повторная синхронизация (обновление)
    test_sleep_data[today]['sleep_score'] = 87.0  # Изменяем оценку
    result2 = db.sync_sleep_data(test_sleep_data)
    print(f"   Повторная синхронизация: {result2}")
    assert result2['new'] == 0, "Новых записей быть не должно"
    assert result2['updated'] == 2, "Должно быть обновлено 2 записи"
    
    # Проверяем получение данных
    sleep_df = db.get_sleep_data(30)
    print(f"   Получено данных сна: {len(sleep_df)} записей")
    assert len(sleep_df) == 2, "Должно быть 2 записи"
    
    # Очистка
    if os.path.exists("test_sleep_sync.db"):
        os.remove("test_sleep_sync.db")
    
    print("   ✅ Синхронизация данных сна работает корректно")

def test_daily_health_sync():
    """Тестирование синхронизации ежедневных показателей здоровья"""
    print("\n🧪 Тестирование синхронизации ежедневных показателей...")
    
    # Удаляем старую БД если существует
    if os.path.exists("test_health_sync.db"):
        os.remove("test_health_sync.db")
    
    # Создаем тестовую БД
    db = Database("test_health_sync.db")
    
    # Тестовые данные здоровья (используем текущие даты)
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    test_health_data = {
        today: {
            'resting_hr': 52,
            'steps': 8500,
            'floors_climbed': 12,
            'calories_active': 520,
            'calories_bmr': 1650,
            'distance_meters': 6800,
            'active_minutes': 45,
            'intensity_minutes': 22
        },
        yesterday: {
            'resting_hr': 54,
            'steps': 12300,
            'floors_climbed': 18,
            'calories_active': 680,
            'calories_bmr': 1650,
            'distance_meters': 9200,
            'active_minutes': 62,
            'intensity_minutes': 35
        }
    }
    
    # Первая синхронизация
    result1 = db.sync_daily_health(test_health_data)
    print(f"   Первая синхронизация: {result1}")
    assert result1['new'] == 2, "Должно быть добавлено 2 записи"
    
    # Повторная синхронизация
    test_health_data[today]['resting_hr'] = 53  # Изменяем пульс покоя
    result2 = db.sync_daily_health(test_health_data)
    print(f"   Повторная синхронизация: {result2}")
    assert result2['updated'] == 2, "Должно быть обновлено 2 записи"
    
    # Проверяем получение данных
    health_df = db.get_daily_health(30)
    print(f"   Получено данных здоровья: {len(health_df)} записей")
    assert len(health_df) == 2, "Должно быть 2 записи"
    
    # Проверяем конкретные значения
    if not health_df.empty:
        # Находим запись с сегодняшней датой
        today_entry = health_df[health_df['date'].dt.strftime('%Y-%m-%d') == today]
        if not today_entry.empty:
            resting_hr = today_entry.iloc[0]['resting_hr']
            assert resting_hr == 53, f"Пульс покоя должен быть 53 (после обновления), но получен {resting_hr}"
            print(f"   Обновлённый пульс покоя: {resting_hr} уд/мин")
    
    # Очистка
    if os.path.exists("test_health_sync.db"):
        os.remove("test_health_sync.db")
    
    print("   ✅ Синхронизация показателей здоровья работает корректно")

def test_training_status_sync():
    """Тестирование синхронизации статуса тренированности"""
    print("\n🧪 Тестирование синхронизации статуса тренированности...")
    
    # Удаляем старую БД если существует
    if os.path.exists("test_training_sync.db"):
        os.remove("test_training_sync.db")
    
    # Создаем тестовую БД
    db = Database("test_training_sync.db")
    
    # Тестовые данные статуса тренированности (используем текущую дату)
    today = datetime.now().strftime('%Y-%m-%d')
    
    test_status_data = {
        today: {
            'vo2_max': 52.5,
            'fitness_age': 28,
            'training_load_7d': 320.5,
            'training_status': 'Productive',
            'training_readiness': 75.8,
            'recovery_time_hours': 18,
            'load_ratio': 1.2
        }
    }
    
    # Первая синхронизация
    result1 = db.sync_training_status(test_status_data)
    print(f"   Первая синхронизация: {result1}")
    assert result1['new'] == 1, "Должна быть добавлена 1 запись"
    
    # Обновление статуса
    test_status_data[today]['vo2_max'] = 53.0
    test_status_data[today]['training_readiness'] = 78.2
    result2 = db.sync_training_status(test_status_data)
    print(f"   Обновление статуса: {result2}")
    assert result2['updated'] == 1, "Должна быть обновлена 1 запись"
    
    # Проверяем получение данных
    status_df = db.get_training_status_history(90)
    print(f"   Получено записей статуса: {len(status_df)} записей")
    assert len(status_df) == 1, "Должна быть 1 запись"
    
    if not status_df.empty:
        latest_status = status_df.iloc[0]
        assert latest_status['vo2_max'] == 53.0, "VO2 max должен быть обновлён"
        print(f"   VO2 max: {latest_status['vo2_max']}")
        print(f"   Статус тренированности: {latest_status['training_status']}")
    
    # Очистка
    if os.path.exists("test_training_sync.db"):
        os.remove("test_training_sync.db")
    
    print("   ✅ Синхронизация статуса тренированности работает корректно")

def test_comprehensive_sync():
    """Комплексное тестирование всех методов синхронизации"""
    print("\n🧪 Комплексное тестирование синхронизации...")
    
    # Удаляем старую БД если существует
    if os.path.exists("test_comprehensive_sync.db"):
        os.remove("test_comprehensive_sync.db")
    
    # Создаем тестовую БД
    db = Database("test_comprehensive_sync.db")
    
    # Проверяем статистику до синхронизации
    stats_before = db.get_database_stats()
    print(f"   Статистика до синхронизации: {stats_before}")
    
    # Добавляем данные во все новые таблицы (используем текущую дату)
    today = datetime.now().strftime('%Y-%m-%d')
    
    sleep_data = {today: {'total_sleep_minutes': 450, 'sleep_score': 80}}
    health_data = {today: {'resting_hr': 55, 'steps': 10000}}
    status_data = {today: {'vo2_max': 50.0, 'training_status': 'Maintaining'}}
    
    # Синхронизируем все типы данных
    sleep_result = db.sync_sleep_data(sleep_data)
    health_result = db.sync_daily_health(health_data)
    status_result = db.sync_training_status(status_data)
    
    print("   Результаты синхронизации:")
    print(f"     Сон: {sleep_result}")
    print(f"     Здоровье: {health_result}")
    print(f"     Статус: {status_result}")
    
    # Проверяем статистику после синхронизации
    stats_after = db.get_database_stats()
    print(f"   Статистика после синхронизации: {stats_after}")
    
    assert stats_after['sleep_data'] == 1, "Должна быть 1 запись сна"
    assert stats_after['daily_health'] == 1, "Должна быть 1 запись здоровья"
    assert stats_after['training_status'] == 1, "Должна быть 1 запись статуса"
    
    # Тестируем очистку
    db.clear_all_data()
    stats_cleared = db.get_database_stats()
    print(f"   Статистика после очистки: {stats_cleared}")
    
    for table, count in stats_cleared.items():
        assert count == 0, f"Таблица {table} должна быть пустой"
    
    # Очистка
    if os.path.exists("test_comprehensive_sync.db"):
        os.remove("test_comprehensive_sync.db")
    
    print("   ✅ Комплексная синхронизация работает корректно")

def main():
    """Основная функция тестирования"""
    print("🚀 Тестирование новых методов синхронизации Фазы 1\n")
    
    try:
        test_sleep_data_sync()
        test_daily_health_sync()
        test_training_status_sync()
        test_comprehensive_sync()
        
        print("\n🎉 Все тесты синхронизации прошли успешно!")
        print("\n📋 Проверенные методы:")
        print("   ✅ sync_sleep_data() - синхронизация данных сна")
        print("   ✅ sync_daily_health() - синхронизация показателей здоровья")
        print("   ✅ sync_training_status() - синхронизация статуса тренированности")
        print("   ✅ get_sleep_data() - получение данных сна")
        print("   ✅ get_daily_health() - получение показателей здоровья")
        print("   ✅ get_training_status_history() - история статуса")
        print("\n🔧 Функции работают с:")
        print("   ✅ Умной синхронизацией (без дублей)")
        print("   ✅ Обновлением существующих записей")
        print("   ✅ Корректной обработкой дат")
        print("   ✅ Интеграцией с общей системой очистки БД")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тестах: {e}")
        raise

if __name__ == "__main__":
    main()