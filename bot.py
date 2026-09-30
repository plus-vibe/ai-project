import asyncio
import os
import sys
import traceback
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import BufferedInputFile
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
from charts import ChartGenerator

db = Database()
print("✅ Шаг 6: Database инициализирована", flush=True)

llm = OllamaLLM()
print("✅ Шаг 7: LLM инициализирован", flush=True)

charts = ChartGenerator()
print("✅ Шаг 8: ChartGenerator инициализирован", flush=True)

user_cache = {}

def get_user_id(telegram_id: int) -> int:
    if telegram_id not in user_cache:
        user_cache[telegram_id] = db.get_or_create_user(telegram_id)
    return user_cache[telegram_id]


# ============================================
# БАЗОВЫЕ КОМАНДЫ
# ============================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /start от пользователя {message.from_user.id}", flush=True)
    
    text = """💰 Привет! Я SmartWallet AI — твой умный финансовый коуч.

📝 Просто напиши, что купил:
• "кофе 350"
• "такси до работы 500"
• "продукты 2500"

🎯 Возможности:
• /goal 1000000 2026-12-31 — установить цель
• /patterns — анализ трат по дням недели
• /whatif кофе — симулятор экономии
• /stats — статистика за неделю
• /chart — графики трат 📊
• /chart month — графики за месяц
• /limit 2000 — дневной лимит

🔔 Каждое утро в 9:00 я присылаю персональный инсайт!
"""
    await message.answer(text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    print(f"✅ /help от пользователя {message.from_user.id}", flush=True)
    
    text = """📖 Команды SmartWallet AI:

📝 Учёт трат:
• Просто напиши "кофе 350" — я сам определю категорию

🎯 Финансовые цели:
• /goal 1000000 2026-12-31 — накопить миллион к дате
• /goal off — отключить цель

📊 Аналитика:
• /stats — статистика за неделю
• /chart — графики трат (круговая + по дням + сравнение недель)
• /chart month — графики за месяц
• /patterns — в какие дни ты тратишь больше
• /whatif кофе — сколько сэкономишь, если отказаться

💰 Лимиты:
• /limit 2000 — дневной лимит трат

💡 После каждой записи я даю короткий инсайт!
"""
    await message.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
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
        
        # Если есть цель — показываем прогресс
        goal = db.get_goal(user_id)
        if goal:
            text += f"\n🎯 Цель: {goal['amount']:.0f}₽ к {goal['deadline']}"
        
        await message.answer(text)
    
    except Exception as e:
        print(f"❌ Ошибка в /stats: {e}", flush=True)
        traceback.print_exc()
        await message.answer("⚠️ Ошибка при получении статистики.")


@dp.message(Command("limit"))
async def cmd_limit(message: types.Message):
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /limit от пользователя {message.from_user.id}", flush=True)
    
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
# KILLER FEATURES
# ============================================

@dp.message(Command("goal"))
async def cmd_goal(message: types.Message):
    """Установка финансовой цели"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /goal от пользователя {message.from_user.id}", flush=True)
    
    args = message.text.split()
    
    # /goal off — отключить цель
    if len(args) >= 2 and args[1].lower() == "off":
        db.set_goal(user_id, 0, None)
        await message.answer("🎯 Цель отключена. Ты можешь установить новую командой /goal 1000000 2026-12-31")
        return
    
    # /goal — показать текущую цель
    if len(args) < 3:
        goal = db.get_goal(user_id)
        if goal:
            days_left = (datetime.strptime(goal["deadline"], "%Y-%m-%d") - datetime.now()).days
            await message.answer(
                f"🎯 Текущая цель:\n"
                f"💰 Накопить: {goal['amount']:.0f}₽\n"
                f"📅 К дате: {goal['deadline']}\n"
                f"⏳ Осталось дней: {days_left}\n\n"
                f"Отключить: /goal off\n"
                f"Изменить: /goal 1000000 2026-12-31"
            )
        else:
            await message.answer(
                "🎯 У тебя пока нет финансовой цели.\n\n"
                "Пример:\n"
                "/goal 1000000 2026-12-31\n"
                "(накопить 1 млн ₽ к 31 декабря 2026)"
            )
        return
    
    # /goal сумма дата — установить цель
    try:
        amount = float(args[1].replace(" ", "").replace(",", ""))
        deadline = args[2]
        
        # Проверяем формат даты
        datetime.strptime(deadline, "%Y-%m-%d")
        
        if amount <= 0:
            raise ValueError
        
        db.set_goal(user_id, amount, deadline)
        
        # Считаем, сколько нужно откладывать
        days_left = (datetime.strptime(deadline, "%Y-%m-%d") - datetime.now()).days
        months_left = days_left / 30
        monthly_saving = amount / months_left if months_left > 0 else amount
        
        # Рассчитываем новый дневной лимит (упрощённо)
        current_limit = db.get_daily_limit(user_id)
        
        await message.answer(
            f"🎯 Цель установлена!\n\n"
            f"💰 Накопить: {amount:.0f}₽\n"
            f"📅 К дате: {deadline}\n"
            f"⏳ Осталось дней: {days_left}\n\n"
            f"📊 План:\n"
            f"• Откладывать в месяц: {monthly_saving:.0f}₽\n"
            f"• Откладывать в день: {amount/days_left:.0f}₽\n\n"
            f"💡 Текущий дневной лимит трат: {current_limit:.0f}₽\n"
            f"Хочешь изменить лимит? /limit 2000"
        )
    
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Пример:\n"
            "/goal 1000000 2026-12-31\n\n"
            "Сумма — число, дата — в формате ГГГГ-ММ-ДД"
        )
    except Exception as e:
        print(f"❌ Ошибка в /goal: {e}", flush=True)
        await message.answer("⚠️ Ошибка при установке цели.")


@dp.message(Command("patterns"))
async def cmd_patterns(message: types.Message):
    """Анализ паттернов трат по дням недели"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /patterns от пользователя {message.from_user.id}", flush=True)
    
    try:
        patterns = db.get_day_of_week_stats(user_id, days=30)
        
        if not patterns:
            await message.answer(
                "📊 Пока недостаточно данных для анализа паттернов.\n\n"
                "Записывай траты хотя бы неделю, и я покажу, в какие дни ты тратишь больше всего!"
            )
            return
        
        text = "🔍 Твои финансовые паттерны (за 30 дней):\n\n"
        
        for p in patterns:
            text += f"• {p['day_name']}: {p['total']:.0f}₽ ({p['count']} трат, среднее {p['avg_per_day']:.0f}₽/день)\n"
        
        # Находим самый "дорогой" день
        most_expensive = patterns[0]
        text += f"\n🔥 Самый затратный день: {most_expensive['day_name']}\n"
        text += f"💡 В этот день ты тратишь в среднем {most_expensive['avg_per_day']:.0f}₽"
        
        # Если есть цель — добавляем совет
        goal = db.get_goal(user_id)
        if goal and len(patterns) > 1:
            text += f"\n\n🎯 Для достижения цели '{goal['amount']:.0f}₽ к {goal['deadline']}' попробуй сократить траты по {most_expensive['day_name']} на 20%"
        
        await message.answer(text)
    
    except Exception as e:
        print(f"❌ Ошибка в /patterns: {e}", flush=True)
        traceback.print_exc()
        await message.answer("⚠️ Ошибка при анализе паттернов.")


