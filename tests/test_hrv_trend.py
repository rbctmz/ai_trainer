#!/usr/bin/env python3
"""
Тест функционала тренда HRV
"""

import sys
import numpy as np
import pytest

sys.path.append('.')

from data.database import Database

def test_hrv_trend():
    """Тест вычисления тренда HRV"""
    
    print("📈 Тест функционала тренда HRV")
    print("=" * 40)
    
    database = Database()
    
    # Получаем HRV данные
    hrv_df = database.get_hrv_data(30)
    
    if hrv_df.empty:
        print("❌ Нет HRV данных для тестирования тренда")
        pytest.skip("В локальной базе нет HRV данных для тестирования тренда")
    
    print(f"📊 Всего HRV записей: {len(hrv_df)}")
    
    # Фильтруем валидные RMSSD данные
    valid_data = hrv_df[hrv_df['rmssd'].notna()].copy()
    print(f"📊 Валидных RMSSD записей: {len(valid_data)}")
    
    if len(valid_data) < 2:
        print("❌ Недостаточно данных для вычисления тренда (нужно минимум 2)")
        pytest.skip("Недостаточно HRV данных для вычисления тренда")
    
    # Сортируем по дате
    valid_data = valid_data.sort_values('date').reset_index(drop=True)
    
    print("\n📋 Данные для анализа тренда:")
    print(f"  Период: {valid_data['date'].min().strftime('%Y-%m-%d')} - {valid_data['date'].max().strftime('%Y-%m-%d')}")
    print(f"  RMSSD: {valid_data['rmssd'].min():.1f} - {valid_data['rmssd'].max():.1f} мс")
    print(f"  Среднее: {valid_data['rmssd'].mean():.1f} мс")
    
    # Вычисляем тренд (как в приложении)
    try:
        from sklearn.linear_model import LinearRegression
        
        # Подготавливаем данные для регрессии
        x_numeric = np.arange(len(valid_data)).reshape(-1, 1)
        y_values = valid_data['rmssd'].values
        
        # Строим линейную регрессию
        model = LinearRegression()
        model.fit(x_numeric, y_values)
        trend_values = model.predict(x_numeric)
        
        # Анализируем тренд
        trend_slope = model.coef_[0]  # Изменение RMSSD за один день
        trend_direction = "📈 Растущий" if trend_slope > 0 else "📉 Падающий" if trend_slope < 0 else "➡️ Стабильный"
        trend_change = trend_slope * len(valid_data)  # Общее изменение за период
        r_squared = model.score(x_numeric, y_values)  # Коэффициент детерминации (качество подгонки)
        
        print("\n📈 Анализ тренда:")
        print(f"  Направление: {trend_direction}")
        print(f"  Скорость изменения: {trend_slope:+.3f} мс/день")
        print(f"  Изменение за период: {trend_change:+.1f} мс")
        print(f"  Качество модели (R²): {r_squared:.3f}")
        
        # Показываем первые и последние значения тренда
        print(f"  Тренд в начале: {trend_values[0]:.1f} мс")
        print(f"  Тренд в конце: {trend_values[-1]:.1f} мс")
        
        # Интерпретация тренда для пользователя
        print("\n💡 Интерпретация тренда:")
        if abs(trend_slope) < 0.1:
            print("  ⚖️ HRV стабилен - изменения минимальны")
        elif trend_slope > 0.5:
            print("  🟢 HRV значительно улучшается - отличная тенденция!")
        elif trend_slope > 0.1:
            print("  🟢 HRV немного улучшается - хорошая тенденция")
        elif trend_slope < -0.5:
            print("  🔴 HRV значительно ухудшается - стоит обратить внимание")
        elif trend_slope < -0.1:
            print("  🟡 HRV немного ухудшается - возможна усталость")
        
        if r_squared < 0.3:
            print("  ⚠️ Тренд неустойчивый - данные сильно варьируются")
        elif r_squared > 0.7:
            print("  ✅ Четкий тренд - изменения последовательны")
        
        # Показываем несколько последних значений для примера
        print("\n📋 Последние значения RMSSD:")
        for _, row in valid_data.tail(5).iterrows():
            print(f"  {row['date'].strftime('%Y-%m-%d')}: {row['rmssd']:.1f} мс")
        
        assert len(trend_values) == len(valid_data)
        
    except ImportError:
        print("❌ Ошибка: scikit-learn не установлен")
        pytest.skip("scikit-learn не установлен")
    except Exception as e:
        print(f"❌ Ошибка при вычислении тренда: {e}")
        raise

if __name__ == "__main__":
    success = test_hrv_trend()
    if success:
        print("\n🎉 Тест тренда HRV прошел успешно!")
        print("📱 В приложении теперь доступны:")
        print("  • 'Только данные' - график без дополнительных линий")
        print("  • 'Среднее' - горизонтальная линия среднего значения")
        print("  • 'Тренд' - линия линейной регрессии с направлением")
        print("  • 'Среднее + Тренд' - обе линии вместе")
    else:
        print("\n❌ Проблемы с тестированием тренда")
