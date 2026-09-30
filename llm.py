import requests
import json
import re
from typing import Dict, Optional

class OllamaLLM:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.base_url = base_url
        self.model = model
    
    def _call_ollama(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.0,  # Полная детерминированность
                    "top_p": 0.9,
                    "repeat_penalty": 1.1
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            print(f"❌ Ошибка Ollama: {e}")
            return ""
    
    def _is_mostly_russian(self, text: str, threshold: float = 0.7) -> bool:
        """Проверяет, что БОЛЬШИНСТВО символов — русские"""
        if not text or len(text) < 10:
            return False
        
        russian_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
        
        # Считаем только буквы (игнорируем цифры, пробелы, эмодзи)
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return False
        
        russian_count = sum(1 for c in letters if c in russian_chars)
        ratio = russian_count / len(letters)
        
        print(f"🔍 Проверка языка: {ratio:.2%} русских букв", flush=True)
        return ratio >= threshold
    
    def parse_transaction(self, text: str) -> Optional[Dict]:
        prompt = f"""Extract amount and category from this expense text: "{text}"

Return ONLY valid JSON, no markdown, no explanations:
{{
    "amount": number (rubles),
    "category": string (one of: Еда, Транспорт, Развлечения, Покупки, Здоровье, Образование, Другое),
    "description": string (1-3 words)
}}

If no amount found, return: {{"amount": null, "category": "Другое", "description": ""}}
"""
        
        response = self._call_ollama(prompt)
        
        if not response:
            return None
        
        try:
            clean_response = response.replace("```json", "").replace("```", "").strip()
            start_idx = clean_response.find("{")
            end_idx = clean_response.rfind("}") + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = clean_response[start_idx:end_idx]
                data = json.loads(json_str)
                
                if data.get("amount") is not None:
                    return {
                        "amount": float(data["amount"]),
                        "category": data.get("category", "Другое"),
                        "description": data.get("description", text)
                    }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"⚠️ Ошибка парсинга JSON: {e}", flush=True)
        
        return None
    
    def generate_insight(self, amount: float, category: str, week_total: float, today_total: float, daily_limit: float) -> str:
        remaining = daily_limit - today_total
        
        prompt = f"""You are a friendly financial assistant. Generate ONE short insight (1-2 sentences) in RUSSIAN language ONLY.

Data:
- Expense: {amount}₽ ({category})
- Spent today: {today_total}₽ of limit {daily_limit}₽ (remaining {remaining}₽)
- Spent this week on "{category}": {week_total}₽

Examples (in Russian):
- ☕ Первая трата на еду сегодня, отличный старт!
- 🚕 Многовато на такси за неделю — 2800₽. Может, в следующий раз пройдёшься пешком?
- 👍 Вписываешься в лимит, так держать!
- ⚠️ Сегодня ты уже потратил 2500₽ из 2000₽. Будь осторожнее!

Rules:
- ONLY RUSSIAN LANGUAGE (никаких английских, корейских, китайских символов)
- 1-2 sentences maximum
- 1-2 emojis at the beginning
- Be friendly and brief
- NO markdown

Insight (in Russian):"""
        
        response = self._call_ollama(prompt)
        
        # Строгая проверка: если не русский — используем шаблон
        if response and not self._is_mostly_russian(response):
            print(f"⚠️ Модель ответила не на русском, используем шаблон", flush=True)
            return self._template_insight(amount, category, week_total, today_total, daily_limit)
        
        return response.strip() if response else self._template_insight(amount, category, week_total, today_total, daily_limit)
    
    def _template_insight(self, amount: float, category: str, week_total: float, today_total: float, daily_limit: float) -> str:
        """Шаблонный инсайт, если LLM не справился"""
        remaining = daily_limit - today_total
        
        if today_total > daily_limit:
            return f"⚠️ Ты уже потратил {today_total:.0f}₽ из лимита {daily_limit:.0f}₽. Превышение на {today_total - daily_limit:.0f}₽!"
        elif remaining < 500:
            return f"⚠️ Осталось всего {remaining:.0f}₽ до лимита. Будь осторожнее!"
        elif week_total > 5000:
            return f"📊 За неделю на {category.lower()} уже {week_total:.0f}₽. Возможно, стоит сократить."
        elif week_total > 2000:
            return f"💰 На {category.lower()} за неделю потрачено {week_total:.0f}₽. Нормально, но следи."
        else:
            return f"✅ Записал. На {category.lower()} за неделю потрачено {week_total:.0f}₽."
    
    def generate_morning_alert(self, today_day: str, today_avg: float, week_total: float, daily_limit: float, goal_info: Optional[Dict]) -> str:
        goal_text = ""
        if goal_info:
            goal_text = f"\n- Financial goal: save {goal_info['amount']:.0f}₽ by {goal_info['deadline']}"
        
        prompt = f"""You are a friendly financial coach. Generate a short morning message in RUSSIAN language ONLY.

Data:
- Today: {today_day}
- Average spending on this day: {today_avg:.0f}₽
- Spent last week: {week_total:.0f}₽
- Daily limit: {daily_limit}₽{goal_text}

Examples (in Russian):
- ☀️ Доброе утро! Сегодня пятница — день, когда ты обычно тратишь больше. Давай поставим лимит 1500₽?
- 🎯 Напоминаю о цели: накопить 1000000₽ к 2026-12-31. Сегодня можешь потратить 2000₽.
- ⚠️ Сегодня суббота. В прошлые субботы ты тратил 3500₽. Попробуем уложиться в 2000₽?

Rules:
- ONLY RUSSIAN LANGUAGE
- 2-3 sentences maximum
- 1-2 emojis
- Be friendly, not preachy
- NO markdown

Message (in Russian):"""
        
        response = self._call_ollama(prompt)
        
        if response and not self._is_mostly_russian(response):
            print(f"⚠️ Утреннее уведомление не на русском, используем шаблон", flush=True)
            return self._template_morning_alert(today_day, today_avg, daily_limit, goal_info)
        
        return response.strip() if response else self._template_morning_alert(today_day, today_avg, daily_limit, goal_info)
    
    def _template_morning_alert(self, today_day: str, today_avg: float, daily_limit: float, goal_info: Optional[Dict]) -> str:
        """Шаблонное утреннее уведомление"""
        text = f"☀️ Доброе утро! Сегодня {today_day}.\n\n"
        
        if today_avg > daily_limit:
            text += f"⚠️ В этот день ты обычно тратишь {today_avg:.0f}₽ — больше лимита {daily_limit:.0f}₽. Будь осторожнее!"
        elif today_avg > 0:
            text += f"💰 В этот день ты обычно тратишь {today_avg:.0f}₽. Хорошего дня!"
        else:
            text += f"Дневной лимит: {daily_limit:.0f}₽. Удачи!"
        
        if goal_info:
            text += f"\n\n🎯 Напоминаю о цели: накопить {goal_info['amount']:.0f}₽ к {goal_info['deadline']}."
        
        return text
    
    def generate_whatif(self, category: str, current_week: float, year_estimate: float, real_examples: list) -> str:
        examples_text = ""
        if real_examples:
            examples_text = "\n\nExamples for comparison:\n" + "\n".join(real_examples)
        
        prompt = f"""You are a friendly financial assistant. Generate response in RUSSIAN language ONLY.

Data:
- Category: {category}
- Weekly spending: {current_week:.0f}₽
- Yearly estimate: {year_estimate:.0f}₽
- If reduce by 50%: save {year_estimate/2:.0f}₽{examples_text}

Task:
- Show yearly spending if nothing changes
- Show savings if reduce by 50%
- Give 1-2 examples what to do with saved money
- ONLY RUSSIAN LANGUAGE
- 3-4 sentences
- 2-3 emojis
- NO markdown

Response (in Russian):"""
        
        response = self._call_ollama(prompt)
        
        if response and not self._is_mostly_russian(response):
            print(f"⚠️ What-if ответ не на русском, используем шаблон", flush=True)
            return self._template_whatif(category, year_estimate)
        
        return response.strip() if response else self._template_whatif(category, year_estimate)
    
    def _template_whatif(self, category: str, year_estimate: float) -> str:
        """Шаблонный what-if ответ"""
        saving = year_estimate / 2
        
        text = f"💰 Если сократить траты на {category.lower()} на 50%, сэкономишь {saving:.0f}₽ за год.\n\n"
        
        if saving > 100000:
            text += f"📱 Это почти новый iPhone!"
        elif saving > 50000:
            text += f"✈️ Это 2 недели отдыха в Турции!"
        elif saving > 20000:
            text += f"💪 Это хорошая подушка безопасности!"
        else:
            text += f"🎯 Это отличная возможность для накоплений!"
        
        return text