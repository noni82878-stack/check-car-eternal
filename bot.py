import os
import logging
import requests
import json
from urllib.parse import quote
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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

def get_gibdd_inline_keyboard():
    """Инлайн-клавиатура для выбора типа проверки ГИБДД"""
    keyboard = [
        [
            InlineKeyboardButton("📜 История регистраций", callback_data="gibdd_history"),
            InlineKeyboardButton("🚗 Участие в ДТП", callback_data="gibdd_accident"),
        ],
        [
            InlineKeyboardButton("🚨 Нахождение в розыске", callback_data="gibdd_wanted"),
            InlineKeyboardButton("🔒 Наложенные ограничения", callback_data="gibdd_restrict"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.message.from_user
    logger.info(f"Пользователь {user.first_name} ({user.id}) запустил бота")
    
    welcome_text = """
🤖 Добро пожаловать в бот для проверки автомобилей!

Возможности бота:
• 🚗 Проверка по гос.номеру (ОСАГО и техосмотр)
• 🔍 Проверка по VIN коду (полная: ГИБДД, ОСАГО, техосмотр)

Выберите способ проверки:
    """
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о боте"""
    about_text = """
ℹ️ О боте

Этот бот помогает получить информацию об автомобилях через официальные API:

• ГИБДД - история регистрации, ДТП, розыск, ограничения
• НСИС - данные о полисах ОСАГО
• ЕАИСТО - информация о техосмотре

📋 Доступно:
• Полная проверка по VIN коду
• Проверка ОСАГО и техосмотра по гос.номеру
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
    if 7 <= len(plate) <= 9:
        return all(c.isalnum() for c in plate)
    return False

# Функции запросов к API
async def make_gibdd_request(query: str, query_type: str, check_type: str = "history") -> str:
    """
    Запрос к API ГИБДД
    
    check_type: history, accident, wanted, restrict
    """
    try:
        # Кодируем запрос для URL
        encoded_query = quote(query)
        
        # Определяем endpoint в зависимости от типа проверки
        endpoints = {
            "history": "https://parser-api.com/parser/gibdd_api/history",
            "accident": "https://parser-api.com/parser/gibdd_api/accident", 
            "wanted": "https://parser-api.com/parser/gibdd_api/wanted",
            "restrict": "https://parser-api.com/parser/gibdd_api/restrict"
        }
        
        url = f"{endpoints[check_type]}?key={API_KEYS['gibdd']}&{query_type}={encoded_query}"
        
        logger.info(f"ГИБДД запрос ({check_type}): {url}")
        
        headers = {"User-Agent": "TelegramBot/1.0"}
        
        response = requests.get(url, headers=headers, timeout=20)
        logger.info(f"ГИБДД статус ({check_type}): {response.status_code}")
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            return f"❌ **ГИБДД ({check_type}):** Неверный формат ответа"
        
        if data.get('success'):
            return format_gibdd_response(data, check_type)
        else:
            error_msg = data.get('error', 'Данные не найдены')
            return f"❌ **ГИБДД ({check_type}):** {error_msg}"
            
    except Exception as e:
        logger.error(f"ГИБДД ошибка ({check_type}): {e}")
        return f"❌ **ГИБДД ({check_type}):** Ошибка запроса"

def format_gibdd_response(data: dict, check_type: str) -> str:
    """Форматирование ответа от ГИБДД"""
    type_names = {
        "history": "📜 История регистраций",
        "accident": "🚗 Участие в ДТП", 
        "wanted": "🚨 Нахождение в розыске",
        "restrict": "🔒 Наложенные ограничения"
    }
    
    result = f"✅ **{type_names[check_type]}:**\n"
    
    if check_type == "history" and data.get('history'):
        vehicle = data['history']
        result += f"• Марка: {vehicle.get('model', 'Н/Д')}\n"
        result += f"• Год: {vehicle.get('year', 'Н/Д')}\n"
        result += f"• Цвет: {vehicle.get('color', 'Н/Д')}\n"
        result += f"• Объем: {vehicle.get('engineVolume', 'Н/Д')} см³\n"
        result += f"• Мощность: {vehicle.get('powerHp', 'Н/Д')} л.с.\n"
        
        owners = vehicle.get('ownershipPeriods', [])
        if owners:
            result += f"• Владельцев: {len(owners)}\n"
            
    elif check_type == "accident" and data.get('accidents'):
        accidents = data['accidents']
        result += f"• Найдено ДТП: {len(accidents)}\n"
        for i, accident in enumerate(accidents[:3], 1):  # Показываем первые 3
            result += f"• ДТП {i}: {accident.get('accidentDatetime', 'Н/Д')}\n"
            
    elif check_type == "wanted" and data.get('searches'):
        searches = data['searches']
        result += f"• Найдено записей о розыске: {len(searches)}\n"
        for search in searches[:2]:
            result += f"• Регион: {search.get('region', 'Н/Д')}\n"
            
    elif check_type == "restrict" and data.get('restrictions'):
        restrictions = data['restrictions']
        result += f"• Найдено ограничений: {len(restrictions)}\n"
        for restrict in restrictions[:2]:
            result += f"• Тип: {restrict.get('restriction_name', 'Н/Д')}\n"
    else:
        result += "• Данные не найдены\n"
    
    return result

async def make_nsis_request(query: str, query_type: str) -> str:
    """Запрос к API НСИС (ОСАГО)"""
    try:
        encoded_query = quote(query)
        
        # Используем правильное имя параметра для госномера
        param_name = "vin" if query_type == "vin" else "regNumber"
        url = f"https://parser-api.com/parser/osago_api/?key={API_KEYS['nsis']}&{param_name}={encoded_query}"
        
        logger.info(f"НСИС запрос: {url}")
        
        response = requests.get(url, headers={"User-Agent": "TelegramBot/1.0"}, timeout=30)
        logger.info(f"НСИС статус: {response.status_code}")
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            return "❌ **ОСАГО:** Неверный формат ответа"
        
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
            
    except Exception as e:
        logger.error(f"НСИС ошибка: {e}")
        return "❌ **ОСАГО:** Ошибка запроса"

async def make_eaisto_request(query: str, query_type: str) -> str:
    """Запрос к API ЕАИСТО"""
    try:
        encoded_query = quote(query)
        
        url = f"https://parser-api.com/parser/eaisto_mileage_api/?key={API_KEYS['eaisto']}&{query_type}={encoded_query}"
        
        logger.info(f"ЕАИСТО запрос: {url}")
        
        response = requests.get(url, headers={"User-Agent": "TelegramBot/1.0"}, timeout=20)
        logger.info(f"ЕАИСТО статус: {response.status_code}")
        
        try:
            data = response.json()
        except json.JSONDecodeError:
            return "❌ **Техосмотр:** Неверный формат ответа"
        
        if data.get('kbm_done') and data.get('diagnose_cards'):
            card = data['diagnose_cards'][0]
            result = "✅ **Данные техосмотра:**\n"
            result += f"• Карта: {card.get('number', 'Н/Д')}\n"
            result += f"• Период: {card.get('startDate', '')} - {card.get('endDate', '')}\n"
            result += f"• Пробег: {card.get('mileage', 'Н/Д')} км\n"
            return result
        else:
            return "❌ **Техосмотр:** Действующих диагностических карт не найдено"
            
    except Exception as e:
        logger.error(f"ЕАИСТО ошибка: {e}")
        return "❌ **Техосмотр:** Ошибка запроса"

# Обработка инлайн-кнопок ГИБДД
async def handle_gibdd_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки ГИБДД"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    vin = user_data.get('current_vin')
    check_type = query.data.replace('gibdd_', '')
    
    if not vin:
        await query.edit_message_text("❌ Не найден VIN для проверки")
        return
    
    type_names = {
        "history": "📜 истории регистраций",
        "accident": "🚗 участия в ДТП", 
        "wanted": "🚨 нахождения в розыске",
        "restrict": "🔒 наложенных ограничений"
    }
    
    await query.edit_message_text(f"🔍 Запрашиваю данные {type_names[check_type]}...")
    
    try:
        result = await make_gibdd_request(vin, 'vin', check_type)
        await query.edit_message_text(result)
    except Exception as e:
        logger.error(f"Ошибка при запросе ГИБДД: {e}")
        await query.edit_message_text("⚠️ Произошла ошибка при запросе данных")

# Основная функция обработки запроса
async def process_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса пользователя"""
    user_input = update.message.text.strip()
    query_type = context.user_data.get('mode')
    
    # Валидация ввода
    if query_type == 'vin' and not validate_vin(user_input):
        await update.message.reply_text(
            "❌ Неверный формат VIN кода!\nVIN должен содержать 17 символов\nПример: XTA111930B0134057",
            reply_markup=get_back_keyboard()
        )
        return
        
    elif query_type == 'regnum' and not validate_license_plate(user_input):
        await update.message.reply_text(
            "❌ Неверный формат гос. номера!\nПримеры: А123ВВ777, Е001КХ178",
            reply_markup=get_back_keyboard()
        )
        return

    await update.message.reply_text(
        "🔍 Запрашиваю данные...",
        reply_markup=get_back_keyboard()
    )

    try:
        if query_type == 'vin':
            # Сохраняем VIN для последующих запросов
            context.user_data['current_vin'] = user_input
            
            # Быстрая базовая проверка
            gibdd_result = await make_gibdd_request(user_input, 'vin', 'history')
            nsis_result = await make_nsis_request(user_input, 'vin')
            eaisto_result = await make_eaisto_request(user_input, 'vin')
            
            result_text = f"📊 **Базовые результаты по VIN:**\n\n"
            result_text += f"{gibdd_result}\n"
            result_text += f"{nsis_result}\n"
            result_text += f"{eaisto_result}\n\n"
            result_text += "🔍 **Для детальной проверки выберите тип запроса:**"
            
            await update.message.reply_text(
                result_text, 
                reply_markup=get_gibdd_inline_keyboard()
            )
            
        else:  # regnum
            # Для гос.номера - ОСАГО и техосмотр
            nsis_result = await make_nsis_request(user_input, 'regnum')
            eaisto_result = await make_eaisto_request(user_input, 'regnum')
            
            result_text = f"📊 **Результаты проверки по гос.номеру:**\n\n"
            result_text += f"{nsis_result}\n"
            result_text += f"{eaisto_result}\n\n"
            result_text += "💡 *Для полной проверки используйте VIN код*\n\n"
            result_text += "➡️ Для нового запроса выберите способ проверки"
            
            await update.message.reply_text(result_text, reply_markup=get_main_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при запросе данных. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    
    if query_type != 'vin':  # Для VIN состояние сохраняем для инлайн-кнопок
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
            "Примеры:\n• А123БВ777\n• Е001КХ178\n• Х123ХХ123\n\n"
            "💡 *Доступны данные ОСАГО и техосмотра*",
            reply_markup=get_back_keyboard(),
            parse_mode='Markdown'
        )
        
    elif text == "🔍 Проверить по VIN коду":
        user_data['mode'] = 'vin'
        await update.message.reply_text(
            "Введите **VIN код** автомобиля (17 символов):\n\n"
            "Пример: XTA111930B0134057\n\n"
            "💡 *Доступны полные данные: ГИБДД, ОСАГО, техосмотр*",
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
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(handle_gibdd_button, pattern="^gibdd_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Бот запускается...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()