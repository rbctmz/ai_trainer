#!/usr/bin/env python3
"""
Тест логики отображения HRV (симуляция show_hrv_analysis)
"""

import sys
sys.path.append('.')

from data.database import Database
import pandas as pd

def test_hrv_logic():
    """Тест логики отображения HRV"""
    
    print("🧪 Тест логики show_hrv_analysis")
    print("=" * 40)
    
    database = Database()
    
    # Получаем HRV данные (как в show_hrv_analysis)
    hrv_df = database.get_hrv_data(30)  # За последние 30 дней
    
    print(f"📊 hrv_df.empty = {hrv_df.empty}")
    print(f"📊 len(hrv_df) = {len(hrv_df)}")
    
    if hrv_df.empty:
        print("📭 Будет показано: 'Нет данных HRV за последние 30 дней'")
        return False
    else:
        print("✅ HRV данные найдены, будет показан анализ")
        
        # Проверяем период (как в show_hrv_analysis)
        period_days = 30  # default value
        hrv_filtered = hrv_df.tail(period_days)
        hrv_filtered['date'] = pd.to_datetime(hrv_filtered['date'])
        
        print(f"📊 После фильтрации: {len(hrv_filtered)} записей")
        
        if not hrv_filtered.empty:
            latest_data = hrv_filtered.iloc[-1]
            baseline_rmssd = hrv_filtered['rmssd'].mean()
            
            print(f"📊 Последняя дата: {latest_data['date']}")
            print(f"📊 Последний RMSSD: {latest_data['rmssd']}")
            print(f"📊 Средний RMSSD: {baseline_rmssd:.1f}")
            
            # Проверяем валидность последних данных
            valid_rmssd = hrv_filtered['rmssd'].notna().sum()
            print(f"📊 Валидных RMSSD записей: {valid_rmssd}")
            
            if valid_rmssd > 0:
                print("✅ Будут показаны метрики и графики HRV")
                return True
            else:
                print("❌ Все RMSSD значения NaN - анализ будет ограничен")
                return False
        else:
            print("❌ После фильтрации данных нет")
            return False

if __name__ == "__main__":
    success = test_hrv_logic()
    if success:
        print("\n🎉 HRV анализ должен работать корректно!")
    else:
        print("\n❌ Найдены проблемы в логике HRV анализа")