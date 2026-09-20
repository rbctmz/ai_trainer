#!/usr/bin/env python3
"""
Скрипт для очистки базы данных от тестовых данных

#625 destructive boundary: this CLI deletes rows (including ALL ``hrv_data``), so
it is an operator flow, not a temporary-artifact tool. It resolves the canonical
dogfood path through ``config.db_paths``, refuses every other target, and repeats
the exact target path plus deletion counts before opening a connection. Inside a
test/acceptance session the shared connection hook
(``data.database.guard_connect_path``) also fails closed, so this script cannot
be pointed at dogfood data by accident.
"""

import argparse
import sqlite3
import sys

sys.path.append('.')
from config.db_paths import (
    DatabasePathViolation,
    assert_operator_action_target,
    classify,
    normalize_path,
    production_database_path,
)

#: Rows this script is allowed to remove: only synthetic test fixtures.
TEST_ACTIVITY_PATTERNS = ('test_%', 'date_test_%', 'test_df_%')


def resolve_target_database(database: str | None = None) -> str:
    """Return the canonical dogfood path, refusing every other target.

    ``--database`` may only repeat the configured production path: this script is
    not a general maintenance tool for arbitrary databases.
    """
    production = production_database_path()

    if database is not None and normalize_path(database) != production:
        raise DatabasePathViolation(
            'clean-database-target',
            kind=classify(database).kind,
            detail=(
                'this operation only acts on the configured production database; '
                'point DATABASE_PATH at the intended file instead'
            ),
        )

    return str(
        assert_operator_action_target(
            production,
            purpose='clean_database deletion',
            invariant='clean-database-target',
        )
    )


def _require_operator_confirmation(database: str, counts: dict[str, int]) -> None:
    """Repeat the resolved target and the exact damage before any write."""
    print("\n⚠️  Destructive maintenance on the production database")
    print(f"🎯 Target: {database}")
    print(f"🗑️  Test activities to delete: {counts['test_activities']}")
    print(f"🗑️  HRV rows to delete: {counts['total_hrv']}")
    print("ℹ️  Take a validated snapshot first:")
    print("   python scripts/sqlite_backup_restore.py backup --output <path> --confirm-stopped")
    response = input("Type DELETE to confirm: ")
    if response.strip() != "DELETE":
        raise SystemExit("🚫 Очистка отменена: подтверждение не получено")


def analyze_database(database_path: str):
    """Анализирует содержимое базы данных перед очисткой"""
    conn = sqlite3.connect(database_path)
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


def clean_database(database_path: str, confirm: bool = True):
    """Очищает тестовые данные из базы данных"""

    if confirm:
        response = input("\n⚠️  Вы уверены, что хотите очистить тестовые данные? (yes/no): ")
        if response.lower() not in ['yes', 'y', 'да']:
            print("🚫 Очистка отменена")
            return False

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    print("\n🧹 Начинаем очистку...")

    # Удаляем тестовые активности
    total_deleted = 0

    for pattern in TEST_ACTIVITY_PATTERNS:
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


def verify_cleanup(database_path: str):
    """Проверяет результаты очистки"""
    conn = sqlite3.connect(database_path)
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


def main(argv: list[str] | None = None) -> int:
    """Главная функция"""
    parser = argparse.ArgumentParser(description="Очистка тестовых данных AI Trainer")
    parser.add_argument(
        "--database",
        default=None,
        help="Повторите путь из DATABASE_PATH (защита от очистки чужой базы)",
    )
    args = parser.parse_args(argv)

    print("🧹 Очистка базы данных AI Trainer")
    print("=" * 50)

    try:
        database_path = resolve_target_database(args.database)
    except DatabasePathViolation as exc:
        print(f"❌ Отказ: {exc}")
        return 2

    # Анализируем текущее состояние
    stats = analyze_database(database_path)

    if stats['test_activities'] == 0 and stats['total_hrv'] == 0:
        print("\n✨ База данных уже чистая!")
        return 0

    print("\n📋 План очистки:")
    print(f"  🗑️  Удалить {stats['test_activities']} тестовых активностей")
    print(f"  🗑️  Удалить {stats['total_hrv']} HRV записей")
    print(f"  ✅ Оставить {stats['real_activities']} реальных активностей")

    try:
        _require_operator_confirmation(database_path, stats)
    except SystemExit as exc:
        print(exc)
        return 1

    # Выполняем очистку
    if clean_database(database_path, confirm=False):
        verify_cleanup(database_path)
        print("\n🎉 База данных готова для загрузки реальных данных из Garmin!")
        print("\n📱 Теперь можете:")
        print("  1. Запустить: streamlit run app.py")
        print("  2. Подключиться к Garmin Connect")
        print("  3. Синхронизировать реальные данные")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
