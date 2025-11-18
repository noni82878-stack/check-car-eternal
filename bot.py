import os
import logging
import requests
import json
from urllib.parse import quote
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
    return True

def validate_license_plate(plate: str) -> bool:
    """Проверка валидности гос. номера"""
    plate = plate.upper().replace(' ', '').replace('-', '')
    
    # Российские форматы номеров:
    # Х999ХХ99 (старый) - 8 символов
    # Х999ХХ999 (новый) - 9 символов  
    # ХХ99999 (мотоциклы) - 7 символов
    
    if 7 <= len(plate) <= 9:
        # Проверяем, что номер содержит только буквы и цифры
        return all(c.isalnum() for c in plate)
    return False

# Базовые функции API (для VIN - работают отлично)
async def make_gibdd_request(query: str, query_type: str) -> str:
    """Запрос к API ГИБДД"""
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        
        url = f"https://parser-api.com/parser/gibdd_api/history?key={API_KEYS['gibdd']}&{query_type}={encoded_query}"
        
        logger.info(f"ГИБДД запрос: {url}")
        
        headers = {
            "User-Agent": "TelegramBot/1.0"
        }
        
        response = requests.get(
            url, 
            headers=headers,
            timeout=20
        )
        
        logger.info(f"ГИБДД статус: {response.status_code}")
        logger.info(f"ГИБДД заголовки: {dict(response.headers)}")
        
        # Детальное логирование при ошибке 400
        if response.status_code == 400:
            logger.error(f"ГИБДД 400 ошибка: {response.text}")
        
        # Пробуем распарсить JSON
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"ГИБДД JSON ошибка: {e}")
            logger.error(f"ГИБДД полный ответ: {response.text}")
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
    """Запрос к API НСИС (ОСАГО)"""
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        
        url = f"https://parser-api.com/parser/osago_api/?key={API_KEYS['nsis']}&{query_type}={encoded_query}"
        
        logger.info(f"НСИС запрос: {url}")
        
        headers = {
            "User-Agent": "TelegramBot/1.0"
        }
        
        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )
        
        logger.info(f"НСИС статус: {response.status_code}")
        
        # Детальное логирование при ошибке 400
        if response.status_code == 400:
            logger.error(f"НСИС 400 ошибка: {response.text}")
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"НСИС JSON ошибка: {e}")
            logger.error(f"НСИС полный ответ: {response.text}")
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
    """Запрос к API ЕАИСТО"""
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        
        url = f"https://parser-api.com/parser/eaisto_mileage_api/?key={API_KEYS['eaisto']}&{query_type}={encoded_query}"
        
        logger.info(f"ЕАИСТО запрос: {url}")
        
        headers = {
            "User-Agent": "TelegramBot/1.0"
        }
        
        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )
        
        logger.info(f"ЕАИСТО статус: {response.status_code}")
        
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"ЕАИСТО JSON ошибка: {e}")
            logger.error(f"ЕАИСТО полный ответ: {response.text}")
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

