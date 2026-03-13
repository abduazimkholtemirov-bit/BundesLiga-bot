import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from collections import defaultdict
import re
import os
import threading
from flask import Flask

# ===== НАСТРОЙКИ =====
# Читаем токен из переменной окружения (должна быть задана на Render)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_TOKEN environment variable set")

# ⚠️ ЗАМЕНИ ЭТО ЧИСЛО НА СВОЙ TELEGRAM ID (узнай у @userinfobot)
ALLOWED_USER_ID = 783515622  # <--- ВСТАВЬ СВОЙ ID СЮДА

# Хранилище данных (в памяти) — при перезапуске данные теряются
user_tournaments = {}
user_team = {}

# ===== ФУНКЦИИ ДЛЯ LICHESS =====
def get_tournament_scores(tournament_id):
    url = f"https://lichess.org/api/tournament/{tournament_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Ошибка при запросе турнира {tournament_id}: {e}")
        return {}
    scores = {}
    standing = data.get('standing', {})
    for player in standing.get('players', []):
        name = player.get('name')
        score = player.get('score', 0)
        if name:
            scores[name] = score
    return scores

def aggregate_scores(tournament_ids):
    total = defaultdict(float)
    for tid in tournament_ids:
        scores = get_tournament_scores(tid)
        for player, score in scores.items():
            total[player] += score
    return total

def extract_tournament_id(text):
    match = re.search(r'lichess\.org/tournament/([a-zA-Z0-9]+)', text)
    if match:
        return match.group(1)
    return text.strip()

# ===== ПРОВЕРКА НА ВЛАДЕЛЬЦА =====
def is_allowed(user_id):
    return user_id == ALLOWED_USER_ID

# ===== ОБРАБОТЧИКИ КОМАНД =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /start доступен всем (без проверки)
    await update.message.reply_text(
        "Привет! Я помогаю подсчитывать очки игроков команды по турнирам Lichess.\n\n"
        "📊 **Команды:**\n"
        "/total — показать суммарные очки игроков команды (доступно всем)\n\n"
        "🔒 **Команды только для владельца:**\n"
        "/setteam ник1 ник2 ... — задать список игроков команды\n"
        "/add <ссылка или ID турнира> — добавить турнир\n"
        "/clear — очистить список турниров\n"
        "/clearteam — очистить список команды"
    )

async def set_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только для владельца
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён. Эта команда только для владельца.")
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Укажи ники игроков через пробел, например:\n/setteam ZEROO1391 Maksimligotnis")
        return
    team = context.args
    user_team[chat_id] = [nick.lower() for nick in team]
    await update.message.reply_text(f"✅ Команда сохранена: {', '.join(team)}")

async def add_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только для владельца
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён. Эта команда только для владельца.")
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Укажи ссылку или ID турнира, например:\n/add https://lichess.org/tournament/abc123")
        return
    raw_input = context.args[0]
    tournament_id = extract_tournament_id(raw_input)
    if chat_id not in user_tournaments:
        user_tournaments[chat_id] = []
    user_tournaments[chat_id].append(tournament_id)
    await update.message.reply_text(f"✅ Турнир {tournament_id} добавлен. Всего в списке: {len(user_tournaments[chat_id])}")

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Доступно ВСЕМ (без проверки)
    chat_id = update.effective_chat.id
    if chat_id not in user_tournaments or not user_tournaments[chat_id]:
        await update.message.reply_text("📭 Список турниров пуст. Владелец ещё не добавил турниры.")
        return
    if chat_id not in user_team or not user_team[chat_id]:
        await update.message.reply_text("👥 Список команды ещё не задан. Владелец должен выполнить /setteam")
        return
    await update.message.reply_text("🔄 Собираю данные с Lichess, это может занять несколько секунд...")
    scores = aggregate_scores(user_tournaments[chat_id])
    team_nicks = user_team[chat_id]
    team_scores = {p: s for p, s in scores.items() if p.lower() in team_nicks}
    if not team_scores:
        await update.message.reply_text("😕 Никто из игроков команды не найден в добавленных турнирах.")
        return
    sorted_scores = sorted(team_scores.items(), key=lambda x: x[1], reverse=True)
    lines = ["**📊 Суммарные очки игроков команды:**"]
    for player, total_score in sorted_scores:
        lines.append(f"• {player}: {total_score}")
    await update.message.reply_text("\n".join(lines))

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только для владельца
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.effective_chat.id
    if chat_id in user_tournaments:
        user_tournaments[chat_id] = []
    await update.message.reply_text("🗑 Список турниров очищен.")

async def clear_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Только для владельца
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.effective_chat.id
    if chat_id in user_team:
        del user_team[chat_id]
    await update.message.reply_text("🗑 Список команды очищен.")

# ===== ЗАПУСК БОТА В ФОНЕ =====
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setteam", set_team))
application.add_handler(CommandHandler("add", add_tournament))
application.add_handler(CommandHandler("total", total))
application.add_handler(CommandHandler("clear", clear))
application.add_handler(CommandHandler("clearteam", clear_team))

def run_bot():
    print("🤖 Бот запущен в фоне...")
    application.run_polling()

# ===== FLASK-СЕРВЕР ДЛЯ RENDER =====
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает! 🤖"

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    # Запускаем Flask-сервер
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
        
   
