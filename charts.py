import matplotlib
matplotlib.use('Agg')  # Важно: без GUI, для сервера
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import sqlite3
import io

# Настройка шрифтов для корректного отображения кириллицы
def setup_russian_font():
    fonts_to_try = ['Segoe UI', 'Arial', 'DejaVu Sans', 'Liberation Sans', 'Roboto']
    from matplotlib import font_manager
    available_fonts = [f.name for f in font_manager.fontManager.ttflist]
    
    for font in fonts_to_try:
        if font in available_fonts:
            plt.rcParams['font.family'] = font
            return

setup_russian_font()

# Красивая цветовая палитра (без эмодзи в коде, чтобы не ломать шрифты)
COLORS = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE']


class ChartGenerator:
    def __init__(self, db_path: str = "wallet.db"):
        self.db_path = db_path
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def generate_pie_chart(self, user_id: int, days: int = 7) -> io.BytesIO:
        """Круговая диаграмма: распределение по категориям"""
        since = datetime.now() - timedelta(days=days)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT category, SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ? AND created_at > ?
                   GROUP BY category
                   ORDER BY total DESC""",
                (user_id, since)
            )
            rows = cursor.fetchall()
        
        if not rows:
            return None
        
        categories = [row[0] for row in rows]
        amounts = [row[1] for row in rows]
        total = sum(amounts)
        
        # УБРАЛИ эмодзи из подписей, чтобы matplotlib не ругался
        labels = [f"{cat}\n{amt:.0f}₽ ({amt/total*100:.0f}%)" 
                  for cat, amt in zip(categories, amounts)]
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        wedges, texts = ax.pie(
            amounts,
            labels=labels,
            colors=COLORS[:len(categories)],
            startangle=90,
            wedgeprops=dict(width=0.7, edgecolor='white', linewidth=2)
        )
        
        # Центральная надпись (текстом, без эмодзи)
        ax.text(0, 0, f'ВСЕГО\n{total:.0f}₽', 
                ha='center', va='center', 
                fontsize=20, fontweight='bold')
        
        period_text = "неделю" if days == 7 else f"{days} дней"
        ax.set_title(f'Распределение трат за {period_text}', 
                     fontsize=16, fontweight='bold', pad=20)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', 
                    facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        
        return buf
    
    def generate_daily_chart(self, user_id: int, days: int = 7) -> io.BytesIO:
        """Столбчатая диаграмма: траты по дням"""
        since = datetime.now() - timedelta(days=days)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT DATE(created_at) as day, SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ? AND created_at > ?
                   GROUP BY DATE(created_at)
                   ORDER BY day""",
                (user_id, since)
            )
            rows = cursor.fetchall()
        
        if not rows:
            return None
        
        days_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        dates, amounts, day_labels = [], [], []
        
        for row in rows:
            date = datetime.strptime(row[0], "%Y-%m-%d")
            dates.append(date)
            amounts.append(row[1])
            day_labels.append(f"{days_names[date.weekday()]}\n{date.strftime('%d.%m')}")
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(range(len(dates)), amounts, color=COLORS[1], edgecolor='white', linewidth=1.5, width=0.6)
        
        for bar, amount in zip(bars, amounts):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(amounts) * 0.02,
                    f'{amount:.0f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        ax.set_xticks(range(len(dates)))
        ax.set_xticklabels(day_labels, fontsize=10)
        ax.set_ylabel('Сумма (₽)', fontsize=12)
        
        avg = sum(amounts) / len(amounts)
        ax.axhline(y=avg, color='red', linestyle='--', linewidth=2, alpha=0.7)
        ax.text(len(dates) - 1, avg, f'Среднее: {avg:.0f}', ha='right', va='bottom', color='red', fontsize=10, fontweight='bold')
        
        period_text = "неделю" if days == 7 else f"{days} дней"
        ax.set_title(f'Траты по дням за {period_text}', fontsize=16, fontweight='bold', pad=15)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf
    
    def generate_comparison_chart(self, user_id: int) -> io.BytesIO:
        """Сравнение этой и прошлой недели"""
        now = datetime.now()
        this_week_start = now - timedelta(days=7)
        last_week_start = now - timedelta(days=14)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT category, SUM(amount) FROM transactions
                   WHERE user_id = ? AND created_at > ? GROUP BY category""",
                (user_id, this_week_start)
            )
            this_week = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor = conn.execute(
                """SELECT category, SUM(amount) FROM transactions
                   WHERE user_id = ? AND created_at > ? AND created_at <= ? GROUP BY category""",
                (user_id, last_week_start, this_week_start)
            )
            last_week = {row[0]: row[1] for row in cursor.fetchall()}
        
        if not this_week and not last_week:
            return None
        
        all_categories = sorted(set(list(this_week.keys()) + list(last_week.keys())))
        labels = all_categories # Без эмодзи
        this_week_values = [this_week.get(cat, 0) for cat in all_categories]
        last_week_values = [last_week.get(cat, 0) for cat in all_categories]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        x = range(len(all_categories))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], last_week_values, width, label='Прошлая неделя', color=COLORS[2], alpha=0.8)
        ax.bar([i + width/2 for i in x], this_week_values, width, label='Эта неделя', color=COLORS[0], alpha=0.8)
        
        ax.set_ylabel('Сумма (₽)', fontsize=12)
        ax.set_title('Сравнение недель', fontsize=16, fontweight='bold', pad=15)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11)
        ax.legend(fontsize=11, loc='upper right')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
        buf.seek(0)
        plt.close(fig)
        return buf