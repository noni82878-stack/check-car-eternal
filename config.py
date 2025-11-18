import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    GIBDD_API_KEY = os.getenv('GIBDD_API_KEY')
    NSIS_API_KEY = os.getenv('NSIS_API_KEY')
    EAISTO_API_KEY = os.getenv('EAISTO_API_KEY')
    
    @classmethod
    def validate(cls):
        """Проверка наличия всех необходимых переменных"""
        required_vars = ['BOT_TOKEN', 'GIBDD_API_KEY', 'NSIS_API_KEY', 'EAISTO_API_KEY']
        missing = [var for var in required_vars if not getattr(cls, var)]
        if missing:
            raise ValueError(f"Отсутствуют переменные окружения: {', '.join(missing)}")