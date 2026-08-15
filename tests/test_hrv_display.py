#!/usr/bin/env python3
"""
Тест отображения HRV данных
"""

import sys
sys.path.append('.')

from data.database import Database

def test_hrv_display():
    """Тест отображения HRV данных"""
    
    print("🧪 Тест отображения HRV данных")
    print("=" * 40)
    
    database = Database()
    
    # Получаем HRV данные
    hrv_df = database.get_hrv_data(30)
    
    print(f"📊 Количество записей: {len(hrv_df)}")
    print(f"📊 DataFrame пустой? {hrv_df.empty}")
    
    if len(hrv_df) > 0:
        print(f"📊 Колонки: {list(hrv_df.columns)}")
        print(f"📊 Типы данных:\n{hrv_df.dtypes}")
        print("\n📋 Первые несколько записей:")
        print(hrv_df.head())
        
        # Проверим RMSSD значения
        print("\n💓 RMSSD статистика:")
        print(f"  Всего значений: {len(hrv_df['rmssd'])}")
        print(f"  Не NaN значений: {hrv_df['rmssd'].notna().sum()}")
        print(f"  Среднее RMSSD: {hrv_df['rmssd'].mean():.1f}")
        print(f"  Мин RMSSD: {hrv_df['rmssd'].min():.1f}")
        print(f"  Макс RMSSD: {hrv_df['rmssd'].max():.1f}")
        
        # Показываем последние записи с действительными данными
        valid_hrv = hrv_df[hrv_df['rmssd'].notna()]
        print("\n📋 Последние записи с валидными RMSSD:")
        for _, row in valid_hrv.tail(5).iterrows():
            print(f"  {row['date']}: RMSSD = {row['rmssd']}")
    else:
        print("📭 Нет HRV данных")

if __name__ == "__main__":
    test_hrv_display()