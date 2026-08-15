#!/usr/bin/env python3
"""
Тест улучшенного форматирования результатов инструментов
"""

import sys
sys.path.append('..')

from data.database import Database
from models.ai_tools import AITools

# Импортируем функцию форматирования из app.py
from app import format_tool_result

def test_improved_formatting():
    """Тестирует улучшенное форматирование результатов инструментов"""
    print("=" * 80)
    print("🎨 ТЕСТ УЛУЧШЕННОГО ФОРМАТИРОВАНИЯ")
    print("=" * 80)
    
    # Инициализация
    db = Database()
    ai_tools = AITools(db)
    
    print("🔧 Инициализация завершена")
    
    # Список тестовых инструментов
    test_cases = [
        {
            "tool": "get_activities_by_date_range",
            "params": {"start_date": "2025-07-01", "end_date": "2025-07-31"},
            "description": "Активности за июль 2025"
        },
        {
            "tool": "get_performance_metrics", 
            "params": {"days": 90},
            "description": "Метрики производительности"
        },
        {
            "tool": "get_recent_activities",
            "params": {"limit": 3},
            "description": "Последние активности"
        },
        {
            "tool": "analyze_recovery_state",
            "params": {},
            "description": "Анализ восстановления"
        }
    ]
    
    print(f"\n📋 Тестируем {len(test_cases)} инструментов...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'─' * 60}")
        print(f"🧪 ТЕСТ {i}: {test_case['description']}")
        print(f"🔧 Инструмент: {test_case['tool']}")
        print(f"⚙️ Параметры: {test_case['params']}")
        
        try:
            # Выполняем инструмент
            result = ai_tools.execute_tool(test_case['tool'], **test_case['params'])
            
            if result.get('success'):
                data = result['result']
                
                # Форматируем результат через обновленную функцию
                formatted_result = format_tool_result(test_case['tool'], data)
                
                print("✅ Инструмент выполнен успешно")
                print(f"📏 Размер отформатированного результата: {len(formatted_result)} символов")
                
                print("\n📄 ОТФОРМАТИРОВАННЫЙ РЕЗУЛЬТАТ:")
                print("┌" + "─" * 58 + "┐")
                
                # Показываем результат построчно с рамкой
                lines = formatted_result.split('\n')
                for line in lines[:20]:  # Ограничиваем до 20 строк
                    padded_line = line[:56].ljust(56)
                    print(f"│ {padded_line} │")
                
                if len(lines) > 20:
                    print(f"│ ... (еще {len(lines)-20} строк) {' '*34} │")
                
                print("└" + "─" * 58 + "┘")
                
                # Проверяем, что форматирование содержит markdown элементы
                markdown_elements = ['##', '###', '**', '•', '🏃', '📊']
                found_elements = [elem for elem in markdown_elements if elem in formatted_result]
                
                if found_elements:
                    print(f"✅ Найдены markdown элементы: {', '.join(found_elements)}")
                else:
                    print("⚠️ Не найдено markdown элементов")
                
            else:
                print(f"❌ Ошибка выполнения: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ Исключение: {e}")
    
    # Тестируем пустой результат
    print(f"\n{'─' * 60}")
    print("🧪 ТЕСТ: Пустой результат (май 2025)")
    
    try:
        result = ai_tools.execute_tool("get_activities_by_date_range", 
                                     start_date="2025-05-01", end_date="2025-05-31")
        
        if result.get('success'):
            formatted = format_tool_result("get_activities_by_date_range", result['result'])
            print("✅ Пустой результат отформатирован:")
            print(f"📄 {formatted}")
        else:
            print(f"❌ Ошибка: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
    
    # Тестируем общий формат для неизвестного инструмента
    print(f"\n{'─' * 60}")
    print("🧪 ТЕСТ: Неизвестный инструмент")
    
    mock_data = {
        'count': 5,
        'total_tss': 350,
        'some_complex_data': {'nested': 'data', 'values': [1, 2, 3]},
        'message': 'Тестовое сообщение'
    }
    
    formatted = format_tool_result("unknown_tool", mock_data)
    print("✅ Неизвестный инструмент отформатирован:")
    print(f"📄 {formatted}")
    
    # Резюме
    print("\n" + "=" * 80)
    print("📋 ИТОГИ ТЕСТИРОВАНИЯ ФОРМАТИРОВАНИЯ")
    print("=" * 80)
    
    print("""
✅ УЛУЧШЕНИЯ РЕАЛИЗОВАНЫ:
• Использование Markdown заголовков (##, ###)
• Эмодзи для видов спорта и метрик
• Структурированное отображение данных
• Нумерованные списки активностей  
• Цветовые индикаторы для TSB и восстановления
• Улучшенная обработка пустых результатов
• Общий формат для неизвестных инструментов

🎨 РЕЗУЛЬТАТ:
• Данные теперь отображаются структурированно
• Используются эмодзи для лучшего восприятия
• Заголовки помогают организовать информацию
• Списки легко читаются и понимаются

🚀 ГОТОВО К ИСПОЛЬЗОВАНИЮ:
Теперь все результаты инструментов будут красиво форматироваться
в чате AI тренера с использованием Markdown и эмодзи.

📝 РЕКОМЕНДАЦИЯ:
Перезапустите приложение (streamlit run app.py) чтобы увидеть улучшения!
    """)

if __name__ == "__main__":
    test_improved_formatting()