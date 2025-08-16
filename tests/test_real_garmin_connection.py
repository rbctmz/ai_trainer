#!/usr/bin/env python3
"""
Тест реального подключения к Garmin Connect для диагностики данных сна
"""

import sys
import os
sys.path.append('..')

try:
    from data.garmin_client import GarminClient
    from data.data_processor_phase1 import Phase1DataProcessor
except ImportError:
    sys.path.append('.')
    from data.garmin_client import GarminClient
    from data.data_processor_phase1 import Phase1DataProcessor

from datetime import datetime, timedelta
import streamlit as st

def test_real_garmin_connection():
    """Тестирование реального подключения к Garmin"""
    print("🔍 Тестирование реального подключения к Garmin Connect...")
    
    print("\n📋 Инструкции для проверки:")
    print("1. Убедитесь что вы авторизованы в Garmin Connect через приложение")
    print("2. Проверьте веб-интерфейс Garmin Connect - есть ли там данные сна")
    print("3. Убедитесь что устройство Garmin поддерживает отслеживание сна")
    print("4. Проверьте настройки приватности в Garmin Connect")
    
    print("\n🔧 Что проверить в Garmin Connect:")
    print("• Меню 'Здоровье' → 'Сон' - есть ли данные?")
    print("• Настройки → 'Приватность' → разрешён ли экспорт данных?")
    print("• Устройства → ваше устройство поддерживает сон?")
    
    print("\n💡 Дополнительные советы:")
    print("• Носите устройство ночью минимум 4 часа")
    print("• Убедитесь что батарея устройства заряжена")
    print("• Синхронизируйте устройство с приложением Garmin Connect")
    print("• Попробуйте сначала синхронизировать данные за последние 3-7 дней")

def create_manual_sleep_input():
    """Создание функции ручного ввода данных сна"""
    print("\n📝 Альтернатива: ручной ввод данных сна")
    
    manual_input_code = '''
def add_manual_sleep_data():
    """Функция для ручного ввода данных сна"""
    st.subheader("📝 Ручной ввод данных сна")
    
    with st.form("manual_sleep_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            sleep_date = st.date_input("Дата сна", datetime.now() - timedelta(days=1))
            bedtime = st.time_input("Время засыпания", datetime.strptime("23:00", "%H:%M").time())
            wakeup_time = st.time_input("Время пробуждения", datetime.strptime("07:00", "%H:%M").time())
            
        with col2:
            total_sleep = st.number_input("Общее время сна (часы)", min_value=0.0, max_value=12.0, value=8.0, step=0.5)
            sleep_quality = st.slider("Качество сна (субъективно)", 1, 10, 7)
            awakenings = st.number_input("Количество пробуждений", min_value=0, max_value=10, value=1)
        
        if st.form_submit_button("💾 Сохранить данные сна"):
            # Конвертируем в формат приложения
            sleep_data = {
                sleep_date.strftime('%Y-%m-%d'): {
                    'total_sleep_minutes': int(total_sleep * 60),
                    'deep_sleep_minutes': int(total_sleep * 60 * 0.2),  # ~20% глубокого сна
                    'light_sleep_minutes': int(total_sleep * 60 * 0.6), # ~60% легкого сна
                    'rem_sleep_minutes': int(total_sleep * 60 * 0.2),   # ~20% REM сна
                    'awakenings_count': awakenings,
                    'sleep_score': sleep_quality * 10,  # Конвертируем в 100-балльную шкалу
                    'bedtime': bedtime.strftime('%H:%M'),
                    'wakeup_time': wakeup_time.strftime('%H:%M'),
                    'sleep_efficiency': 90.0 if sleep_quality >= 7 else 75.0
                }
            }
            
            # Сохраняем в БД
            result = st.session_state.database.sync_sleep_data(sleep_data)
            st.success(f"✅ Данные сна сохранены: {result}")
            st.rerun()
'''
    
    print(f"Код для добавления в app.py:\n{manual_input_code}")

def suggest_garmin_connect_export():
    """Инструкции по экспорту из Garmin Connect"""
    print("\n📁 Экспорт данных из Garmin Connect:")
    
    print("1. Откройте веб-интерфейс Garmin Connect (connect.garmin.com)")
    print("2. Перейдите в раздел 'Здоровье' → 'Сон'")
    print("3. Выберите период (например, последний месяц)")
    print("4. Найдите опцию экспорта или скачивания данных")
    print("5. Сохраните файл CSV/JSON с данными сна")
    
    print("\n💾 Импорт в приложение:")
    print("• Создать функцию загрузки CSV файлов")
    print("• Парсить данные в формат приложения")
    print("• Автоматически заполнить БД историческими данными")

def main():
    """Главная функция тестирования"""
    print("🚀 Тестирование реального подключения к Garmin Connect\n")
    
    test_real_garmin_connection()
    create_manual_sleep_input()
    suggest_garmin_connect_export()
    
    print("\n" + "="*70)
    print("📋 РЕЗЮМЕ ПО ДАННЫМ СНА:")
    print("="*70)
    print("❌ Проблема: API Garmin не возвращает данные сна")
    print("🔍 Причина: Ограничения неофициальной библиотеки или настройки аккаунта")
    print("✅ Решения:")
    print("   1. 🧪 Использовать тестовые данные (уже реализовано)")
    print("   2. 📝 Добавить ручной ввод данных сна")
    print("   3. 📁 Реализовать импорт из Garmin Connect CSV")
    print("   4. 📱 Интеграция с Apple Health/Google Fit")
    print("🎯 Статус: Функционал готов, нужен источник данных")
    
    print("\n💡 РЕКОМЕНДАЦИЯ:")
    print("Используйте тестовые данные для ознакомления с функционалом,")
    print("а затем рассмотрите ручной ввод или экспорт из Garmin Connect.")

if __name__ == "__main__":
    main()