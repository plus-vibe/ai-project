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
                    "temperature": 0.1 # Делаем модель более предсказуемой и строгой
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            print(f"❌ Ошибка Ollama: {e}")
            return ""
    
    def parse_transaction(self, text: str) -> Optional[Dict]:
        prompt = f"""Ты - строгий парсер финансовых трат. 
Извлеки сумму и категорию из текста: "{text}"

Ответь СТРОГО валидным JSON объектом. Никаких пояснений, никакого markdown (без ```json). 
Формат:
{{
    "amount": число (сумма в рублях, только цифры),
    "category": строка (строго одна из: Еда, Транспорт, Развлечения, Покупки, Здоровье, Образование, Другое),
    "description": строка (краткое описание, 1-3 слова)
}}

Если сумму найти невозможно, верни: {{"amount": null, "category": "Другое", "description": ""}}
"""
        
        response = self._call_ollama(prompt)
        print(f"🤖 Сырой ответ от LLM:\n{response}", flush=True)
        
        if not response:
            return None
        
        try:
            # 1. Убираем markdown-обёртки, если модель всё-таки их добавила
            clean_response = response.replace("```json", "").replace("```", "").strip()
            
            # 2. Ищем первую { и последнюю }
            start_idx = clean_response.find("{")
            end_idx = clean_response.rfind("}") + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = clean_response[start_idx:end_idx]
                data = json.loads(json_str)
                
                # 3. Проверяем, что есть сумма
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
        
        prompt = f"""Ты — дружелюбный финансовый помощник. Твоя задача — дать короткий инсайт пользователю.

ВАЖНО: Отвечай СТРОГО на РУССКОМ языке. Никаких других языков.

Данные:
- Трата: {amount}₽ ({category})
- Потрачено сегодня: {today_total}₽ из лимита {daily_limit}₽ (осталось {remaining}₽)
- Потрачено за неделю на категорию "{category}": {week_total}₽

Примеры правильных ответов (на русском!):
- ☕ Первая трата на еду сегодня, отличный старт!
- 🚕 Многовато на такси за неделю — 2800₽. Может, в следующий раз пройдёшься пешком?
- 👍 Вписываешься в лимит, так держать!

Правила:
- Ответ ТОЛЬКО на русском языке
- 1-2 предложения максимум
- 1-2 эмодзи в начале
- Если трата большая — мягко предупреди
- Если всё хорошо — похвали
- Без markdown, только текст

Инсайт:"""
        
        response = self._call_ollama(prompt)
        
        # Дополнительная защита: если модель всё-таки ответила не на русском, 
        # используем шаблонный инсайт
        if response and not any(c in response for c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'):
            print(f"⚠️ Модель ответила не на русском, используем шаблон", flush=True)
            if today_total > daily_limit:
                return f"⚠️ Ты уже потратил {today_total:.0f}₽ из лимита {daily_limit:.0f}₽. Будь осторожнее!"
            elif week_total > 5000:
                return f"📊 За неделю на {category.lower()} уже {week_total:.0f}₽. Возможно, стоит сократить."
            else:
                return f"✅ Записал. На {category.lower()} за неделю потрачено {week_total:.0f}₽."
        
        return response.strip() if response else ""