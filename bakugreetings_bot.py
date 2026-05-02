import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import json
import os
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

class StatsManager:
    """Менеджер статистики, хранящий данные в JSON файле"""
    
    def __init__(self, stats_file: str = "greeting_stats.json"):
        self.stats_file = stats_file
        self.stats = self.load_stats()
        # Структура: {chat_id: {user_id: {"username": str, "count": int, "targets": {target: count}}}}
    
    def load_stats(self) -> Dict:
        """Загрузка статистики из файла"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                logger.error("Ошибка загрузки статистики, создаю новую")
                return {}
        return {}
    
    def save_stats(self):
        """Сохранение статистики в файл"""
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
    
    def add_greeting(self, chat_id: int, user_id: int, username: str, target: str):
        """Добавление приветствия в статистику"""
        chat_id = str(chat_id)
        user_id = str(user_id)
        
        # Инициализируем структуру для чата
        if chat_id not in self.stats:
            self.stats[chat_id] = {}
        
        # Инициализируем структуру для пользователя
        if user_id not in self.stats[chat_id]:
            self.stats[chat_id][user_id] = {
                "username": username,
                "count": 0,
                "targets": {}
            }
        
        # Обновляем статистику
        self.stats[chat_id][user_id]["username"] = username  # обновляем username
        self.stats[chat_id][user_id]["count"] += 1
        
        # Добавляем цель приветствия
        target_key = target if target else "всех"
        if target_key not in self.stats[chat_id][user_id]["targets"]:
            self.stats[chat_id][user_id]["targets"][target_key] = 0
        self.stats[chat_id][user_id]["targets"][target_key] += 1
        
        # Сохраняем изменения
        self.save_stats()
    
    def get_stats_by_period(self, chat_id: int, period_hours: int = None) -> List[Tuple]:
        """Получение отсортированной статистики за период (часы)"""
        chat_id = str(chat_id)
        
        if chat_id not in self.stats:
            return []
        
        stats_list = []
        for user_id, user_data in self.stats[chat_id].items():
            count = user_data["count"]
            username = user_data["username"]
            stats_list.append((int(user_id), username, count))
        
        # Сортируем по убыванию количества
        stats_list.sort(key=lambda x: x[2], reverse=True)
        
        # Если указан период, возвращаем все равно все (для простоты)
        # В реальном приложении нужно хранить timestamp каждого приветствия
        return stats_list
    
    def get_user_stats(self, chat_id: int, username: str) -> Optional[Dict]:
        """Получение статистики конкретного пользователя"""
        chat_id = str(chat_id)
        
        if chat_id not in self.stats:
            return None
        
        # Ищем пользователя по username
        for user_id, user_data in self.stats[chat_id].items():
            if user_data["username"].lower() == username.lower():
                return {
                    "username": user_data["username"],
                    "count": user_data["count"],
                    "targets": user_data["targets"]
                }
        
        return None
    
    def get_popular_targets(self, chat_id: int, limit: int = 20) -> List[Tuple]:
        """Получение популярных целей приветствий"""
        chat_id = str(chat_id)
        
        if chat_id not in self.stats:
            return []
        
        targets_count = defaultdict(int)
        
        for user_id, user_data in self.stats[chat_id].items():
            for target, count in user_data["targets"].items():
                targets_count[target] += count
        
        # Сортируем по убыванию
        sorted_targets = sorted(targets_count.items(), key=lambda x: x[1], reverse=True)
        return sorted_targets[:limit]
    
    def get_total_stats(self, chat_id: int) -> Dict:
        """Получение общей статистики чата"""
        chat_id = str(chat_id)
        
        if chat_id not in self.stats:
            return {"total_greetings": 0, "total_users": 0}
        
        total_greetings = sum(user_data["count"] for user_data in self.stats[chat_id].values())
        total_users = len(self.stats[chat_id])
        
        return {
            "total_greetings": total_greetings,
            "total_users": total_users
        }
    
    def wipe_chat_stats(self, chat_id: int):
        """Очистка статистики чата"""
        chat_id = str(chat_id)
        
        if chat_id in self.stats:
            del self.stats[chat_id]
            self.save_stats()
            return True
        return False


class GreetingBot:
    """Основной класс бота"""
    
    def __init__(self, stats_file: str = "greeting_stats.json"):
        self.stats_manager = StatsManager(stats_file)
        self.pattern = re.compile(r"^/7PUBET(\S*)$", re.IGNORECASE)
        self.user_message_times = defaultdict(list)
        self.muted_until = {}
    
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
            
            # Сохраняем приветствие в статистику
            username = user.username or user.first_name
            self.stats_manager.add_greeting(chat_id, user_id, username, greeting_target)
            
            # Отправляем подтверждение
            username_mention = f"@{user.username}" if user.username else user.first_name
            
            if greeting_target:
                response = f"✅ {username_mention} поприветствовал(а) {greeting_target}!{warning}"
            else:
                response = f"✅ {username_mention} поприветствовал(а) всех!{warning}"
            
            await update.message.reply_text(response)
            logger.info(f"Greeting recorded: {user_id} -> {greeting_target}")
    
    async def stats_day(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за день"""
        chat_id = update.effective_chat.id
        stats = self.stats_manager.get_stats_by_period(chat_id)
        await self._send_stats(update, stats, "📊 Статистика приветов:")
    
    async def stats_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за неделю"""
        chat_id = update.effective_chat.id
        stats = self.stats_manager.get_stats_by_period(chat_id)
        await self._send_stats(update, stats, "📊 Статистика приветов:")
    
    async def stats_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за месяц"""
        chat_id = update.effective_chat.id
        stats = self.stats_manager.get_stats_by_period(chat_id)
        await self._send_stats(update, stats, "📊 Статистика приветов:")
    
    async def stats_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика за всё время"""
        chat_id = update.effective_chat.id
        stats = self.stats_manager.get_stats_by_period(chat_id)
        await self._send_stats(update, stats, "📊 Общая статистика приветов:")
    
    async def stats_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика конкретного пользователя"""
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите пользователя!\nПример: /stats_user username"
            )
            return
        
        target_username = context.args[0].replace('@', '')
        user_stats = self.stats_manager.get_user_stats(chat_id, target_username)
        
        if not user_stats:
            await update.message.reply_text(
                f"❌ Пользователь {target_username} не найден в статистике!"
            )
            return
        
        message = f"📊 Статистика приветствий для {user_stats['username']}:\n\n"
        message += f"📅 Всего приветов: {user_stats['count']}\n"
        
        if user_stats['targets']:
            message += "\n👥 Кого приветствовал:\n"
            sorted_targets = sorted(user_stats['targets'].items(), key=lambda x: x[1], reverse=True)
            for target, count in sorted_targets[:10]:
                message += f"  • {target}: {count} раз(а)\n"
        
        await update.message.reply_text(message)
    
    async def stats_names(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика популярных имен/целей приветствий"""
        chat_id = update.effective_chat.id
        popular_targets = self.stats_manager.get_popular_targets(chat_id)
        
        if not popular_targets:
            await update.message.reply_text("❌ Пока нет данных о приветствиях!")
            return
        
        message = "🏆 Топ приветствуемых:\n\n"
        
        for i, (target, count) in enumerate(popular_targets, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            message += f"{medal} {target}: {count} раз(а)\n"
        
        await update.message.reply_text(message)
    
    async def wipe_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка статистики (только для владельца чата)"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Проверяем, является ли пользователь владельцем чата
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        
        if chat_member.status not in ['creator', 'administrator']:
            await update.message.reply_text(
                "❌ Только владелец или администратор чата может очистить статистику!"
            )
            return
        
        # Запрашиваем подтверждение
        if not context.args or context.args[0].lower() != 'confirm':
            await update.message.reply_text(
                "⚠️ Вы уверены, что хотите удалить ВСЮ статистику чата?\n"
                "Для подтверждения используйте: /wipe_stats confirm"
            )
            return
        
        # Очищаем статистику
        if self.stats_manager.wipe_chat_stats(chat_id):
            await update.message.reply_text("✅ Статистика чата успешно очищена!")
            logger.info(f"Stats wiped for chat {chat_id} by user {user_id}")
        else:
            await update.message.reply_text("ℹ️ Статистика уже была пуста.")
    
    async def _send_stats(self, update: Update, stats: List[Tuple], title: str):
        """Отправка статистики"""
        if not stats:
            await update.message.reply_text(f"{title}\n\n❌ Нет данных!")
            return
        
        message = f"{title}\n\n"
        total = sum(count for _, _, count in stats)
        
        for i, (user_id, username, count) in enumerate(stats, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            percentage = (count / total) * 100 if total > 0 else 0
            message += f"{medal} {username}: {count} приветов ({percentage:.1f}%)\n"
        
        message += f"\n📈 Всего приветов: {total}"
        await update.message.reply_text(message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь по командам"""
        help_text = """
🤖 Бот для подсчёта приветствий

**Как использовать:**
Отправьте сообщение, начинающееся с `/7PUBET` (регистр не важен):
• `/7PUBET` - поприветствовать всех
• `/7PUBETИмя` - поприветствовать конкретного человека/предмет

**Команды статистики:**
• `/stats_all` - общая статистика
• `/stats_user username` - статистика пользователя
• `/stats_names` - популярные цели приветствий
• `/wipe_stats` - очистить статистику (только для админов)

**Анти-спам:**
При более 10 сообщений `/7PUBET` за минуту выдаётся мут на 1 минуту.
Предупреждения начинаются за 3 сообщения до мута.

**Для администраторов:**
• `/wipe_stats confirm` - полная очистка статистики чата

**Примеры:**
`/7PUBET` - просто привет
`/7PUBETВася` - привет Васе
`/7PUBET6AKYBAT` - привет бакубату 😄
"""
        await update.message.reply_text(help_text)
    
    def run(self, token: str):
        """Запуск бота"""
        application = Application.builder().token(token).build()
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("stats_all", self.stats_all))
        application.add_handler(CommandHandler("stats_user", self.stats_user))
        application.add_handler(CommandHandler("stats_names", self.stats_names))
        application.add_handler(CommandHandler("wipe_stats", self.wipe_stats))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("start", self.help_command))
        
        # Создаем фильтр для сообщений /7PUBET
        class GreetingFilter(filters.MessageFilter):
            def filter(self, message):
                if message.text:
                    return bool(re.match(r'^/7PUBET', message.text, re.IGNORECASE))
                return False
        
        application.add_handler(MessageHandler(GreetingFilter(), self.handle_message))
        
        print("🤖 Бот для подсчёта приветствий запущен!")
        print("📋 Доступные команды:")
        print("  /stats_all - общая статистика")
        print("  /stats_user username - статистика пользователя")
        print("  /stats_names - популярные цели приветствий")
        print("  /wipe_stats - очистить статистику (админы)")
        print("  /help - помощь")
        print("\n📝 Отправьте /7PUBET или /7PUBETИмя чтобы поприветствовать!")
        print("💾 Статистика сохраняется в файл greeting_stats.json")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    import os
    
    BOT_TOKEN = os.environ.get('BOT_TOKEN', '8701010609:AAFF4Ju4znaBvGki7HoItqPd55H8AE_wSVY')
    
    bot = GreetingBot()
    bot.run(BOT_TOKEN)