#!/usr/bin/env python3
"""
Тест для выяснения структуры реальных данных сна от garth
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.garmin_client import GarminClient

def debug_real_sleep_data():
    """Получаем реальные данные сна и анализируем их структуру"""
    print("🔍 Отладка реальных данных сна...")
    
    # Инициализируем клиент
    client = GarminClient()
    
    # Примерные данные аутентификации (НЕ ВЫПОЛНЯЕМ реальную аутентификацию)
    # client.authenticate("email", "password")
    
    # Симулируем, что получили реальные данные из логов
    # Берем пример данных, которые мы видели в логах
    print("📥 Анализируем структуру данных из логов...")
    
    # Выводим, что нужно смотреть в логах
    print("""
🔍 Нужно проверить:
1. Формат данных, который возвращает garth
2. Структура поля 'dailySleepDTO'
3. Какие еще поля есть в response
4. Почему процессор падает с ошибками

📋 Команды для анализа:
grep -A 20 "✅ Данные сна получены через connectapi" logs/garmin_sync_20250816.log | head -40
grep "Ошибка обработки данных сна" logs/garmin_sync_20250816.log
""")
    
    # Попробуем понять ошибки
    print("❌ Обнаруженные ошибки:")
    print("1. 'float' object has no attribute 'lower' - обработка sleepLevels")
    print("2. unsupported operand type(s) for //: 'NoneType' and 'int' - деление None на число")
    
    print("\n📊 Возможные причины:")
    print("- sleepLevels содержит числа вместо строк")  
    print("- Некоторые поля содержат None вместо чисел")
    print("- Структура данных отличается от ожидаемой")

if __name__ == "__main__":
    debug_real_sleep_data()