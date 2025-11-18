import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
from urllib.parse import quote

# Загружаем переменные окружения
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_KEYS = {
    "gibdd": os.getenv('GIBDD_API_KEY'),
    "nsis": os.getenv('NSIS_API_KEY'),
    "eaisto": os.getenv('EAISTO_API_KEY')
}

# Проверка загрузки токенов
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Клавиатуры
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚗 Проверить по гос.номеру"), 
         KeyboardButton("🔍 Проверить по VIN коду")],
        [KeyboardButton("ℹ️ О боте")]
    ], resize_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("⬅️ Назад в меню")]
    ], resize_keyboard=True)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} ({user.id}) запустил бота")
    
    welcome_text = """
🤖 Добро пожаловать в бот для проверки автомобилей!

Возможности бота:
• Проверка по VIN коду
• Проверка по гос. номеру
• Данные из ГИБДД
• Информация об ОСАГО
• Данные о техосмотре

Выберите способ проверки:
    """
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о боте"""
    about_text = """
ℹ️ О боте

Этот бот помогает получить информацию об автомобилях через официальные API:

• ГИБДД - история регистрации, характеристики
• НСИС - данные о полисах ОСАГО  
• ЕАИСТО - информация о техосмотре

Бот использует официальные источники данных.
    """
    await update.message.reply_text(about_text, reply_markup=get_main_keyboard())

# Функции валидации
def validate_vin(vin: str) -> bool:
    """Проверка валидности VIN кода"""
    vin = vin.upper().strip()
    if len(vin) != 17:
        return False
    # Дополнительные проверки можно добавить
    return True

def validate_license_plate(plate: str) -> bool:
    """Проверка валидности гос. номера"""
    plate = plate.upper().replace(' ', '')
    # Российские номера: буква, 3 цифры, 2 буквы, 2-3 цифры региона
    if 8 <= len(plate) <= 9:
        return True
    return False

# Функции запросов к API
# Функции запросов к API с диагностикой
async def make_gibdd_request(query: str, query_type: str) -> str:
    """Запрос к API ГИБДД с диагностикой"""
    try:
        url = "https://parser-api.com/gibdd-ru/vin" if query_type == 'vin' else "https://parser-api.com/gibdd-ru/regnum"
        
        logger.info(f"ГИБДД запрос: {url}")
        logger.info(f"ГИБДД ключ: {API_KEYS['gibdd'][:10]}...")  # Логируем только начало ключа
        
        headers = {
            "Authorization": API_KEYS["gibdd"],
            "Content-Type": "application/json",
            "User-Agent": "TelegramBot/1.0"
        }
        
        payload = {query_type: query}
        
        response = requests.post(
            url, 
            json=payload, 
            headers=headers,
            timeout=15
        )
        
        logger.info(f"ГИБДД статус: {response.status_code}")
        logger.info(f"ГИБДД заголовки: {dict(response.headers)}")
        logger.info(f"ГИБДД ответ (первые 500 символов): {response.text[:500]}")
        
        # Пробуем распарсить JSON
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"ГИБДД JSON ошибка: {e}")
            return "❌ **ГИБДД:** Неверный формат ответа от сервера"
        
        if data.get('success'):
            vehicle = data.get('history', {})
            result = "✅ **Данные ГИБДД:**\n"
            result += f"• Марка: {vehicle.get('model', 'Н/Д')}\n"
            result += f"• Год: {vehicle.get('year', 'Н/Д')}\n"
            result += f"• Цвет: {vehicle.get('color', 'Н/Д')}\n"
            result += f"• Объем: {vehicle.get('engineVolume', 'Н/Д')} см³\n"
            result += f"• Мощность: {vehicle.get('powerHp', 'Н/Д')} л.с.\n"
            result += f"• VIN: {vehicle.get('vin', 'Н/Д')}\n"
            
            # Добавляем информацию о владельцах
            owners = vehicle.get('ownershipPeriods', [])
            if owners:
                result += f"• Владельцев: {len(owners)}\n"
            
            return result
        else:
            error_msg = data.get('error', 'Данные не найдены')
            return f"❌ **ГИБДД:** {error_msg}"
            
    except requests.exceptions.Timeout:
        logger.error("ГИБДД: Таймаут запроса")
        return "❌ **ГИБДД:** Таймаут запроса"
    except requests.exceptions.ConnectionError:
        logger.error("ГИБДД: Ошибка соединения")
        return "❌ **ГИБДД:** Ошибка соединения"
    except Exception as e:
        logger.error(f"ГИБДД ошибка: {e}")
        return "❌ **ГИБДД:** Ошибка запроса"

async def make_nsis_request(query: str, query_type: str) -> str:
    """Запрос к API НСИС (ОСАГО) с диагностикой"""
    try:
        url = "https://parser-api.com/nsis-osago/vin" if query_type == 'vin' else "https://parser-api.com/nsis-osago/regnum"
        
        logger.info(f"НСИС запрос: {url}")
        
        headers = {
            "Authorization": API_KEYS["nsis"],
            "Content-Type": "application/json",
            "User-Agent": "TelegramBot/1.0"
        }
        
        payload = {query_type: query}
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        logger.info(f"НСИС статус: {response.status_code}")
        logger.info(f"НСИС ответ (первые 500 символов): {response.text[:500]}")
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"НСИС JSON ошибка: {e}")
            return "❌ **ОСАГО:** Неверный формат ответа от сервера"
        
        if data.get('success'):
            policies = data.get('policies', [])
            if policies:
                policy = policies[0]
                result = "✅ **Данные ОСАГО:**\n"
                result += f"• Компания: {policy.get('companyName', 'Н/Д')}\n"
                result += f"• Полис: {policy.get('policySerial', '')} {policy.get('policyNumber', '')}\n"
                result += f"• Период: {policy.get('startDate', '')} - {policy.get('endDate', '')}\n"
                result += f"• Статус: {policy.get('status', 'Н/Д')}\n"
                return result
            else:
                return "❌ **ОСАГО:** Полисы не найдены"
        else:
            error_msg = data.get('error', 'Данные не найдены')
            return f"❌ **ОСАГО:** {error_msg}"
            
    except requests.exceptions.Timeout:
        logger.error("НСИС: Таймаут запроса")
        return "❌ **ОСАГО:** Таймаут запроса"
    except Exception as e:
        logger.error(f"НСИС ошибка: {e}")
        return "❌ **ОСАГО:** Ошибка запроса"

async def make_eaisto_request(query: str, query_type: str) -> str:
    """Запрос к API ЕАИСТО с диагностикой"""
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        url = f"https://parser-api.com/eaisto/{query_type}?{query_type}={encoded_query}"
        
        logger.info(f"ЕАИСТО запрос: {url}")
        
        headers = {
            "Authorization": API_KEYS["eaisto"],
            "User-Agent": "TelegramBot/1.0"
        }
        
        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )
        
        logger.info(f"ЕАИСТО статус: {response.status_code}")
        logger.info(f"ЕАИСТО ответ (первые 500 символов): {response.text[:500]}")
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"ЕАИСТО JSON ошибка: {e}")
            return "❌ **Техосмотр:** Неверный формат ответа от сервера"
        
        if data.get('kbm_done') and data.get('diagnose_cards'):
            card = data['diagnose_cards'][0]
            result = "✅ **Данные техосмотра:**\n"
            result += f"• Карта: {card.get('number', 'Н/Д')}\n"
            result += f"• Период: {card.get('startDate', '')} - {card.get('endDate', '')}\n"
            result += f"• Пробег: {card.get('mileage', 'Н/Д')} км\n"
            return result
        else:
            return "❌ **Техосмотр:** Действующих диагностических карт не найдено"
            
    except requests.exceptions.Timeout:
        logger.error("ЕАИСТО: Таймаут запроса")
        return "❌ **Техосмотр:** Таймаут запроса"
    except Exception as e:
        logger.error(f"ЕАИСТО ошибка: {e}")
        return "❌ **Техосмотр:** Ошибка запроса"
    
async def check_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка работоспособности API"""
    test_vin = "Z94CB41AAGR323020"  # Тестовый VIN
    
    await update.message.reply_text("🔍 Проверяю API ключи...")
    
    # Проверяем ГИБДД
    gibdd_result = await make_gibdd_request(test_vin, 'vin')
    
    # Проверяем НСИС  
    nsis_result = await make_nsis_request(test_vin, 'vin')
    
    # Проверяем ЕАИСТО
    eaisto_result = await make_eaisto_request(test_vin, 'vin')
    
    result_text = f"📊 **Результаты проверки API:**\n\n"
    result_text += f"{gibdd_result}\n\n"
    result_text += f"{nsis_result}\n\n"
    result_text += f"{eaisto_result}"
    
    await update.message.reply_text(result_text)

