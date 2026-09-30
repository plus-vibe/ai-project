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