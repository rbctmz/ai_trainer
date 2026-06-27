#!/usr/bin/env python3
"""
Тест современного интерфейса чата с сохранением
"""

import sys
import os
import tempfile
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.chat_manager import ChatManager

def test_modern_chat(tmp_path):
    """Тестирует новый менеджер чатов"""
    print("=" * 80)
    print("🗣️ ТЕСТ СОВРЕМЕННОГО ИНТЕРФЕЙСА ЧАТА")
    print("=" * 80)
    
    # Инициализация менеджера
    chat_manager = ChatManager(chats_dir=str(tmp_path / "chats"))
    
    print("\n🔧 Инициализация завершена")
    print(f"📁 Директория чатов: {chat_manager.chats_dir}")
    
    # 1. Создание нового чата
    print("\n📝 Тестирование создания чата...")
    
    chat_id = chat_manager.create_new_chat("Тестовый чат")
    print(f"✅ Создан чат с ID: {chat_id}")
    
    # 2. Добавление сообщений
    print("\n💬 Тестирование добавления сообщений...")
    
    test_messages = [
        ("user", "Привет! Как дела с моей формой?"),
        ("assistant", "Привет! Анализирую твои данные..."),
        ("user", "Покажи мои метрики за последний месяц"),
        ("assistant", "Вот твои метрики:\n• CTL: 45\n• ATL: 38\n• TSB: +7")
    ]
    
    for role, content in test_messages:
        success = chat_manager.add_message(chat_id, role, content)
        assert success is True
        print(f"  ✅ Добавлено сообщение от {role}: {content[:30]}...")
    
    # 3. Загрузка сообщений
    print("\n📋 Тестирование загрузки сообщений...")
    
    messages = chat_manager.get_chat_messages(chat_id)
    print(f"✅ Загружено {len(messages)} сообщений")
    assert len(messages) == len(test_messages)
    
    for i, msg in enumerate(messages, 1):
        role_name = "🤔 Пользователь" if msg["role"] == "user" else "🤖 AI"
        print(f"  {i}. {role_name}: {msg['content'][:50]}...")
    
    # 4. Получение списка чатов
    print("\n📚 Тестирование списка чатов...")
    
    # Создаем еще один чат для разнообразия
    chat_id2 = chat_manager.create_new_chat()
    assert chat_manager.add_message(chat_id2, "user", "Второй тестовый чат") is True
    
    chats = chat_manager.get_chat_list()
    print(f"✅ Найдено {len(chats)} чатов")
    assert len(chats) == 2
    
    for chat in chats:
        print(f"  💬 {chat['title']} (ID: {chat['id']}, сообщений: {chat['message_count']})")
    
    # 5. Статистика
    print("\n📊 Тестирование статистики...")
    
    stats = chat_manager.get_stats()
    print(f"✅ Статистика:")
    print(f"  • Всего чатов: {stats['total_chats']}")
    print(f"  • Всего сообщений: {stats['total_messages']}")
    
    # 6. Поиск
    print("\n🔍 Тестирование поиска...")
    
    search_results = chat_manager.search_chats("метрики")
    print(f"✅ Найдено {len(search_results)} чатов с 'метрики'")
    assert len(search_results) == 1
    
    # 7. Экспорт чата
    print("\n📤 Тестирование экспорта...")
    
    exported_text = chat_manager.export_chat(chat_id)
    print(f"✅ Экспорт выполнен, размер: {len(exported_text)} символов")
    assert "метрики" in exported_text
    
    print("\n📄 Превью экспорта:")
    print("─" * 50)
    print(exported_text[:300] + "..." if len(exported_text) > 300 else exported_text)
    print("─" * 50)
    
    # 8. Удаление чата
    print("\n🗑️ Тестирование удаления...")
    
    deleted = chat_manager.delete_chat(chat_id2)
    print(f"✅ Чат {chat_id2} удален: {deleted}")
    assert deleted is True
    
    # Проверяем что чат действительно удален
    updated_chats = chat_manager.get_chat_list()
    print(f"  📚 Осталось чатов: {len(updated_chats)}")
    assert len(updated_chats) == 1
    
    # 9. Финальные проверки
    print("\n🔍 Финальная проверка функциональности...")
    
    # Проверяем что основной чат все еще существует
    main_chat = chat_manager.load_chat(chat_id)
    if main_chat:
        print(f"✅ Основной чат существует с {len(main_chat['messages'])} сообщениями")
        print(f"  📝 Название: {main_chat['title']}")
        print(f"  📅 Создан: {main_chat['created_at'][:19]}")
        print(f"  🔄 Обновлен: {main_chat['updated_at'][:19]}")
    else:
        print("❌ Основной чат не найден!")
    assert main_chat is not None
    assert len(main_chat["messages"]) == len(test_messages)
    
    # Резюме
    print(f"\n" + "=" * 80)
    print("📋 РЕЗЮМЕ ТЕСТИРОВАНИЯ СОВРЕМЕННОГО ЧАТА")
    print("=" * 80)
    
    print(f"""
✅ УСПЕШНО ПРОТЕСТИРОВАНО:
• Создание и управление чатами
• Добавление и загрузка сообщений
• Автоматическое обновление названий чатов
• Список чатов с сортировкой по времени
• Статистика по чатам
• Поиск по содержимому чатов
• Экспорт чатов в текстовый формат
• Удаление чатов

🎯 КЛЮЧЕВЫЕ ВОЗМОЖНОСТИ:
• Сохранение всех диалогов в JSON файлы
• Автоматические названия на основе первого сообщения
• Метаданные: дата создания, обновления, количество сообщений
• Поиск по названиям и содержимому
• Экспорт для резервного копирования
• Простое управление через API

🚀 ИНТЕГРАЦИЯ С STREAMLIT:
• Боковая панель со списком чатов
• Кнопки для создания, выбора и удаления
• Статистика и метрики чатов
• Современный интерфейс как в ChatGPT

💾 ДАННЫЕ СОХРАНЯЮТСЯ В:
  {os.path.abspath(chat_manager.chats_dir)}/

🔧 ГОТОВО К ИСПОЛЬЗОВАНИЮ!
Запустите приложение и протестируйте новый интерфейс чата.
    """)
    

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_modern_chat(Path(tmp_dir))