# Основная функция обработки запроса
async def process_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса пользователя"""
    user_input = update.message.text.strip()
    query_type = context.user_data.get('mode')
    
    # Валидация ввода
    if query_type == 'vin' and not validate_vin(user_input):
        await update.message.reply_text(
            "❌ Неверный формат VIN кода!\n"
            "VIN должен содержать 17 символов (буквы и цифры)\n"
            "Пример: Z94CB41AAGR323020",
            reply_markup=get_back_keyboard()
        )
        return
        
    elif query_type == 'reg_num' and not validate_license_plate(user_input):
        await update.message.reply_text(
            "❌ Неверный формат гос. номера!\n"
            "Примеры правильных форматов:\n"
            "• А123БВ777\n• Е001КХ178\n• Х123ХХ123",
            reply_markup=get_back_keyboard()
        )
        return

    # Отправляем сообщение о начале проверки
    progress_msg = await update.message.reply_text(
        "🔍 Запрашиваю данные...\n"
        "Это может занять несколько секунд",
        reply_markup=get_back_keyboard()
    )

    try:
        # Выполняем запросы к API
        gibdd_result = await make_gibdd_request(user_input, query_type)
        nsis_result = await make_nsis_request(user_input, query_type)  
        eaisto_result = await make_eaisto_request(user_input, query_type)
        
        # Формируем итоговый ответ
        result_text = f"📊 **Результаты проверки:**\n\n"
        result_text += f"{gibdd_result}\n\n"
        result_text += f"{nsis_result}\n\n" 
        result_text += f"{eaisto_result}\n\n"
        result_text += "➡️ Для нового запроса выберите способ проверки"
        
        await update.message.reply_text(result_text, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при запросе данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    
    # Очищаем состояние пользователя
    context.user_data.clear()

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений"""
    text = update.message.text
    user_data = context.user_data

    if text == "⬅️ Назад в меню":
        user_data.clear()
        await start(update, context)
        
    elif text == "🚗 Проверить по гос.номеру":
        user_data['mode'] = 'reg_num'
        await update.message.reply_text(
            "Введите **гос. номер** автомобиля:\n\n"
            "Примеры:\n"
            "• А123БВ777\n"  
            "• Е001КХ178\n"
            "• Х123ХХ123",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
        
    elif text == "🔍 Проверить по VIN коду":
        user_data['mode'] = 'vin'
        await update.message.reply_text(
            "Введите **VIN код** автомобиля (17 символов):\n\n"
            "Пример: Z94CB41AAGR323020",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
        
    elif text == "ℹ️ О боте":
        await about_bot(update, context)
        
    elif user_data.get('mode'):
        await process_query(update, context)
        
    else:
        await update.message.reply_text(
            "Используйте кнопки для навигации 👇",
            reply_markup=get_main_keyboard()
        )

# Основная функция
def main():
    """Запуск бота"""
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CommandHandler("checkapi", check_api))
        
        # Запускаем бота
        logger.info("Бот запускается...")
        print("🤖 Бот запущен! Нажмите Ctrl+C для остановки")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()