
# Пример использования GarminClient с поддержкой garth

from data.garmin_client import GarminClient
from datetime import datetime, timedelta

# Создание клиента
client = GarminClient()

# Проверка доступности garth
info = client.get_connection_info()
print(f"Garth доступен: {info['garth_available']}")

# Авторизация (сначала попробует garth, потом garminconnect)
success = client.authenticate("email@example.com", "password")
if success:
    print(f"Авторизация успешна, используется: {'garth' if client.use_garth else 'garminconnect'}")
    
    # Получение данных сна (автоматически выберет лучший метод)
    yesterday = datetime.now() - timedelta(days=1)
    sleep_data = client.get_sleep_data(yesterday)
    
    if sleep_data:
        print("Данные сна получены!")
        # Обработка данных...
    else:
        print("Данные сна недоступны")
    
    # Тестирование garth подключения
    if client.use_garth:
        test_results = client.test_garth_connection()
        print(f"Тест garth: {test_results}")

# Отключение
client.disconnect()
