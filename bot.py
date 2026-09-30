import asyncio
import os
import sys
import traceback
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from dotenv import load_dotenv

# ============================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================

print("✅ Шаг 1: Модули импортированы", flush=True)

load_dotenv()
print("✅ Шаг 2: .env загружен", flush=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
print(f"✅ Шаг 3: Токен получен: {BOT_TOKEN[:10] if BOT_TOKEN else 'НЕТ ТОКЕНА'}...", flush=True)

if not BOT_TOKEN:
    print("❌ ОШИБКА: Не указан BOT_TOKEN в .env файле", flush=True)
    sys.exit(1)

try:
    bot = Bot(token=BOT_TOKEN)
    print("✅ Шаг 4: Бот создан", flush=True)
except Exception as e:
    print(f"❌ ОШИБКА создания бота: {e}", flush=True)
    sys.exit(1)

dp = Dispatcher()
print("✅ Шаг 5: Dispatcher создан", flush=True)

from database import Database
from llm import OllamaLLM

db = Database()
print("✅ Шаг 6: Database инициализирована", flush=True)

llm = OllamaLLM()
print("✅ Шаг 7: LLM инициализирован", flush=True)

# Кэш user_id (telegram_id -> user_id в БД)
user_cache = {}

def get_user_id(telegram_id: int) -> int:
    """Получает или создаёт user_id"""
    if telegram_id not in user_cache:
        user_cache[telegram_id] = db.get_or_create_user(telegram_id)
    return user_cache[telegram_id]


# ============================================
# КОМАНДЫ
# ============================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Приветствие"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /start от пользователя {message.from_user.id}", flush=True)
    
    text = """💰 Привет! Я SmartWallet AI - твой умный помощник для учёта расходов.

Просто напиши мне, что купил:
• "кофе 350"
• "такси до работы 500"
• "продукты 2500"

Я сам определю категорию и дам полезный совет!

Команды:
/stats - статистика за неделю
/limit 2000 - установить дневной лимит
/help - помощь
"""
    await message.answer(text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Помощь"""
    print(f"✅ /help от пользователя {message.from_user.id}", flush=True)
    
    text = """📖 Как пользоваться:

1️⃣ Записать трату:
   Просто напиши что купил и сколько:
   • "кофе 350"
   • "обед 450"
   • "такси 800"

2️⃣ Статистика:
   /stats - покажет траты за неделю

3️⃣ Дневной лимит:
   /limit 2000 - установит лимит 2000₽/день

💡 После каждой записи я дам короткий инсайт!
"""
    await message.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика за неделю"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /stats от пользователя {message.from_user.id}", flush=True)
    
    try:
        stats = db.get_week_stats(user_id)
        
        if stats["total"] == 0:
            await message.answer("📊 За последнюю неделю трат не было.")
            return
        
        text = f"📊 Статистика за 7 дней:\n\n"
        text += f"💰 Всего: {stats['total']:.0f}₽\n"
        text += f"📅 Сегодня: {stats['today']:.0f}₽\n\n"
        
        if stats["categories"]:
            text += "По категориям:\n"
            for category, amount, count in stats["categories"]:
                percent = (amount / stats["total"]) * 100
                text += f"• {category}: {amount:.0f}₽ ({percent:.0f}%) - {count} трат\n"
        
        await message.answer(text)
    
    except Exception as e:
        print(f"❌ Ошибка в /stats: {e}", flush=True)
        traceback.print_exc()
        await message.answer("⚠️ Ошибка при получении статистики. Попробуй позже.")


@dp.message(Command("limit"))
async def cmd_limit(message: types.Message):
    """Установить дневной лимит"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /limit от пользователя {message.from_user.id}", flush=True)
    
    # Парсим аргумент команды
    args = message.text.split()
    if len(args) < 2:
        current_limit = db.get_daily_limit(user_id)
        await message.answer(f"💡 Текущий дневной лимит: {current_limit:.0f}₽\n\nИспользуй: /limit 2000")
        return
    
    try:
        new_limit = float(args[1])
        if new_limit <= 0:
            raise ValueError
        
        db.set_daily_limit(user_id, new_limit)
        await message.answer(f"✅ Дневной лимит установлен: {new_limit:.0f}₽")
    except ValueError:
        await message.answer("❌ Укажи число. Пример: /limit 2000")


# ============================================
# ОБРАБОТКА ТРАТ
# ============================================

@dp.message(F.text)
async def handle_expense(message: types.Message):
    """Обработка текстовых сообщений (трат)"""
    user_id = get_user_id(message.from_user.id)
    
    try:
        processing_msg = await message.answer("🤔 Думаю...")
        
        print(f"📝 Обрабатываю: '{message.text}'", flush=True)
        
        # Парсим трату через LLM
        transaction = llm.parse_transaction(message.text)
        
        print(f"🔍 Результат парсинга: {transaction}", flush=True)
        
        if not transaction:
            await processing_msg.edit_text(
                "❌ Не понял сумму. Напиши в формате: 'кофе 350'\n\n"
                "💡 Я умею записывать траты, а не болтать 😄"
            )
            return
        
        # Сохраняем в БД
        db.add_transaction(
            user_id=user_id,
            amount=transaction["amount"],
            category=transaction["category"],
            description=transaction["description"]
        )
        
        print(f"✅ Трата сохранена: {transaction}", flush=True)
        
        # Получаем данные для инсайта
        week_total = db.get_category_week_total(user_id, transaction["category"])
        today_total = db.get_today_total(user_id)
        daily_limit = db.get_daily_limit(user_id)
        
        print(f"📊 Данные для инсайта: week={week_total}, today={today_total}, limit={daily_limit}", flush=True)
        
        # Генерируем инсайт
        insight = llm.generate_insight(
            amount=transaction["amount"],
            category=transaction["category"],
            week_total=week_total,
            today_total=today_total,
            daily_limit=daily_limit
        )
        
        print(f"💡 Инсайт: {insight}", flush=True)
        
        # Формируем ответ
        response = f"✅ Записал {transaction['amount']:.0f}₽ → {transaction['category']}\n"
        if insight:
            response += f"\n{insight}"
        
        await processing_msg.edit_text(response)
        print(f"✅ Ответ отправлен пользователю", flush=True)
    
    except Exception as e:
        print(f"❌ ОШИБКА в handle_expense: {e}", flush=True)
        traceback.print_exc()
        
        try:
            await message.answer(
                f"⚠️ Произошла ошибка при обработке.\n\n"
                f"Попробуй написать чётче, например:\n"
                f"• кофе 350\n"
                f"• такси 500\n"
                f"• продукты 2500"
            )
        except Exception as send_error:
            print(f"❌ Не удалось отправить сообщение об ошибке: {send_error}", flush=True)


# ============================================
# ЗАПУСК
# ============================================

async def main():
    """Запуск бота"""
    print("=" * 50, flush=True)
    print("🚀 Бот запущен!", flush=True)
    print(f"📱 Username: @{(await bot.get_me()).username}", flush=True)
    print("Ожидаю сообщения...", flush=True)
    print("=" * 50, flush=True)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n⏹ Бот остановлен пользователем", flush=True)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}", flush=True)
        traceback.print_exc()
    finally:
        await bot.session.close()
        print("✅ Сессия бота закрыта", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Бот остановлен", flush=True)
    except Exception as e:
        print(f"❌ ОШИБКА: {e}", flush=True)
        traceback.print_exc()