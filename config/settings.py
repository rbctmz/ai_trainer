import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()


def _env_flag(name: str, default: str = "0") -> bool:
    raw_value = os.getenv(name, default)
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}

class Settings:
    """Настройки приложения"""
    
    # AI Провайдеры
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    
    # Провайдер по умолчанию
    DEFAULT_AI_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "openai")
    
    # Garmin Connect
    GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
    GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

    # Intervals.icu (опционально) — персональный API key для sync planned workouts
    INTERVALS_ICU_API_KEY = os.getenv("INTERVALS_ICU_API_KEY")
    INTERVALS_ICU_ATHLETE_ID = os.getenv("INTERVALS_ICU_ATHLETE_ID", "0")
    INTERVALS_ICU_BASE_URL = os.getenv("INTERVALS_ICU_BASE_URL", "https://intervals.icu")
    
    # База данных
    DATABASE_PATH = os.getenv("DATABASE_PATH", "ai_trainer.db")

    # Acceptance mode: isolated runtime for safe browser verification
    ACCEPTANCE_MODE = _env_flag("ACCEPTANCE_MODE", "0")
    ACCEPTANCE_AUTO_DEMO = _env_flag(
        "ACCEPTANCE_AUTO_DEMO",
        "1" if ACCEPTANCE_MODE else "0",
    )
    ACCEPTANCE_DISABLE_GARMIN = _env_flag(
        "ACCEPTANCE_DISABLE_GARMIN",
        "1" if ACCEPTANCE_MODE else "0",
    )
    ACCEPTANCE_LABEL = os.getenv("ACCEPTANCE_LABEL", "Acceptance Mode")
    
    # Пороги пользователя
    USER_FTP = int(os.getenv("USER_FTP", 250))
    USER_LTHR = int(os.getenv("USER_LTHR", 170))
    USER_MAX_HR = int(os.getenv("USER_MAX_HR", 185))
    
    # Параметры модели Банистера по умолчанию
    BANISTER_K1 = 1.0
    BANISTER_K2 = 2.0
    BANISTER_TAU1 = 42.0
    BANISTER_TAU2 = 7.0
    
    # Окна для расчёта CTL/ATL
    CTL_WINDOW = 42  # дней
    ATL_WINDOW = 7   # дней
    
    # HRV пороги
    HRV_DFA_AEROBIC_THRESHOLD = 0.75
    HRV_DFA_ANAEROBIC_THRESHOLD = 0.5

    # Garmin FIT SDK (опционально) — путь к FitCSVTool.jar для сборки .fit из CSV
    FIT_SDK_JAR = os.getenv("FIT_SDK_JAR", "")

    # Developer-only controls in the main product shell
    SHOW_DEVELOPMENT_TOOLS = os.getenv("SHOW_DEVELOPMENT_TOOLS", "0") == "1"
