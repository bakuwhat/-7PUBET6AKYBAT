import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import sys

# Для PythonAnywhere
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    # Создаем лог-файл
    import logging
    logging.basicConfig(
        filename='/home/yourusername/bot.log',
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Greeting:
    """Класс для хранения информации о приветствии"""
    def __init__(self, user_id: int, username: str, chat_id: int, greeting_target: str, timestamp: datetime):
        self.user_id = user_id
        self.username = username
        self.chat_id = chat_id
        self.greeting_target = greeting_target
        self.timestamp = timestamp

class GreetingDatabase:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = "greetings.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица приветствий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS greetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    greeting_target TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для быстрого поиска
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_timestamp 
                ON greetings(user_id, timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON greetings(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_greeting_target 
                ON greetings(greeting_target)
            ''')
            
            conn.commit()
    
    def add_greeting(self, greeting: Greeting):
        """Добавить приветствие в базу"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO greetings (user_id, username, chat_id, greeting_target, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                greeting.user_id,
                greeting.username,
                greeting.chat_id,
                greeting.greeting_target,
                greeting.timestamp
            ))
            conn.commit()
    
    def get_stats_by_period(self, chat_id: int, period_start: datetime, period_end: datetime = None) -> List[Tuple]:
        """Получить статистику за период"""
        if period_end is None:
            period_end = datetime.now()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, COUNT(*) as count
                FROM greetings
                WHERE chat_id = ? 
                AND timestamp BETWEEN ? AND ?
                GROUP BY user_id, username
                ORDER BY count DESC
            ''', (chat_id, period_start, period_end))
            return cursor.fetchall()
    
    def get_user_stats(self, chat_id: int, user_id: int) -> Dict:
        """Получить полную статистику пользователя"""
        now = datetime.now()
        
        periods = {
            'day': now - timedelta(days=1),
            'week': now - timedelta(weeks=1),
            'month': now - timedelta(days=30),
            'all': datetime(2020, 1, 1)
        }
        
        stats = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for period_name, period_start in periods.items():
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM greetings
                    WHERE chat_id = ? AND user_id = ? AND timestamp >= ?
                ''', (chat_id, user_id, period_start))
                stats[f'count_{period_name}'] = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT greeting_target, COUNT(*) as count
                FROM greetings
                WHERE chat_id = ? AND user_id = ? AND greeting_target != ''
                GROUP BY greeting_target
                ORDER BY count DESC
                LIMIT 20
            ''', (chat_id, user_id))
            stats['targets'] = cursor.fetchall()
        
        return stats
    
    def get_popular_targets(self, chat_id: int, limit: int = 20) -> List[Tuple]:
        """Получить популярные цели приветствий"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT greeting_target, COUNT(*) as count
                FROM greetings
                WHERE chat_id = ? AND greeting_target != ''
                GROUP BY greeting_target
                ORDER BY count DESC
                LIMIT ?
            ''', (chat_id, limit))
            return cursor.fetchall()

class GreetingBot:
    """Основной класс бота"""
    
    def __init__(self, db_path: str = "greetings.db"):
        self.db = GreetingDatabase(db_path)
        # Исправленное регулярное выражение
        self.pattern = re.compile(r'^/7PUBET(\S*)$', re.IGNORECASE)
        self.last_greetings = {}  # Для анти-спама
    
    def extract_greeting(self, text: str) -> Optional[str]:
        """Извлечь цель приветствия из сообщения"""
        match = self.pattern.match(text.strip())
        if match:
            target = match.group(1)
            return target if target else ""
        return None
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений"""
        if not update.message or not update.message.text:
            return
        
        text = update.message.text.strip()
        greeting_target = self.extract_greeting(text)
        
        if greeting_target is not None:
            user = update.effective_user
            chat_id = update.effective_chat.id
            
            # Анти-спам: не чаще одного приветствия в 3 секунды
            user_id = user.id
            current_time = datetime.now()
            
            if user_id in self.last_greetings:
                time_diff = (current_time - self.last_greetings[user_id]).total_seconds()
                if time_diff < 3:
                    await update.message.reply_text("⏳ Слишком часто! Подождите немного.")
                    return
            
            self.last_greetings[user_id] = current_time
            
            # Создаем объект приветствия
            greeting = Greeting(
                user_id=user.id,
                username=user.username or user.first_name,
                chat_id=chat_id,
                greeting_target=greeting_target,
                timestamp=current_time
            )
            
            # Сохраняем в базу
            self.db.add_greeting(greeting)
            
            # Отправляем подтверждение
            username_mention = f"@{user.username}" if user.username else user.first_name
            
            if greeting_target:
                response = f"✅ {username_mention} поприветствовал(а) {greeting_target}!"
            else:
                response = f"✅ {username_mention} поприветствовал(а) всех!"
            
            await update.message.reply_text(response)
            logger.info(f"Greeting recorded: {user.id} -> {greeting_target}")
    
    async def stats_day(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за день"""
        chat_id = update.effective_chat.id
        period_start = datetime.now() - timedelta(days=1)
        
        stats = self.db.get_stats_by_period(chat_id, period_start)
        await self._send_stats(update, stats, "📊 Статистика приветов за день:")
    
    async def stats_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за неделю"""
        chat_id = update.effective_chat.id
        period_start = datetime.now() - timedelta(weeks=1)
        
        stats = self.db.get_stats_by_period(chat_id, period_start)
        await self._send_stats(update, stats, "📊 Статистика приветов за неделю:")
    
    async def stats_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за месяц"""
        chat_id = update.effective_chat.id
        period_start = datetime.now() - timedelta(days=30)
        
        stats = self.db.get_stats_by_period(chat_id, period_start)
        await self._send_stats(update, stats, "📊 Статистика приветов за месяц:")
    
    async def stats_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за всё время"""
        chat_id = update.effective_chat.id
        period_start = datetime(2020, 1, 1)
        
        stats = self.db.get_stats_by_period(chat_id, period_start)
        await self._send_stats(update, stats, "📊 Общая статистика приветов:")
    
    async def stats_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика конкретного пользователя"""
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите пользователя!\n"
                "Пример: /stats_user @username"
            )
            return
        
        target_username = context.args[0].replace('@', '')
        target_user = None
        
        # Ищем пользователя в базе
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT user_id, username 
                FROM greetings 
                WHERE chat_id = ? AND LOWER(username) = LOWER(?)
                LIMIT 1
            ''', (chat_id, target_username))
            result = cursor.fetchone()
            
            if result:
                target_user = {'id': result[0], 'username': result[1]}
        
        if not target_user:
            await update.message.reply_text(f"❌ Пользователь {target_username} не найден в базе приветствий!")
            return
        
        stats = self.db.get_user_stats(chat_id, target_user['id'])
        
        message = f"📊 Статистика приветствий для @{target_user['username']}:\n\n"
        message += f"📅 За день: {stats['count_day']}\n"
        message += f"📅 За неделю: {stats['count_week']}\n"
        message += f"📅 За месяц: {stats['count_month']}\n"
        message += f"📅 За всё время: {stats['count_all']}\n"
        
        if stats['targets']:
            message += "\n👥 Кого приветствовал:\n"
            for target, count in stats['targets'][:10]:
                if target:
                    message += f"  • {target}: {count} раз(а)\n"
                else:
                    message += f"  • Всех: {count} раз(а)\n"
        
        await update.message.reply_text(message)
    
    async def stats_names(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика популярных имен/целей приветствий"""
        chat_id = update.effective_chat.id
        
        popular_targets = self.db.get_popular_targets(chat_id)
        
        if not popular_targets:
            await update.message.reply_text("❌ Пока нет данных о приветствиях конкретных целей!")
            return
        
        message = "🏆 Топ приветствуемых:\n\n"
        
        for i, (target, count) in enumerate(popular_targets, 1):
            if target:
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                message += f"{medal} {target}: {count} раз(а)\n"
            else:
                message += f"{i}. Всех: {count} раз(а)\n"
        
        await update.message.reply_text(message)
    
    async def _send_stats(self, update: Update, stats: List[Tuple], title: str):
        """Отправка статистики"""
        if not stats:
            await update.message.reply_text(f"{title}\n\n❌ Нет данных за этот период!")
            return
        
        message = f"{title}\n\n"
        total = sum(count for _, _, count in stats)
        
        for i, (user_id, username, count) in enumerate(stats, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            percentage = (count / total) * 100 if total > 0 else 0
            message += f"{medal} @{username}: {count} приветов ({percentage:.1f}%)\n"
        
        message += f"\n📈 Всего приветов: {total}"
        
        await update.message.reply_text(message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь по командам"""
        help_text = """
🤖 Бот для подсчёта приветствий

**Как использовать:**
Отправьте сообщение, начинающееся с `/7PUBET` (регистр не важен):
• `/7PUBET` - поприветствовать всех
• `/7PUBETИмя` - поприветствовать конкретного человека

**Команды статистики:**
• `/stats_day` - статистика за день
• `/stats_week` - статистика за неделю  
• `/stats_month` - статистика за месяц
• `/stats_all` - общая статистика
• `/stats_user @username` - статистика пользователя
• `/stats_names` - популярные цели приветствий
• `/help` - это сообщение
"""
        await update.message.reply_text(help_text)
    
    def run(self, token: str):
        """Запуск бота"""
        application = Application.builder().token(token).build()
        
        # Регистрируем обработчики команд статистики
        application.add_handler(CommandHandler("stats_day", self.stats_day))
        application.add_handler(CommandHandler("stats_week", self.stats_week))
        application.add_handler(CommandHandler("stats_month", self.stats_month))
        application.add_handler(CommandHandler("stats_all", self.stats_all))
        application.add_handler(CommandHandler("stats_user", self.stats_user))
        application.add_handler(CommandHandler("stats_names", self.stats_names))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("start", self.help_command))
        
        # Исправленный обработчик для сообщений с /7PUBET
        # Используем filters.Regex с одним аргументом
        greeting_filter = filters.Regex(re.compile(r'^/7PUBET', re.IGNORECASE))
        application.add_handler(MessageHandler(greeting_filter, self.handle_message))
        
        # Обработчик для всех остальных текстовых сообщений (не команд)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~greeting_filter, 
            self.handle_message
        ))
        
        print("🤖 Бот для подсчёта приветствий запущен!")
        print("📋 Доступные команды:")
        print("  /stats_day - статистика за день")
        print("  /stats_week - статистика за неделю")
        print("  /stats_month - статистика за месяц")
        print("  /stats_all - общая статистика")
        print("  /stats_user @username - статистика пользователя")
        print("  /stats_names - популярные цели приветствий")
        print("  /help - помощь")
        print("\n📝 Отправьте /7PUBET или /7PUBETИмя чтобы поприветствовать!")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)

# В конец файла, перед if __name__ == '__main__':
import os
from flask import Flask
import threading

# Создаем веб-сервер для Render (требуется для бесплатного тарифа)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Запускаем бота
    bot = GreetingBot()
    bot.run(BOT_TOKEN)

if __name__ == '__main__':
    # Замените на токен вашего бота
    BOT_TOKEN = "8701010609:AAFF4Ju4znaBvGki7HoItqPd55H8AE_wSVY"
    
    bot = GreetingBot()
    bot.run(BOT_TOKEN)