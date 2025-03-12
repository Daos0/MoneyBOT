import os
from flask import Flask, request
from aiogram import Bot, Dispatcher
from aiogram.types import Update

# Загружаем токен из переменной окружения (Railway задаст его)
API_TOKEN = os.environ.get("7987383265:AAHYOCxCVk8AeM61iFEGnzXPKFCHOXoRDjk")
app = Flask(__name__)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
@app.route("/", methods=["GET"])
def home():
    return "Бот работает!"

@app.route(f"/{API_TOKEN}", methods=["POST"])
async def telegram_webhook():
    update = Update(**request.json)
    await dp.process_update(update)
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 3000))  # Railway назначит порт автоматически
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    import threading
    threading.Thread(target=run_flask).start()
