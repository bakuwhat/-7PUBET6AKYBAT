import re
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sqlite3
from collections import defaultdict
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Старая статистика для восстановления (username: count)
OLD_STATS = {
    "actrightnm4": 284,
    "Zhmoteyka": 152,
    "Zhmoteyka123": 133,
    "TroilTag": 101,
    "Fantolla1": 100,
    "gupiaboba": 68,
    "Bambusya1404": 50,
    "osuenjoyer": 34,
    "kr1toff": 40,
    "s11nam0ta": 24,
    "nahhx": 14,
    "Lenny192": 12,
    "D4star": 12,
    "Олег": 16,
    "batonchekki": 9,
    "krawsw": 7,
    "wemakeitunited": 7,
    "goth_sera": 7,
    "Channel_Bot": 2,
    "bakuwhat": 4,
    "kashirintimofey": 2,
    "Yanekoka": 4,
    "fearitf": 1,
    "ugglllyyyy": 1,
    "apofjadpofszklfviaojfawfpoikafjg": 1,
    "patchouler": 3,
    "JailFish": 1,
    "thevupsenn": 1,
    "henrilhimmler": 4,
    "harusssssss": 1,
    "aleshadunai": 1,
}


class Greeting:
    """Класс для хранения информации о приветствии"""

    def __init__(
        self,
        user_id: int,
        username: str,
        chat_id: int,
        greeting_target: str,
        timestamp: datetime,
    ):
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
        """Инициализация базы данных с авто-миграцией"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Создаем таблицу, если её нет
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
            
            # Проверяем существующие колонки
            cursor.execute("PRAGMA table_info(greetings)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Добавляем is_imported, если его нет
            if 'is_imported' not in columns:
                print("🔧 Добавление колонки is_imported...")
                cursor.execute('ALTER TABLE greetings ADD COLUMN is_imported INTEGER DEFAULT 0')
            
            # Создаем все нужные индексы
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_user_timestamp ON greetings(user_id, timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON greetings(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_greeting_target ON greetings(greeting_target)",
                "CREATE INDEX IF NOT EXISTS idx_imported ON greetings(is_imported)"
            ]
            
            for index_query in indexes:
                cursor.execute(index_query)
            
            conn.commit()
            print("✅ База данных готова к работе")

    def import_old_stats(self, chat_id: int):
        """Импорт старой статистики в БД (выполняется один раз)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Проверяем, не импортировали ли уже
            cursor.execute("SELECT COUNT(*) FROM greetings WHERE is_imported = 1")
            already_imported = cursor.fetchone()[0]
            if already_imported > 0:
                print(f"ℹ️ Старая статистика уже импортирована ({already_imported} записей)")
                return False

            print("📥 Импорт старой статистики...")
            imported = 0
            for username, count in OLD_STATS.items():
                for _ in range(count):
                    cursor.execute('''
                        INSERT INTO greetings (user_id, username, chat_id, greeting_target, timestamp, is_imported)
                        VALUES (?, ?, ?, ?, ?, 1)
                    ''', (0, username, chat_id, "", datetime(2024, 1, 1, 0, 0, 0)))
                    imported += 1

            conn.commit()
            print(f"✅ Импортировано {imported} записей старой статистики")
            return True

    def add_greeting(self, greeting: Greeting):
        """Добавление нового приветствия"""
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
    def __init__(self, db_path: str = "greetings.db", chat_id: int = None):
        self.db = GreetingDatabase(db_path)
        self.pattern = re.compile(r"^/7PUBET(\S*)$", re.IGNORECASE)
        self.user_message_times = defaultdict(list)
        self.muted_until = {}

        # Если указан chat_id, восстанавливаем старую статистику
        if chat_id:
            print("🔍 Проверка старой статистики...")
            self.db.import_old_stats(chat_id)

    def extract_greeting(self, text: str) -> Optional[str]:
        match = self.pattern.match(text.strip())
        if match:
            target = match.group(1)
            return target if target else ""
        return None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        greeting_target = self.extract_greeting(text)

        if greeting_target is not None:
            user = update.effective_user
            chat_id = update.effective_chat.id
            user_id = user.id
            now = datetime.now()
            current_timestamp = now.timestamp()

            # Проверка мута
            if user_id in self.muted_until:
                if now < self.muted_until[user_id]:
                    remaining = (self.muted_until[user_id] - now).seconds
                    await update.message.reply_text(
                        f"🚫 Вы замучены за спам! Осталось {remaining} секунд."
                    )
                    return
                else:
                    del self.muted_until[user_id]

            # Обновляем историю сообщений пользователя (за последние 60 секунд)
            cutoff = current_timestamp - 60
            user_times = self.user_message_times[user_id]
            user_times = [t for t in user_times if t > cutoff]
            user_times.append(current_timestamp)
            self.user_message_times[user_id] = user_times

            total_after = len(user_times)

            # 11-е сообщение за минуту -> мут
            if total_after > 10:
                self.muted_until[user_id] = now + timedelta(minutes=1)
                del self.user_message_times[user_id]
                await update.message.reply_text(
                    "🚫 Вы получили мут на 1 минуту за спам!"
                )
                return

            # Предупреждения (с 8-го по 10-е сообщение)
            warning = ""
            if 8 <= total_after <= 10:
                remaining_messages = 11 - total_after
                warning = f" ⚠️ Осталось {remaining_messages} сообщ. до мута!"

            # Записываем приветствие в БД
            greeting = Greeting(
                user_id=user.id,
                username=user.username or user.first_name,
                chat_id=chat_id,
                greeting_target=greeting_target,
                timestamp=now,
            )
            self.db.add_greeting(greeting)

            username_mention = (
                f"@{user.username}" if user.username else user.first_name
            )
            if greeting_target:
                response = f"✅ {username_mention} поприветствовал(а) {greeting_target}!{warning}"
            else:
                response = f"✅ {username_mention} поприветствовал(а) всех!{warning}"

            await update.message.reply_text(response)
            logger.info(
                f"Greeting recorded: {user.id} -> {greeting_target} | count: {total_after}"
            )

    # Статистика (исправлено: username без @)
    async def stats_day(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        stats = self.db.get_stats_by_period(
            chat_id, datetime.now() - timedelta(days=1)
        )
        await self._send_stats(update, stats, "📊 Статистика приветов за день:")

    async def stats_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        stats = self.db.get_stats_by_period(
            chat_id, datetime.now() - timedelta(weeks=1)
        )
        await self._send_stats(update, stats, "📊 Статистика приветов за неделю:")

    async def stats_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        stats = self.db.get_stats_by_period(
            chat_id, datetime.now() - timedelta(days=30)
        )
        await self._send_stats(update, stats, "📊 Статистика приветов за месяц:")

    async def stats_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        stats = self.db.get_stats_by_period(chat_id, datetime(2020, 1, 1))
        await self._send_stats(update, stats, "📊 Общая статистика приветов:")

    async def stats_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите пользователя!\nПример: /stats_user @username"
            )
            return

        target_username = context.args[0].replace("@", "")
        target_user = None
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT user_id, username FROM greetings
                WHERE chat_id = ? AND LOWER(username) = LOWER(?)
                LIMIT 1
            """,
                (chat_id, target_username),
            )
            result = cursor.fetchone()
            if result:
                target_user = {"id": result[0], "username": result[1]}

        if not target_user:
            await update.message.reply_text(
                f"❌ Пользователь {target_username} не найден в базе приветствий!"
            )
            return

        stats = self.db.get_user_stats(chat_id, target_user["id"])
        # Убрали собачку перед именем
        message = f"📊 Статистика приветствий для {target_user['username']}:\n\n"
        message += f"📅 За день: {stats['count_day']}\n"
        message += f"📅 За неделю: {stats['count_week']}\n"
        message += f"📅 За месяц: {stats['count_month']}\n"
        message += f"📅 За всё время: {stats['count_all']}\n"

        if stats["targets"]:
            message += "\n👥 Кого приветствовал:\n"
            for target, count in stats["targets"][:10]:
                if target:
                    message += f"  • {target}: {count} раз(а)\n"
                else:
                    message += f"  • Всех: {count} раз(а)\n"

        await update.message.reply_text(message)

    async def stats_names(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        popular_targets = self.db.get_popular_targets(chat_id)
        if not popular_targets:
            await update.message.reply_text(
                "❌ Пока нет данных о приветствиях конкретных целей!"
            )
            return

        message = "🏆 Топ приветствуемых:\n\n"
        for i, (target, count) in enumerate(popular_targets, 1):
            medal = (
                "🥇"
                if i == 1
                else "🥈"
                if i == 2
                else "🥉"
                if i == 3
                else f"{i}."
            )
            if target:
                message += f"{medal} {target}: {count} раз(а)\n"
            else:
                message += f"{medal} Всех: {count} раз(а)\n"

        await update.message.reply_text(message)

    async def _send_stats(self, update: Update, stats: List[Tuple], title: str):
        if not stats:
            await update.message.reply_text(
                f"{title}\n\n❌ Нет данных за этот период!"
            )
            return

        message = f"{title}\n\n"
        total = sum(count for _, _, count in stats)

        for i, (user_id, username, count) in enumerate(stats, 1):
            medal = (
                "🥇"
                if i == 1
                else "🥈"
                if i == 2
                else "🥉"
                if i == 3
                else f"{i}."
            )
            percentage = (count / total) * 100 if total > 0 else 0
            # username без @
            message += f"{medal} {username}: {count} приветов ({percentage:.1f}%)\n"

        message += f"\n📈 Всего приветов: {total}"
        await update.message.reply_text(message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🤖 Бот для подсчёта приветствий

**Как использовать:**
Отправьте сообщение, начинающееся с `/7PUBET` (регистр не важен):
• `/7PUBET` - поприветствовать всех
• `/7PUBETИмя` - поприветствовать конкретного человека/предмет

**Команды статистики:**
• `/stats_day` - статистика за день
• `/stats_week` - статистика за неделю  
• `/stats_month` - статистика за месяц
• `/stats_all` - общая статистика
• `/stats_user @username` - статистика пользователя
• `/stats_names` - популярные цели приветствий
• `/help` - это сообщение

**Анти-спам:**
При более 10 сообщений `/7PUBET` за минуту выдаётся мут на 1 минуту.
Предупреждения начинаются за 3 сообщения до мута.
"""
        await update.message.reply_text(help_text)

    def run(self, token: str):
        application = Application.builder().token(token).build()

        application.add_handler(CommandHandler("stats_day", self.stats_day))
        application.add_handler(CommandHandler("stats_week", self.stats_week))
        application.add_handler(CommandHandler("stats_month", self.stats_month))
        application.add_handler(CommandHandler("stats_all", self.stats_all))
        application.add_handler(CommandHandler("stats_user", self.stats_user))
        application.add_handler(CommandHandler("stats_names", self.stats_names))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("start", self.help_command))

        class GreetingFilter(filters.MessageFilter):
            def filter(self, message):
                if message.text:
                    return bool(
                        re.match(r"^/7PUBET", message.text, re.IGNORECASE)
                    )
                return False

        application.add_handler(
            MessageHandler(GreetingFilter(), self.handle_message)
        )

        print("🤖 Бот для подсчёта приветствий запущен!")
        print("📋 Доступные команды:")
        print("  /stats_day, /stats_week, /stats_month, /stats_all")
        print("  /stats_user @username")
        print("  /stats_names")
        print("  /help")
        print("\n📝 Отправьте /7PUBET или /7PUBETИмя чтобы поприветствовать!")

        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import os
    import sys

    BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

    # ID чата (замените на реальный ID вашего чата)
    CHAT_ID = -1002611211879  # <-- ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ на ID вашего чата!

    # Если запущен с аргументом --import-stats, делаем импорт и выходим
    if "--import-stats" in sys.argv:
        db = GreetingDatabase()
        print(f"Импорт старой статистики для чата {CHAT_ID}...")
        db.import_old_stats(CHAT_ID)
        print("Готово. Теперь запускайте бота без этого флага.")
        sys.exit(0)

    bot = GreetingBot(chat_id=CHAT_ID)
    bot.run(BOT_TOKEN)