@dp.message(Command("whatif"))
async def cmd_whatif(message: types.Message):
    """What-if симулятор"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /whatif от пользователя {message.from_user.id}", flush=True)
    
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "💭 What-if симулятор\n\n"
            "Узнай, сколько ты сэкономишь, если откажешься от чего-то.\n\n"
            "Примеры:\n"
            "• /whatif кофе\n"
            "• /whatif такси\n"
            "• /whatif развлечения"
        )
        return
    
    # Берём только ВТОРОЕ слово (первое - это команда /whatif)
    category_input = args[1].strip().lower()
    
    # Маппинг пользовательских названий на категории БД
    category_map = {
        "кофе": "Еда",
        "еда": "Еда",
        "продукты": "Еда",
        "ресторан": "Еда",
        "обед": "Еда",
        "завтрак": "Еда",
        "ужин": "Еда",
        "такси": "Транспорт",
        "транспорт": "Транспорт",
        "метро": "Транспорт",
        "автобус": "Транспорт",
        "бензин": "Транспорт",
        "развлечения": "Развлечения",
        "кино": "Развлечения",
        "бар": "Развлечения",
        "алкоголь": "Развлечения",
        "кафе": "Развлечения",
        "покупки": "Покупки",
        "одежда": "Покупки",
        "обувь": "Покупки",
        "электроника": "Покупки",
        "здоровье": "Здоровье",
        "врач": "Здоровье",
        "лекарства": "Здоровье",
        "аптека": "Здоровье",
        "образование": "Образование",
        "курсы": "Образование",
        "книги": "Образование",
        "обучение": "Образование"
    }
    
    category = category_map.get(category_input)
    
    if not category:
        await message.answer(
            f"❌ Не знаю категорию '{category_input}'.\n\n"
            f"Попробуй:\n"
            f"• /whatif кофе\n"
            f"• /whatif такси\n"
            f"• /whatif развлечения\n"
            f"• /whatif покупки\n"
            f"• /whatif здоровье\n"
            f"• /whatif образование"
        )
        return
    
    try:
        # Получаем данные о категории
        data = db.get_category_year_estimate(user_id, category)
        
        if data["week_total"] == 0:
            await message.answer(
                f"📊 У тебя пока нет трат по категории '{category}'.\n\n"
                f"Записывай траты, и я покажу, сколько ты сможешь сэкономить!"
            )
            return
        
        # Примеры для эмоциональной подачи
        year_saving = data["year_estimate"] / 2
        examples = []
        if year_saving > 100000:
            examples.append(f"• {year_saving:.0f}₽ — это почти новый iPhone")
        if year_saving > 50000:
            examples.append(f"• {year_saving:.0f}₽ — это 2 недели отдыха в Турции")
        if year_saving > 20000:
            examples.append(f"• {year_saving:.0f}₽ — это хорошая подушка безопасности")
        if year_saving > 5000:
            examples.append(f"• {year_saving:.0f}₽ — это новый смартфон")
        
        # Генерируем ответ через LLM
        insight = llm.generate_whatif(
            category=category,
            current_week=data["week_total"],
            year_estimate=data["year_estimate"],
            real_examples=examples[:2] if examples else []
        )
        
        text = f"💭 Что если отказаться от '{category}'?\n\n"
        text += f"📊 Сейчас:\n"
        text += f"• За неделю: {data['week_total']:.0f}₽\n"
        text += f"• За год (прогноз): {data['year_estimate']:.0f}₽\n\n"
        text += f"💰 Если сократить на 50%:\n"
        text += f"• Экономия в год: {data['year_estimate']/2:.0f}₽\n\n"
        if insight:
            text += insight
        
        await message.answer(text)
    
    except Exception as e:
        print(f"❌ Ошибка в /whatif: {e}", flush=True)
        traceback.print_exc()
        await message.answer("⚠️ Ошибка при расчёте.")


# ============================================
# ОБРАБОТКА ТРАТ
# ============================================
@dp.message(Command("chart"))
async def cmd_chart(message: types.Message):
    """Генерация графиков"""
    user_id = get_user_id(message.from_user.id)
    print(f"✅ /chart от пользователя {message.from_user.id}", flush=True)
    
    args = message.text.split()
    days = 7
    
    if len(args) >= 2:
        try:
            if args[1].lower() == "month":
                days = 30
            elif args[1].isdigit():
                days = int(args[1])
                if days < 1 or days > 90:
                    raise ValueError
        except:
            await message.answer(
                "📊 Использование:\n"
                "• /chart — за неделю\n"
                "• /chart month — за месяц\n"
                "• /chart 14 — за 14 дней"
            )
            return
    
    await message.answer("🎨 Генерирую графики...")
    
    try:
        # 1. Круговая диаграмма
        pie_buf = charts.generate_pie_chart(user_id, days)
        if pie_buf:
            period_text = "неделю" if days == 7 else f"{days} дней"
            await message.answer_photo(
                photo=BufferedInputFile(pie_buf.getvalue(), filename="pie.png"),
                caption=f"📊 Распределение трат за {period_text}"
            )
        else:
            await message.answer("📊 Нет данных для круговой диаграммы.")
        
        # 2. График по дням
        daily_buf = charts.generate_daily_chart(user_id, days)
        if daily_buf:
            period_text = "неделю" if days == 7 else f"{days} дней"
            await message.answer_photo(
                photo=BufferedInputFile(daily_buf.getvalue(), filename="daily.png"),
                caption=f"📅 Траты по дням за {period_text}"
            )
        
        # 3. Сравнение недель (только если запрошена неделя)
        if days == 7:
            comparison_buf = charts.generate_comparison_chart(user_id)
            if comparison_buf:
                await message.answer_photo(
                    photo=BufferedInputFile(comparison_buf.getvalue(), filename="comparison.png"),
                    caption="📊 Сравнение этой и прошлой недели"
                )
    
    except Exception as e:
        print(f"❌ Ошибка в /chart: {e}", flush=True)
        import traceback
        traceback.print_exc()
        await message.answer("⚠️ Ошибка при генерации графиков.")


@dp.message(F.text)
async def handle_expense(message: types.Message):
    user_id = get_user_id(message.from_user.id)
    
    try:
        processing_msg = await message.answer("🤔 Думаю...")
        
        print(f"📝 Обрабатываю: '{message.text}'", flush=True)
        
        transaction = llm.parse_transaction(message.text)
        
        print(f"🔍 Результат парсинга: {transaction}", flush=True)
        
        if not transaction:
            await processing_msg.edit_text(
                "❌ Не понял сумму. Напиши в формате: 'кофе 350'\n\n"
                "💡 Я умею записывать траты, а не болтать 😄"
            )
            return
        
        db.add_transaction(
            user_id=user_id,
            amount=transaction["amount"],
            category=transaction["category"],
            description=transaction["description"]
        )
        
        print(f"✅ Трата сохранена: {transaction}", flush=True)
        
        week_total = db.get_category_week_total(user_id, transaction["category"])
        today_total = db.get_today_total(user_id)
        daily_limit = db.get_daily_limit(user_id)
        
        print(f"📊 Данные для инсайта: week={week_total}, today={today_total}, limit={daily_limit}", flush=True)
        
        insight = llm.generate_insight(
            amount=transaction["amount"],
            category=transaction["category"],
            week_total=week_total,
            today_total=today_total,
            daily_limit=daily_limit
        )
        
        print(f"💡 Инсайт: {insight}", flush=True)
        
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
# ФОНОВАЯ ЗАДАЧА: УТРЕННИЕ УВЕДОМЛЕНИЯ
# ============================================

async def morning_alert_task():
    """Фоновая задача, которая каждое утро в 9:00 отправляет персональные уведомления"""
    print("🔔 Задача утренних уведомлений запущена", flush=True)
    
    last_sent_date = None
    
    while True:
        try:
            now = datetime.now()
            current_date = now.strftime("%Y-%m-%d")
            
            # Проверяем, что сейчас 9:00 и сегодня ещё не отправляли
            if now.hour == 9 and now.minute == 0 and last_sent_date != current_date:
                print(f"🔔 Время утренних уведомлений! {now}", flush=True)
                
                users = db.get_users_with_morning_alert()
                
                for user_id, telegram_id in users:
                    try:
                        # Собираем данные
                        today_day = db.get_today_day_name()
                        patterns = db.get_day_of_week_stats(user_id, days=30)
                        
                        # Находим среднее для текущего дня недели
                        today_avg = 0
                        for p in patterns:
                            if p["day_name"] == today_day:
                                today_avg = p["avg_per_day"]
                                break
                        
                        week_stats = db.get_week_stats(user_id)
                        daily_limit = db.get_daily_limit(user_id)
                        goal = db.get_goal(user_id)
                        
                        goal_info = None
                        if goal:
                            goal_info = {"amount": goal["amount"], "deadline": goal["deadline"]}
                        
                        # Генерируем сообщение через LLM
                        alert_text = llm.generate_morning_alert(
                            today_day=today_day,
                            today_avg=today_avg,
                            week_total=week_stats["total"],
                            daily_limit=daily_limit,
                            goal_info=goal_info
                        )
                        
                        if alert_text:
                            await bot.send_message(telegram_id, f"☀️ Доброе утро!\n\n{alert_text}")
                            print(f"✅ Уведомление отправлено пользователю {telegram_id}", flush=True)
                    
                    except Exception as e:
                        print(f"❌ Ошибка отправки уведомления пользователю {telegram_id}: {e}", flush=True)
                
                last_sent_date = current_date
            
            # Спим минуту перед следующей проверкой
            await asyncio.sleep(60)
        
        except Exception as e:
            print(f"❌ Ошибка в morning_alert_task: {e}", flush=True)
            await asyncio.sleep(60)


# ============================================
# ЗАПУСК
# ============================================

async def main():
    print("=" * 50, flush=True)
    print("🚀 Бот запущен!", flush=True)
    print(f"📱 Username: @{(await bot.get_me()).username}", flush=True)
    print("🔔 Утренние уведомления активны (9:00)", flush=True)
    print("Ожидаю сообщения...", flush=True)
    print("=" * 50, flush=True)
    
    try:
        # Запускаем фоновую задачу и polling параллельно
        await asyncio.gather(
            dp.start_polling(bot),
            morning_alert_task()
        )
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