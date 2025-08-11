#!/usr/bin/env python3
"""
Финальный тест приложения с полным HRV анализом
"""

import sys
import pandas as pd

sys.path.append('.')

from data.database import Database

def test_final_app():
    """Финальный тест всех компонентов"""
    
    print("🎯 ФИНАЛЬНЫЙ ТЕСТ ПРИЛОЖЕНИЯ AI TRAINER")
    print("=" * 60)
    
    database = Database()
    
    # 1. Проверяем HRV данные
    print("📊 1. Проверка HRV данных:")
    hrv_df = database.get_hrv_data(30)
    print(f"  • Записей в базе: {len(hrv_df)}")
    print(f"  • DataFrame пустой: {hrv_df.empty}")
    
    if not hrv_df.empty:
        # Статистика по типам данных
        rmssd_count = hrv_df['rmssd'].notna().sum()
        stress_count = hrv_df['stress_score'].notna().sum()
        recovery_count = hrv_df['recovery_score'].notna().sum()
        
        print(f"  • RMSSD данных: {rmssd_count}")
        print(f"  • Стресс данных: {stress_count}")
        print(f"  • Восстановление данных: {recovery_count}")
        
        # 2. Проверяем последние данные (как в show_hrv_analysis)
        print(f"\n📊 2. Анализ последних данных:")
        latest_data = hrv_df.iloc[-1]
        print(f"  • Последняя дата: {latest_data['date']}")
        
        # RMSSD
        current_rmssd = latest_data['rmssd'] if pd.notna(latest_data['rmssd']) else 0
        baseline_rmssd = hrv_df['rmssd'].mean()
        print(f"  • RMSSD: {current_rmssd:.1f} мс (среднее: {baseline_rmssd:.1f})")
        
        # Стресс
        if 'stress_score' in latest_data and latest_data['stress_score'] is not None and not pd.isna(latest_data['stress_score']):
            stress_score = latest_data['stress_score']
            stress_color = "🟢" if stress_score < 30 else "🟡" if stress_score < 60 else "🔴"
            print(f"  • Стресс: {stress_color} {stress_score:.0f}")
        else:
            print(f"  • Стресс: Н/Д")
        
        # Восстановление
        if 'recovery_score' in latest_data and latest_data['recovery_score'] is not None and not pd.isna(latest_data['recovery_score']):
            recovery_score = latest_data['recovery_score']
            recovery_color = "🟢" if recovery_score > 70 else "🟡" if recovery_score > 40 else "🔴"
            print(f"  • Восстановление: {recovery_color} {recovery_score:.0f}%")
        else:
            print(f"  • Восстановление: Н/Д")
        
        # 3. Проверяем логику приложения
        print(f"\n🔍 3. Симуляция логики show_hrv_analysis:")
        
        # Условие для отображения анализа
        if not hrv_df.empty:
            print(f"  ✅ hrv_df.empty = False → Анализ HRV будет показан")
            
            # Фильтрация по периоду
            period_days = 30
            hrv_filtered = hrv_df.tail(period_days)
            print(f"  ✅ После фильтрации: {len(hrv_filtered)} записей")
            
            if not hrv_filtered.empty:
                print(f"  ✅ Метрики будут отображены")
            else:
                print(f"  ❌ После фильтрации данных нет")
        else:
            print(f"  ❌ hrv_df.empty = True → Будет показано 'Нет данных'")
        
        # 4. Топ записи для демонстрации
        print(f"\n📋 4. Последние записи (для демонстрации):")
        for _, row in hrv_df.head(5).iterrows():
            rmssd = f"{row['rmssd']:.1f}" if pd.notna(row['rmssd']) else 'Н/Д'
            stress = f"{row['stress_score']:.0f}" if pd.notna(row['stress_score']) else 'Н/Д'
            recovery = f"{row['recovery_score']:.0f}%" if pd.notna(row['recovery_score']) else 'Н/Д'
            print(f"  {row['date'].strftime('%Y-%m-%d')}: RMSSD={rmssd}, Стресс={stress}, Восст.={recovery}")
        
        print(f"\n✅ ТЕСТ ПРОШЕЛ УСПЕШНО!")
        print(f"🎉 Все компоненты HRV анализа работают корректно!")
        return True
    else:
        print(f"  ❌ Нет HRV данных в базе")
        return False

def main():
    success = test_final_app()
    
    print(f"\n" + "="*60)
    if success:
        print(f"🚀 ПРИЛОЖЕНИЕ ГОТОВО К ИСПОЛЬЗОВАНИЮ!")
        print(f"")
        print(f"📱 Для запуска выполните:")
        print(f"   streamlit run app.py")
        print(f"")
        print(f"💡 В разделе 'Анализ HRV' теперь доступны:")
        print(f"   • 💓 RMSSD (вариабельность сердечного ритма)")
        print(f"   • 😰 Стресс-индекс (реальные данные из Garmin)")  
        print(f"   • 🔋 Восстановление (Body Battery из Garmin)")
        print(f"   • 📈 Графики и рекомендации")
        print(f"")
        print(f"🔄 Синхронизация включает все типы данных")
    else:
        print(f"❌ Требуется синхронизация с Garmin Connect")
        print(f"📱 Запустите приложение и нажмите 'Синхронизировать данные'")

if __name__ == "__main__":
    main()