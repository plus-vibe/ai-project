import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = "wallet.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    daily_limit REAL DEFAULT 3000,
                    goal_amount REAL DEFAULT 0,
                    goal_deadline DATE,
                    morning_alert_enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            conn.commit()
    
    def get_or_create_user(self, telegram_id: int) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return row[0]
            
            cursor = conn.execute(
                "INSERT INTO users (telegram_id) VALUES (?)",
                (telegram_id,)
            )
            conn.commit()
            return cursor.lastrowid
    
    def add_transaction(self, user_id: int, amount: float, category: str, description: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO transactions (user_id, amount, category, description)
                   VALUES (?, ?, ?, ?)""",
                (user_id, amount, category, description)
            )
            conn.commit()
    
    # ========== БАЗОВАЯ АНАЛИТИКА ==========
    
    def get_week_stats(self, user_id: int) -> Dict:
        week_ago = datetime.now() - timedelta(days=7)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND created_at > ?""",
                (user_id, week_ago)
            )
            total = cursor.fetchone()[0]
            
            cursor = conn.execute(
                """SELECT category, SUM(amount), COUNT(*)
                   FROM transactions
                   WHERE user_id = ? AND created_at > ?
                   GROUP BY category
                   ORDER BY SUM(amount) DESC""",
                (user_id, week_ago)
            )
            categories = cursor.fetchall()
            
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cursor = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND created_at > ?""",
                (user_id, today)
            )
            today_total = cursor.fetchone()[0]
            
            return {
                "total": total,
                "today": today_total,
                "categories": categories
            }
    
    def get_category_week_total(self, user_id: int, category: str) -> float:
        week_ago = datetime.now() - timedelta(days=7)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND category = ? AND created_at > ?""",
                (user_id, category, week_ago)
            )
            return cursor.fetchone()[0]
    
    def get_today_total(self, user_id: int) -> float:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND created_at > ?""",
                (user_id, today)
            )
            return cursor.fetchone()[0]
    
    def get_daily_limit(self, user_id: int) -> float:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT daily_limit FROM users WHERE id = ?",
                (user_id,)
            )
            return cursor.fetchone()[0]
    
    def set_daily_limit(self, user_id: int, limit: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET daily_limit = ? WHERE id = ?",
                (limit, user_id)
            )
            conn.commit()
    
    # ========== KILLER FEATURES ==========
    
    def set_goal(self, user_id: int, amount: float, deadline: str):
        """Устанавливает финансовую цель"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET goal_amount = ?, goal_deadline = ? WHERE id = ?",
                (amount, deadline, user_id)
            )
            conn.commit()
    
    def get_goal(self, user_id: int) -> Dict:
        """Получает информацию о цели"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT goal_amount, goal_deadline FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row[0] and row[0] > 0:
                return {"amount": row[0], "deadline": row[1]}
            return None
    
    def get_daily_saving_target(self, user_id: int) -> Optional[float]:
        """Считает, сколько нужно откладывать в день для достижения цели"""
        goal = self.get_goal(user_id)
        if not goal:
            return None
        
        try:
            deadline = datetime.strptime(goal["deadline"], "%Y-%m-%d")
            days_left = (deadline - datetime.now()).days
            
            if days_left <= 0:
                return None
            
            # Считаем, сколько уже отложено (упрощённо: считаем средние траты и вычитаем из дохода)
            # Для MVP просто делим цель на дни
            return goal["amount"] / days_left
        except:
            return None
    
    def get_day_of_week_stats(self, user_id: int, days: int = 30) -> List[Dict]:
        """Анализирует траты по дням недели за последние N дней"""
        since = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            # SQLite: strftime('%w', ...) возвращает 0=воскресенье, 1=понедельник, ...
            cursor = conn.execute(
                """SELECT 
                    CASE CAST(strftime('%w', created_at) AS INTEGER)
                        WHEN 0 THEN 'Воскресенье'
                        WHEN 1 THEN 'Понедельник'
                        WHEN 2 THEN 'Вторник'
                        WHEN 3 THEN 'Среда'
                        WHEN 4 THEN 'Четверг'
                        WHEN 5 THEN 'Пятница'
                        WHEN 6 THEN 'Суббота'
                    END as day_name,
                    CAST(strftime('%w', created_at) AS INTEGER) as day_num,
                    SUM(amount) as total,
                    COUNT(*) as count,
                    COUNT(DISTINCT date(created_at)) as days_with_spending
                FROM transactions
                WHERE user_id = ? AND created_at > ?
                GROUP BY day_num
                ORDER BY total DESC""",
                (user_id, since)
            )
            
            results = []
            for row in cursor.fetchall():
                avg = row[2] / row[4] if row[4] > 0 else 0
                results.append({
                    "day_name": row[0],
                    "total": row[2],
                    "count": row[3],
                    "days_with_spending": row[4],
                    "avg_per_day": avg
                })
            
            return results
    
    def get_today_day_name(self) -> str:
        """Возвращает название текущего дня недели"""
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        return days[datetime.now().weekday()]
    
    def get_category_year_estimate(self, user_id: int, category: str) -> Dict:
        """Оценивает траты по категории за год на основе текущих данных"""
        with sqlite3.connect(self.db_path) as conn:
            # Считаем средние траты по категории в неделю
            week_ago = datetime.now() - timedelta(days=7)
            cursor = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND category = ? AND created_at > ?""",
                (user_id, category, week_ago)
            )
            week_total = cursor.fetchone()[0]
            
            # Также смотрим за всё время для более точной оценки
            cursor = conn.execute(
                """SELECT 
                    COALESCE(SUM(amount), 0),
                    MIN(created_at),
                    MAX(created_at)
                   FROM transactions
                   WHERE user_id = ? AND category = ?""",
                (user_id, category)
            )
            row = cursor.fetchone()
            total_all = row[0]
            
            if row[1] and row[2]:
                first_date = datetime.strptime(row[1][:10], "%Y-%m-%d")
                last_date = datetime.strptime(row[2][:10], "%Y-%m-%d")
                days_span = (last_date - first_date).days
                if days_span > 0:
                    daily_avg = total_all / days_span
                    year_estimate = daily_avg * 365
                else:
                    year_estimate = week_total * 52
            else:
                year_estimate = week_total * 52
            
            return {
                "week_total": week_total,
                "year_estimate": year_estimate
            }
    
    def get_top_categories_month(self, user_id: int) -> List[Dict]:
        """Топ категорий за месяц"""
        month_ago = datetime.now() - timedelta(days=30)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT category, SUM(amount) as total, COUNT(*) as count
                   FROM transactions
                   WHERE user_id = ? AND created_at > ?
                   GROUP BY category
                   ORDER BY total DESC
                   LIMIT 5""",
                (user_id, month_ago)
            )
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "category": row[0],
                    "total": row[1],
                    "count": row[2]
                })
            return results
    
    def get_users_with_morning_alert(self) -> List[int]:
        """Возвращает список user_id пользователей с включенными утренними уведомлениями"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, telegram_id FROM users WHERE morning_alert_enabled = 1"
            )
            return cursor.fetchall()
    
    def get_user_by_id(self, user_id: int) -> Dict:
        """Получает данные пользователя по internal id"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, telegram_id, daily_limit, goal_amount, goal_deadline FROM users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "telegram_id": row[1],
                    "daily_limit": row[2],
                    "goal_amount": row[3],
                    "goal_deadline": row[4]
                }
            return None
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Получает данные пользователя по telegram_id"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, telegram_id, daily_limit, goal_amount, goal_deadline FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "telegram_id": row[1],
                    "daily_limit": row[2],
                    "goal_amount": row[3],
                    "goal_deadline": row[4]
                }
            return None