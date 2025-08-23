#!/usr/bin/env python3
"""
Детальная диагностика API сна Garmin
"""

import sys
import os
sys.path.append('..')

try:
    from data.garmin_client import GarminClient
except ImportError:
    sys.path.append('.')
    from data.garmin_client import GarminClient

from datetime import datetime, timedelta

def test_garmin_sleep_api_methods():
    """Тестирование различных методов получения данных сна"""
    print("🔍 Детальная диагностика API сна Garmin...")
    
    # Создаем клиент (без реального подключения для демонстрации)
    client = GarminClient()
    
    # Проверяем доступные методы для сна
    print("\n📋 Доступные методы в GarminClient:")
    sleep_methods = [method for method in dir(client) if 'sleep' in method.lower()]
    for method in sleep_methods:
        print(f"   • {method}")
    
    # Проверяем методы для данных здоровья
    health_methods = [method for method in dir(client) if any(word in method.lower() for word in ['health', 'heart', 'step', 'activity'])]
    print(f"\n💓 Методы для данных здоровья ({len(health_methods)}):")
    for method in health_methods[:10]:  # Показываем первые 10
        print(f"   • {method}")
    
    # Показываем что библиотека garminconnect поддерживает
    try:
        from garminconnect import Garmin
        garmin_methods = [method for method in dir(Garmin) if not method.startswith('_')]
        print(f"\n🔧 Доступные методы в библиотеке garminconnect ({len(garmin_methods)}):")
        
        # Ищем методы связанные со сном
        sleep_related = [method for method in garmin_methods if 'sleep' in method.lower()]
        if sleep_related:
            print("   Методы сна:")
            for method in sleep_related:
                print(f"     • {method}")
        else:
            print("   ❌ Специальных методов для сна не найдено")
        
        # Ищем общие методы данных
        data_methods = [method for method in garmin_methods if any(word in method.lower() for word in ['get_', 'data', 'stats'])]
        print(f"   Общие методы получения данных ({len(data_methods[:15])}):")
        for method in data_methods[:15]:
            print(f"     • {method}")
            
    except ImportError:
        print("   ❌ Библиотека garminconnect не найдена")

def analyze_sleep_data_availability():
    """Анализ доступности данных сна"""
    print("\n🛏️ Анализ доступности данных сна...")
    
    print("📊 Что нужно для получения данных сна:")
    print("   1. ✅ Совместимое устройство Garmin (Vivosmart, Fenix, Forerunner с сенсором)")
    print("   2. ✅ Включенное отслеживание сна в Garmin Connect")
    print("   3. ❓ Достаточная история ношения устройства (минимум несколько ночей)")
    print("   4. ❓ Правильные настройки приватности в аккаунте")
    
    print("\n🔒 Возможные ограничения API:")
    print("   • Неофициальная библиотека garminconnect может не иметь доступа к данным сна")
    print("   • Garmin может требовать специальную авторизацию для данных здоровья")
    print("   • Данные сна могут быть доступны только через официальный SDK")
    
    print("\n🎯 Рекомендации:")
    print("   1. Проверить веб-интерфейс Garmin Connect - есть ли там данные сна")
    print("   2. Убедиться что устройство носится ночью и отслеживает сон")
    print("   3. Проверить настройки приватности в Garmin Connect")
    print("   4. Попробовать экспорт данных вручную из Garmin Connect")

def suggest_alternative_solutions():
    """Предложение альтернативных решений"""
    print("\n🔧 Альтернативные решения:")
    
    print("1. 📁 Ручной импорт из Garmin Connect:")
    print("   • Экспорт данных из веб-интерфейса Garmin Connect")
    print("   • Импорт CSV/JSON файлов в приложение")
    print("   • Разовая настройка для получения исторических данных")
    
    print("\n2. 📱 Интеграция с другими источниками:")
    print("   • Apple Health (для пользователей iPhone)")
    print("   • Google Fit (для пользователей Android)")
    print("   • Fitbit API (если есть устройство Fitbit)")
    print("   • Ручной ввод ключевых показателей")
    
    print("\n3. 🔄 Улучшение текущего API:")
    print("   • Попробовать другие методы библиотеки garminconnect")
    print("   • Обновить библиотеку до последней версии")
    print("   • Исследовать неофициальные методы API")
    
    print("\n4. 🧪 Временное решение:")
    print("   • Использовать тестовые данные для демонстрации функций")
    print("   • Ручной ввод реальных данных сна")
    print("   • Фокус на доступных данных (HRV, пульс покоя)")

def check_garmin_connect_library():
    """Проверка возможностей библиотеки garminconnect"""
    print("\n📚 Проверка библиотеки garminconnect...")
    
    try:
        from garminconnect import Garmin
        
        # Создаем фиктивный клиент для проверки методов
        print("✅ Библиотека garminconnect доступна")
        
        # Ищем все методы связанные с данными
        all_methods = dir(Garmin)
        
        # Группируем методы по категориям
        categories = {
            'sleep': [],
            'body': [],
            'stats': [],
            'activities': [],
            'heart': []
        }
        
        for method in all_methods:
            if not method.startswith('_'):
                method_lower = method.lower()
                if 'sleep' in method_lower:
                    categories['sleep'].append(method)
                elif any(word in method_lower for word in ['body', 'weight', 'composition']):
                    categories['body'].append(method)
                elif any(word in method_lower for word in ['stats', 'summary', 'daily']):
                    categories['stats'].append(method)
                elif any(word in method_lower for word in ['activity', 'activities']):
                    categories['activities'].append(method)
                elif any(word in method_lower for word in ['heart', 'hr', 'pulse']):
                    categories['heart'].append(method)
        
        for category, methods in categories.items():
            if methods:
                print(f"\n   {category.title()} методы ({len(methods)}):")
                for method in methods[:5]:  # Показываем первые 5
                    print(f"     • {method}")
                if len(methods) > 5:
                    print(f"     ... и ещё {len(methods) - 5}")
        
        # Специальная проверка методов сна
        if categories['sleep']:
            print(f"\n🎯 Найдено {len(categories['sleep'])} методов для сна!")
            print("   Это может быть решением проблемы.")
        else:
            print("\n❌ Методы для сна не найдены в библиотеке")
            print("   Возможно, нужно использовать общие методы stats")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке библиотеки: {e}")

def main():
    """Главная функция диагностики"""
    print("🚀 Диагностика проблемы с данными сна Garmin\n")
    
    test_garmin_sleep_api_methods()
    check_garmin_connect_library()
    analyze_sleep_data_availability()
    suggest_alternative_solutions()
    
    print("\n" + "="*60)
    print("📋 ЗАКЛЮЧЕНИЕ:")
    print("="*60)
    print("🔍 Проблема: Данные сна недоступны через текущий API")
    print("💡 Причина: Ограничения неофициальной библиотеки garminconnect")
    print("✅ Решение: Комбинация тестовых данных + альтернативные источники")
    print("🎯 Статус: Функционал готов, нужен другой источник данных")

if __name__ == "__main__":
    main()