# Расширенные функции API для гос.номеров (экспериментальные)
async def make_gibdd_request_advanced(query: str, query_type: str) -> str:
    """Расширенный запрос к API ГИБДД с разными параметрами"""
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        
        # Для VIN используем стандартный подход
        if query_type == 'vin':
            return await make_gibdd_request(query, query_type)
        
        # Для гос.номера пробуем разные варианты параметров
        param_variants = ['regnum', 'reg_number', 'number', 'plate', 'license_plate']
        
        for param_name in param_variants:
            url = f"https://parser-api.com/parser/gibdd_api/history?key={API_KEYS['gibdd']}&{param_name}={encoded_query}"
            
            logger.info(f"ГИБДД пробуем параметр '{param_name}': {url}")
            
            headers = {
                "User-Agent": "TelegramBot/1.0"
            }
            
            response = requests.get(
                url, 
                headers=headers,
                timeout=10
            )
            
            logger.info(f"ГИБДД статус с параметром '{param_name}': {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('success'):
                        vehicle = data.get('history', {})
                        result = "✅ **Данные ГИБДД:**\n"
                        result += f"• Марка: {vehicle.get('model', 'Н/Д')}\n"
                        result += f"• Год: {vehicle.get('year', 'Н/Д')}\n"
                        result += f"• Цвет: {vehicle.get('color', 'Н/Д')}\n"
                        result += f"• Объем: {vehicle.get('engineVolume', 'Н/Д')} см³\n"
                        result += f"• Мощность: {vehicle.get('powerHp', 'Н/Д')} л.с.\n"
                        result += f"• VIN: {vehicle.get('vin', 'Н/Д')}\n"
                        
                        owners = vehicle.get('ownershipPeriods', [])
                        if owners:
                            result += f"• Владельцев: {len(owners)}\n"
                        
                        logger.info(f"ГИБДД УСПЕХ с параметром '{param_name}'!")
                        return result
                except json.JSONDecodeError:
                    continue
            elif response.status_code == 400:
                logger.info(f"ГИБДД 400 с параметром '{param_name}': {response.text[:200]}")
        
        # Если ни один вариант не сработал
        return "❌ **ГИБДД:** Не удалось получить данные по гос.номеру"
            
    except Exception as e:
        logger.error(f"ГИБДД расширенный запрос ошибка: {e}")
        return "❌ **ГИБДД:** Ошибка запроса"

async def make_nsis_request_advanced(query: str, query_type: str) -> str:
    """Расширенный запрос к API НСИС с разными параметрами"""
    try:
        encoded_query = quote(query)
        
        # Для VIN используем стандартный подход
        if query_type == 'vin':
            return await make_nsis_request(query, query_type)
        
        # Для гос.номера пробуем разные варианты параметров
        param_variants = ['regnum', 'reg_number', 'number', 'plate', 'license_plate']
        
        for param_name in param_variants:
            url = f"https://parser-api.com/parser/osago_api/?key={API_KEYS['nsis']}&{param_name}={encoded_query}"
            
            logger.info(f"НСИС пробуем параметр '{param_name}': {url}")
            
            headers = {
                "User-Agent": "TelegramBot/1.0"
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )
            
            logger.info(f"НСИС статус с параметром '{param_name}': {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('success'):
                        policies = data.get('policies', [])
                        if policies:
                            policy = policies[0]
                            result = "✅ **Данные ОСАГО:**\n"
                            result += f"• Компания: {policy.get('companyName', 'Н/Д')}\n"
                            result += f"• Полис: {policy.get('policySerial', '')} {policy.get('policyNumber', '')}\n"
                            result += f"• Период: {policy.get('startDate', '')} - {policy.get('endDate', '')}\n"
                            result += f"• Статус: {policy.get('status', 'Н/Д')}\n"
                            logger.info(f"НСИС УСПЕХ с параметром '{param_name}'!")
                            return result
                except json.JSONDecodeError:
                    continue
            elif response.status_code == 400:
                logger.info(f"НСИС 400 с параметром '{param_name}': {response.text[:200]}")
        
        return "❌ **ОСАГО:** Не удалось получить данные по гос.номеру"
            
    except Exception as e:
        logger.error(f"НСИС расширенный запрос ошибка: {e}")
        return "❌ **ОСАГО:** Ошибка запроса"

# Команда для тестирования гос.номеров
async def test_plate_formats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестирование разных форматов гос.номеров"""
    test_plates = [
        "А123БВ777",  # Кириллица
        "A123BC777",  # Латиница  
        "Е001КХ178",  # Кириллица с нулями
        "E001KX178",  # Латиница с нулями
        "Х123ХХ123",  # Кириллица новый формат
        "X123XX123",  # Латиница новый формат
        "B908EE35",   # Ваш тестовый номер
    ]
    
    await update.message.reply_text("🧪 Начинаю тестирование гос.номеров...")
    
    for plate in test_plates:
        await update.message.reply_text(f"🔍 Тестируем: {plate}")
        
        gibdd_result = await make_gibdd_request_advanced(plate, 'regnum')
        nsis_result = await make_nsis_request_advanced(plate, 'regnum')
        eaisto_result = await make_eaisto_request(plate, 'regnum')
        
        result_text = f"📊 **Результаты для {plate}:**\n\n"
        result_text += f"{gibdd_result}\n"
        result_text += f"{nsis_result}\n"
        result_text += f"{eaisto_result}\n"
        
        await update.message.reply_text(result_text)
    
    await update.message.reply_text("✅ Тестирование завершено!")

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
            "Пример: XTA111930B0134057",
            reply_markup=get_back_keyboard()
        )
        return
        
    elif query_type == 'regnum' and not validate_license_plate(user_input):
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
        # Для VIN используем стандартные функции, для гос.номера - расширенные
        if query_type == 'vin':
            gibdd_result = await make_gibdd_request(user_input, query_type)
            nsis_result = await make_nsis_request(user_input, query_type)
        else:
            gibdd_result = await make_gibdd_request_advanced(user_input, query_type)
            nsis_result = await make_nsis_request_advanced(user_input, query_type)
        
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
        user_data['mode'] = 'regnum'
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
            "Пример: XTA111930B0134057",
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
        application.add_handler(CommandHandler("checkapi", test_plate_formats))  # Для тестирования
        application.add_handler(CommandHandler("testplates", test_plate_formats))  # Для тестирования
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Запускаем бота
        logger.info("Бот запускается...")
        print("🤖 Бот запущен! Нажмите Ctrl+C для остановки")
        
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()