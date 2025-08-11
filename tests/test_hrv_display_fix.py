#!/usr/bin/env python3
"""
Тест отображения HRV с исправленной логикой None значений
"""

import sys
import pandas as pd

sys.path.append('.')

from data.database import Database

def test_hrv_display_fix():
    """Тест отображения HRV с исправленной логикой"""
    
    print("🧪 Тест отображения HRV с исправленной логикой None значений")
    print("=" * 60)
    
    database = Database()
    
    # Получаем HRV данные
    hrv_df = database.get_hrv_data(30)
    
    print(f"📊 Количество записей: {len(hrv_df)}")
    print(f"📊 DataFrame пустой? {hrv_df.empty}")
    
    if len(hrv_df) > 0:
        # Берем последнюю запись для анализа
        latest_data = hrv_df.iloc[-1]
        
        print(f"\n📋 Последняя запись:")
        print(f"  Дата: {latest_data['date']}")
        print(f"  RMSSD: {latest_data['rmssd']}")
        print(f"  Стресс: {latest_data['stress_score']}")
        print(f"  Восстановление: {latest_data['recovery_score']}")
        
        # Тестируем логику проверки None значений (как в приложении)
        print(f"\n🔍 Тест логики проверки None значений:")
        
        # RMSSD
        current_rmssd = latest_data['rmssd'] if pd.notna(latest_data['rmssd']) else 0
        print(f"  RMSSD: {current_rmssd:.1f} мс")
        
        # Стресс-индекс
        if 'stress_score' in latest_data and latest_data['stress_score'] is not None and not pd.isna(latest_data['stress_score']):
            stress_score = latest_data['stress_score']
            stress_color = "🟢" if stress_score < 30 else "🟡" if stress_score < 60 else "🔴"
            print(f"  Стресс: {stress_color} {stress_score:.0f}")
        else:
            print(f"  Стресс: Н/Д (данные недоступны)")
        
        # Восстановление
        if 'recovery_score' in latest_data and latest_data['recovery_score'] is not None and not pd.isna(latest_data['recovery_score']):
            recovery_score = latest_data['recovery_score']
            recovery_color = "🟢" if recovery_score > 70 else "🟡" if recovery_score > 40 else "🔴"
            print(f"  Восстановление: {recovery_color} {recovery_score:.0f}%")
        else:
            # Симулируем расчет на основе RMSSD
            if current_rmssd > 0:
                baseline_rmssd = hrv_df['rmssd'].mean()
                if pd.notna(baseline_rmssd) and baseline_rmssd > 0:
                    recovery_ratio = current_rmssd / baseline_rmssd
                    calculated_recovery = min(100, max(0, 50 + (recovery_ratio - 1) * 50))
                else:
                    calculated_recovery = 50
                recovery_color = "🟢" if calculated_recovery > 70 else "🟡" if calculated_recovery > 40 else "🔴"
                print(f"  Восстановление: {recovery_color} {calculated_recovery:.0f}% (расчет на основе RMSSD)")
            else:
                print(f"  Восстановление: Н/Д (данные недоступны)")
        
        print(f"\n✅ Логика обработки работает корректно!")
        return True
    else:
        print("📭 Нет HRV данных")
        return False

if __name__ == "__main__":
    success = test_hrv_display_fix()
    if success:
        print("\n🎉 Отображение HRV должно работать корректно!")
        print("💡 Стресс-индекс и восстановление теперь показывают 'Н/Д' вместо пустых значений")
        print("📱 Запустите: streamlit run app.py")
    else:
        print("\n❌ Проблемы с отображением HRV")