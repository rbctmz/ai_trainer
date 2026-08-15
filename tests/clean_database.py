#!/usr/bin/env python3
"""
Скрипт для очистки базы данных от тестовых данных
"""

import sys
import sqlite3

sys.path.append('.')
from config.settings import Settings

def analyze_database():
    """Анализирует содержимое базы данных перед очисткой"""
    conn = sqlite3.connect(Settings.DATABASE_PATH)
    cursor = conn.cursor()
    
    print("🔍 Анализ базы данных перед очисткой:")
    print("=" * 50)
    
    # Активности
    cursor.execute('SELECT COUNT(*) FROM activities')
    total_activities = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id LIKE "test_%"')
    test_activities = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id LIKE "date_test_%"')
    date_test_activities = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id LIKE "test_df_%"')
    df_test_activities = cursor.fetchone()[0]
    
    # Реальные данные (не начинаются с "test")
    cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id NOT LIKE "test%"')
    real_activities = cursor.fetchone()[0]
    
    print(f"📊 Всего активностей: {total_activities}")
    print(f"🧪 Тестовых активностей: {test_activities}")
    print(f"📅 Тестов дат: {date_test_activities}")
    print(f"📋 DataFrame тестов: {df_test_activities}")
    print(f"✅ Реальных активностей: {real_activities}")
    
    # HRV данные
    cursor.execute('SELECT COUNT(*) FROM hrv_data')
    total_hrv = cursor.fetchone()[0]
    print(f"💓 HRV записей: {total_hrv}")
    
    # Показываем реальные активности (если есть)
    if real_activities > 0:
        print("\n✅ Реальные активности (будут сохранены):")
        cursor.execute('''
            SELECT activity_id, date, sport, duration_minutes 
            FROM activities 
            WHERE activity_id NOT LIKE "test%" 
            ORDER BY date DESC LIMIT 5
        ''')
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} - {row[2]} ({row[3]} мин)")
    
    conn.close()
    return {
        'total_activities': total_activities,
        'test_activities': test_activities + date_test_activities + df_test_activities,
        'real_activities': real_activities,
        'total_hrv': total_hrv
    }

def clean_database(confirm=True):
    """Очищает тестовые данные из базы данных"""
    
    if confirm:
        response = input("\n⚠️  Вы уверены, что хотите очистить тестовые данные? (yes/no): ")
        if response.lower() not in ['yes', 'y', 'да']:
            print("🚫 Очистка отменена")
            return False
    
    conn = sqlite3.connect(Settings.DATABASE_PATH)
    cursor = conn.cursor()
    
    print("\n🧹 Начинаем очистку...")
    
    # Удаляем тестовые активности
    test_patterns = ['test_%', 'date_test_%', 'test_df_%']
    total_deleted = 0
    
    for pattern in test_patterns:
        cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id LIKE ?', (pattern,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            cursor.execute('DELETE FROM activities WHERE activity_id LIKE ?', (pattern,))
            print(f"🗑️  Удалено {count} активностей с паттерном '{pattern}'")
            total_deleted += count
    
    # Удаляем все HRV данные (так как они тестовые)
    cursor.execute('SELECT COUNT(*) FROM hrv_data')
    hrv_count = cursor.fetchone()[0]
    
    if hrv_count > 0:
        cursor.execute('DELETE FROM hrv_data')
        print(f"🗑️  Удалено {hrv_count} HRV записей")
    
    # Очищаем пользовательские настройки (если нужно)
    cursor.execute('SELECT COUNT(*) FROM user_settings')
    settings_count = cursor.fetchone()[0]
    
    if settings_count > 0:
        response = input(f"❓ Удалить {settings_count} пользовательских настроек? (yes/no): ")
        if response.lower() in ['yes', 'y', 'да']:
            cursor.execute('DELETE FROM user_settings')
            print(f"🗑️  Удалено {settings_count} пользовательских настроек")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Очистка завершена!")
    print(f"🗑️  Всего удалено: {total_deleted} активностей, {hrv_count} HRV записей")
    
    return True

def verify_cleanup():
    """Проверяет результаты очистки"""
    conn = sqlite3.connect(Settings.DATABASE_PATH)
    cursor = conn.cursor()
    
    print("\n🔍 Проверка после очистки:")
    print("=" * 30)
    
    cursor.execute('SELECT COUNT(*) FROM activities')
    activities_count = cursor.fetchone()[0]
    print(f"📊 Активностей осталось: {activities_count}")
    
    cursor.execute('SELECT COUNT(*) FROM activities WHERE activity_id LIKE "test%"')
    test_remaining = cursor.fetchone()[0]
    print(f"🧪 Тестовых активностей: {test_remaining}")
    
    cursor.execute('SELECT COUNT(*) FROM hrv_data')
    hrv_count = cursor.fetchone()[0]
    print(f"💓 HRV записей: {hrv_count}")
    
    if activities_count > 0:
        print("\n📋 Оставшиеся активности:")
        cursor.execute('SELECT activity_id, date, sport FROM activities ORDER BY date DESC LIMIT 3')
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} - {row[2]}")
    else:
        print("📝 База данных полностью очищена и готова для новых данных!")
    
    conn.close()

def main():
    """Главная функция"""
    print("🧹 Очистка базы данных AI Trainer")
    print("=" * 50)
    
    # Анализируем текущее состояние
    stats = analyze_database()
    
    if stats['test_activities'] == 0 and stats['total_hrv'] == 0:
        print("\n✨ База данных уже чистая!")
        return
    
    print("\n📋 План очистки:")
    print(f"  🗑️  Удалить {stats['test_activities']} тестовых активностей")
    print(f"  🗑️  Удалить {stats['total_hrv']} HRV записей")
    print(f"  ✅ Оставить {stats['real_activities']} реальных активностей")
    
    # Выполняем очистку
    if clean_database():
        verify_cleanup()
        print("\n🎉 База данных готова для загрузки реальных данных из Garmin!")
        print("\n📱 Теперь можете:")
        print("  1. Запустить: streamlit run app.py")
        print("  2. Подключиться к Garmin Connect")
        print("  3. Синхронизировать реальные данные")

if __name__ == "__main__":
    main()