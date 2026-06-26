"""
Система логирования для AI Trainer
"""
import logging
import os
from datetime import datetime


class GarminLogger:
    """Логгер для отладки интеграции с Garmin"""
    
    def __init__(self):
        self.setup_logger()
    
    def setup_logger(self):
        """Настройка логгера"""
        # Создаем папку для логов
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Настраиваем логгер
        self.logger = logging.getLogger('garmin_sync')
        self.logger.setLevel(logging.DEBUG)
        
        # Удаляем старые хендлеры
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Файловый хендлер с ротацией по дням
        log_filename = f"logs/garmin_sync_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Консольный хендлер
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Форматтер
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Добавляем хендлеры
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def info(self, message):
        """Информационное сообщение"""
        self.logger.info(message)
    
    def debug(self, message):
        """Отладочное сообщение"""
        self.logger.debug(message)
    
    def warning(self, message):
        """Предупреждение"""
        self.logger.warning(message)
    
    def error(self, message):
        """Ошибка"""
        self.logger.error(message)
    
    def log_api_call(self, method, url, params=None, response=None, error=None):
        """Логирование API вызовов"""
        if params:
            self.debug(f"API CALL: {method} {url} with params: {params}")
        else:
            self.debug(f"API CALL: {method} {url}")
        
        if response:
            self.debug(f"API RESPONSE: Success - {type(response).__name__}")
        
        if error:
            self.error(f"API ERROR: {error}")
    
    def log_data_sync(self, data_type, date, success, data=None, error=None):
        """Логирование синхронизации данных"""
        if success:
            data_info = f"with data: {type(data).__name__}" if data else "no data"
            self.info(f"SYNC SUCCESS: {data_type} for {date} - {data_info}")
            if data and hasattr(data, '__dict__'):
                self.debug(f"SYNC DATA: {data_type} fields: {list(data.__dict__.keys())}")
        else:
            self.warning(f"SYNC FAILED: {data_type} for {date} - {error}")
    
    def log_garth_object(self, obj, obj_name="Object"):
        """Детальное логирование объектов garth"""
        self.debug(f"GARTH OBJECT: {obj_name} - Type: {type(obj).__name__}")
        
        if hasattr(obj, '__dict__'):
            fields = obj.__dict__
            self.debug(f"GARTH FIELDS: {obj_name} - {list(fields.keys())}")
            for key, value in fields.items():
                self.debug(f"GARTH FIELD: {obj_name}.{key} = {value} ({type(value).__name__})")
        elif hasattr(obj, 'dict'):
            try:
                fields = obj.dict()
                self.debug(f"GARTH DICT: {obj_name} - {fields}")
            except Exception as e:
                self.error(f"GARTH DICT ERROR: {obj_name} - {e}")
        else:
            self.debug(f"GARTH STRING: {obj_name} - {str(obj)}")


class LazyGarminLogger:
    """Ленивая обертка, чтобы импорт модуля не создавал файловые хендлеры."""

    def __init__(self):
        self._logger = None

    def _get_logger(self):
        if self._logger is None:
            self._logger = GarminLogger()
        return self._logger

    def __getattr__(self, name):
        return getattr(self._get_logger(), name)


# Глобальный экземпляр логгера
garmin_logger = LazyGarminLogger()
