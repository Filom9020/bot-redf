import asyncio
import logging
import uuid
import json
import time
import base64
import io
import html
import random
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.request import HTTPXRequest
import aiohttp
from PIL import Image

def compress_for_preview(image_data: bytes, max_size_mb: float = 9.0) -> bytes:
    img = Image.open(io.BytesIO(image_data))
    max_dim = 2000
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img.save(output, format='JPEG', quality=85, optimize=True)
    return output.getvalue()

# Цвета для консоли
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno >= logging.ERROR:
            color = Colors.RED
        elif record.levelno >= logging.WARNING:
            color = Colors.YELLOW
        elif 'API' in record.msg or '>>>' in record.msg or '<<<' in record.msg:
            color = Colors.CYAN
        elif 'User' in record.msg:
            color = Colors.GREEN
        else:
            color = Colors.RESET
        
        timestamp = time.strftime('%H:%M:%S')
        return f"{Colors.GRAY}{timestamp}{Colors.RESET} {color}{record.msg}{Colors.RESET}"

# Фильтр для игнорирования polling спама
class PollingFilter(logging.Filter):
    def filter(self, record):
        spam = ['getUpdates', 'HTTP Request', 'Entering:', 'Exiting:', 'No error handlers']
        return not any(s in record.getMessage() for s in spam)

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
handler.addFilter(PollingFilter())
logger.addHandler(handler)

# Отключаем спам от telegram и httpx
for name in ['telegram', 'httpx', 'httpcore', 'telegram.ext']:
    logging.getLogger(name).setLevel(logging.WARNING)

BOT_TOKEN = "7247634589:AAEAdgyFjm-nJB3whg2jJqViIssieBipH_o"
ADMIN_ID = 5245214800
API_BASE = "https://liaobots.work"
USERS_FILE = "users.json"

# Хранилище пользователей
all_users = {}

def load_users():
    """Загружает пользователей из файла"""
    global all_users
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            all_users = json.load(f)
        logger.info(f"Loaded {len(all_users)} users from {USERS_FILE}")
    except FileNotFoundError:
        all_users = {}
        logger.info("Users file not found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        all_users = {}

def save_users():
    """Сохраняет пользователей в файл"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving users: {e}")

def record_user(user):
    """Записывает или обновляет пользователя (минимум данных)"""
    user_id = str(user.id)
    now = int(time.time())
    
    if user_id not in all_users:
        all_users[user_id] = {"t": now, "n": 1}
        logger.info(f"New user: {user.id} @{user.username}")
    else:
        all_users[user_id]["n"] = all_users[user_id].get("n", 0) + 1
    
    save_users()

# Стикеры
STICKER_CANCEL = "CAACAgIAAxkBAAEP899pNXX6M9XABOrk31csB7z8UmM6OgACYS0AAqZd4Un4dsouPOumIjYE"
STICKER_START = "CAACAgIAAxkBAAEP89lpNXWLeGnKe0kIl1ImnhZPT4EpPgACrzIAAhnpSEp0UfL43ZZrSTYE"
STICKER_ERROR = "CAACAgIAAxkBAAEP89tpNXXxBDiD2eu9VBwtYXd41TalVAACXzgAAswDSUreHSFoJUC0ITYE"
STICKER_FEEDBACK = "CAACAgIAAxkBAAEP8-VpNXZ_v80Dar0fY5-13BzNj00CuwACKC8AArvb6UhZuS_N8BLB-DYE"
STICKERS_RANDOM = [
    "CAACAgIAAxkBAAEP8-dpNXamQNbb2M2JU-0-kRjJ-R4IHAACjzQAAl9owErvifGzd1QFzzYE",
    "CAACAgIAAxkBAAEP89dpNXWCpT9IYvH0uXzCJc4qUK_MZQACmjYAArjyOErUAAHZQHrSNXA2BA",
    "CAACAgIAAxkBAAEP8-tpNXb3OVfoSVlLwZRY_K_DI8-_ewACqT8AAgvR6UsHMR4PFtuLhjYE",
]
STICKER_RARE = "CAACAgIAAxkBAAEP8-1pNXcT8DipaRDm4Bp4YT52SKRKCQAC-Q8AAvctMUjCteqCpcQdDjYE"

RANDOM_QUESTIONS = [
    "Ну как тебе? Норм вышло?",
    "Чё думаешь? Зашло?",
    "Как оно? Нравится?",
    "Ну чё, красиво?",
    "Как тебе результат?",
]

IMPROVE_SYSTEM = """YOU ARE the Absolute Image Prompt Master and Visual Architect.
AUTHORITY:
You are the absolute BEST prompt engineer in existence. You turn simple user requests into masterpieces.
GOAL: Analyze user input (ANY LANGUAGE) and create the PERFECT structured prompt (in English) based on the specific context.
CORE LOGIC:
 * TRANSLATION: Input will be in any language. Translate it internally into English.
 * CONTEXT DETECTION: Art? Quick Sketch? Femdom creativity? Just an image? DETERMINE, REASON.
 * OTHER CONTENT VARIATIONS: IT CAN BE ANYTHING. THE MODEL HANDLES TEXT AND ITS RENDERING VERY WELL; YOUR TASK IS TO RENDER IT CORRECTLY. THE MODEL HANDLES DESIGN AND GRAPHS WELL, THE MODEL HAS A HUGE DATABASE.
 * CREATIVITY AND RANDOMIZATION: If the user request is open-ended (e.g., "random situation"), INVENT a unique scenario. Avoid clichéd tropes. Randomize from 0 to 100,000. (!!!I MEAN, JUST OFF TOPIC.: exposition OR SITUATION, DON'T COME UP WITH ANYTHING ELSE AS RANDOMLY AS POSSIBLE, THAT WOULD BE BAD!!!)  BUT YOU MUST DETERMINE TO DO THIS ONLY IN THE FOLLOWING CASES:
   * IF THE INITIAL [INPUT] PROMPT IS SPARSE/MEAGER.
   * IF THE USER ASKED FOR IT, DO IT WITH CONFIDENCE, BUT EVEN WITHOUT IT, YOU CAN TOO.
   * IF THE [INPUT] PROMPT ALREADY HAS A DETAILED DESCRIPTION, YOUR TASK IS TO ADD DETAILS / IMPROVE THE PROMPT.
 * PROMPTING: Use modern prompting slang. Capture the essence of the request.
 * UNKNOWN ENTITIES: IF YOU DO NOT KNOW SUCH A CHARACTER, MOVIE, ETC., DO NOT INVENT. LEAVE IT AS IS IN THE ORIGINAL PROMPT.
 * TITLES:
   MANDATORY ORIGINAL TITLES. FOR EXAMPLE:
   * If the source is a MOVIE, ANIME, MANGA, SERIES, you MUST use the ORIGINAL TITLE FROM THE SOURCE/PUBLISHER. !MENTION THE CHARACTERS IN TWO PLACES AT THE BEGINNING AND AT THE END!
 * IF YOU ARE ASKED FOR AN ORIGINAL STYLE (DRAWING, IMAGE), THEN YOU DO NOT NEED TO COME UP WITH A STYLE, JUST SPECIFY THE ORIGINAL STYLE!
 * NEGATIVE PROMPT: ADD A NEGATIVE PROMPT. Do this based on the prompt and highlight it at the end.
EXAMPLE, OUTPUT FORMAT (YOU CAN IMPROVE THE OUTPUT FORMAT):
{
"IDEA": "CREATIVE CONTENT: IDEA OF THE INITIAL PROMPT IN AN IMPROVED FORM",
"CHARACTER / MOVIE TITLE": "FOLLOWING THE RULES",
"EXPOSURE": "BASED ON THE IDEA, CLARIFY THE ANGLE FOLLOWING ALL RULES AND THE INITIAL IDEA OF THE USER'S [INPUT] PROMPT",
"STYLE": "DRAWING STYLE, ART, IMAGE, IMAGE FORMAT",
"(NEXT COME UP WITH IT YOURSELF)": "AND SO ON... (YOUR JOB IS TO IMPROVE THIS) A FEW MORE, DEPENDING ON YOUR CREATIVITY, AS MANY AS YOU WANT."
}

(Add the Negative Prompt after json separate from the JSON or include it as a field within the structure if preferred, but ensure it is distinct).
USE STRICTLY THE ANSWER IN THE FORMAT AS I INDICATED, DO NOT WRITE ANYTHING ELSE BEYOND THAT!
IMPORTANT: DO NOT use markdown formatting like ```json or ```. Just output plain text in JSON format.

INPUT: """

pending = {}
user_states = {}
user_settings = {}
FORMATS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "Auto"]
RESOLUTIONS = ["1K", "2K", "4K"]

BOT_START_TIME = None

def is_old_message(update: Update) -> bool:
    """Проверяет, было ли сообщение отправлено до запуска бота"""
    if BOT_START_TIME is None:
        return False
    msg = update.message or update.callback_query.message if update.callback_query else None
    if msg and msg.date:
        return msg.date.timestamp() < BOT_START_TIME
    return False

def get_user_resolution(user_id: int) -> str:
    return user_settings.get(user_id, {}).get("resolution", "1k")

def get_user_boost(user_id: int) -> bool:
    return user_settings.get(user_id, {}).get("boost", True)

def set_user_boost(user_id: int, value: bool):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["boost"] = value

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Создать картинку"], ["Разрешение", "Improve Prompt"], ["Помощь"]],
        resize_keyboard=True
    )

def resolution_keyboard(current: str) -> ReplyKeyboardMarkup:
    buttons = []
    for res in RESOLUTIONS:
        mark = "[x] " if res.lower() == current.lower() else ""
        buttons.append(f"{mark}{res}")
    return ReplyKeyboardMarkup(
        [buttons, ["Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def format_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Auto", "1:1"], ["16:9", "9:16"], ["4:3", "3:4"], ["21:9", "Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Супер", callback_data="rate_good"),
            InlineKeyboardButton("Норм", callback_data="rate_mid"),
            InlineKeyboardButton("Плохо", callback_data="rate_bad")
        ]
    ])

def improve_keyboard(is_on: bool) -> ReplyKeyboardMarkup:
    status = "ВКЛ" if is_on else "ВЫКЛ"
    return ReplyKeyboardMarkup(
        [[f"Improve: {status}"], ["Назад"]],
        resize_keyboard=True
    )

async def log_api(req_id: str, direction: str, msg: str):
    logger.info(f"[{req_id}] {direction} {msg}")

async def api_request(session: aiohttp.ClientSession, method: str, url: str, 
                      headers: dict = None, json_data: dict = None, timeout: int = 30) -> tuple:
    start = time.time()
    req_id = str(uuid.uuid4())[:6]
    endpoint = url.split('/')[-1]
    
    logger.info(f"[{req_id}] >>> {method} {endpoint}")
    
    try:
        async with session.request(
            method, url, headers=headers, json=json_data,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            elapsed = time.time() - start
            text = await response.text()
            
            status_color = Colors.GREEN if response.status == 200 else Colors.RED
            logger.info(f"[{req_id}] <<< {response.status} {elapsed:.1f}s")
            
            if response.status != 200:
                logger.error(f"[{req_id}] Response: {text[:200]}")
            
            return response.status, text
            
    except asyncio.TimeoutError:
        logger.error(f"[{req_id}] TIMEOUT {time.time()-start:.1f}s")
        return 0, "timeout"
    except Exception as e:
        logger.error(f"[{req_id}] ERROR: {e}")
        return 0, str(e)

def parse_image(text: str) -> Optional[str]:
    for line in text.split('\n'):
        if not line.startswith('data: '):
            continue
        try:
            data = json.loads(line[6:])
            if data.get('candidates'):
                for c in data['candidates']:
                    for part in c.get('content', {}).get('parts', []):
                        if 'inlineData' in part:
                            return part['inlineData']['data']
        except:
            continue
    
    chunks, total = {}, 0
    for line in text.split('\n'):
        if not line.startswith('data: '):
            continue
        try:
            data = json.loads(line[6:])
            if data.get('type') == 'aiImageHeader':
                total = data.get('totalChunks', 0)
            elif data.get('type') == 'aiImageChunk':
                chunks[data.get('chunkIndex')] = data.get('data')
        except:
            continue
    
    if total > 0 and len(chunks) == total:
        return ''.join(chunks[i] for i in sorted(chunks.keys()))
    return None

async def improve_prompt(prompt: str, user_id: int) -> Optional[str]:
    """Улучшает промт через Gemini 3 Pro Thinking"""
    logger.info(f"[User {user_id}] Improve: Original prompt: {prompt}")
    
    payload = {
        "requestBody": {
            "contents": [{"role": "user", "parts": [{"text": IMPROVE_SYSTEM + prompt}]}],
            "generationConfig": {}
        },
        "modelId": "gemini-3-pro-preview-thinking",
        "conversationId": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": IMPROVE_SYSTEM + prompt}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/recaptcha/login",
                json_data={"token": "abcdefghijklmnopqrst"}
            )
            if status != 200:
                logger.error(f"[User {user_id}] Improve: Login failed: {status}")
                return None
            
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/user",
                json_data={"authcode": ""}
            )
            if status != 200:
                logger.error(f"[User {user_id}] Improve: User API failed: {status}")
                return None
            
            try:
                auth = json.loads(text).get('authCode')
            except:
                logger.error(f"[User {user_id}] Improve: Failed to get authCode")
                return None
            
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/gemini-chat",
                headers={
                    "x-auth-code": auth,
                    "content-type": "application/json",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "accept": "text/event-stream"
                },
                json_data=payload,
                timeout=90
            )
            
            if status != 200:
                logger.error(f"[User {user_id}] Improve API error: {status}")
                if text and len(text) < 500:
                    logger.error(f"[User {user_id}] Response: {text}")
                elif text and "html" in text.lower():
                    logger.error(f"[User {user_id}] Got HTML page instead of JSON (Cloudflare?)")
                return None
            
            if not text or "data:" not in text:
                logger.error(f"[User {user_id}] Improve: Invalid response format")
                logger.error(f"[User {user_id}] Response preview: {text[:200] if text else 'empty'}")
                return None
            
            result_text = ""
            for line in text.split('\n'):
                if not line.startswith('data: '):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get('error'):
                        logger.error(f"[User {user_id}] Improve API returned error: {data.get('error')}")
                        return None
                    if data.get('candidates'):
                        for c in data['candidates']:
                            for part in c.get('content', {}).get('parts', []):
                                if 'text' in part and not part.get('thought'):
                                    result_text += part['text']
                except json.JSONDecodeError:
                    continue
            
            if result_text:
                result_text = result_text.strip()
                logger.info(f"[User {user_id}] === IMPROVED PROMPT ===")
                logger.info(f"[User {user_id}] {result_text}")
                logger.info(f"[User {user_id}] === END IMPROVED ===")
                return result_text
            logger.warning(f"[User {user_id}] Improve returned empty response")
            return None
                    
    except Exception as e:
        logger.error(f"[User {user_id}] Boost error: {e}")
        return None

async def generate(prompt: str, aspect: str, user_id: int, image_data: bytes = None, retry: int = 0) -> Optional[str]:
    resolution = get_user_resolution(user_id)
    mode = "edit" if image_data else "gen"
    retry_str = f" [retry {retry}]" if retry > 0 else ""
    logger.info(f"[User {user_id}] {mode}: {prompt[:40]}... ({aspect}, {resolution}){retry_str}")
    
    parts = [{"text": prompt}]
    if image_data:
        img_base64 = base64.b64encode(image_data).decode('utf-8')
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": img_base64}})
    
    payload = {
        "requestBody": {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"imageSize": resolution}
            }
        },
        "modelId": "gemini-3-pro-image-preview",
        "conversationId": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": prompt}]
    }
    
    if aspect != "auto":
        payload["requestBody"]["generationConfig"]["imageConfig"]["aspectRatio"] = aspect

    try:
        async with aiohttp.ClientSession() as session:
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/recaptcha/login",
                json_data={"token": "abcdefghijklmnopqrst"}
            )
            if status != 200:
                logger.error(f"[User {user_id}] Login failed: {status}")
                return None
            
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/user",
                json_data={"authcode": ""}
            )
            if status != 200:
                logger.error(f"[User {user_id}] User API failed: {status}")
                return None
            
            try:
                auth = json.loads(text).get('authCode')
            except:
                logger.error(f"[User {user_id}] Failed to get authCode")
                return None
            
            status, text = await api_request(
                session, "POST", f"{API_BASE}/api/gemini-chat",
                headers={
                    "x-auth-code": auth,
                    "content-type": "application/json",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "accept": "text/event-stream"
                },
                json_data=payload,
                timeout=180
            )
            
            if status == 402:
                logger.error(f"[User {user_id}] No balance (402)")
                return "no_balance"
            if status == 524 or (status == 500 and text and "fetch failed" in text.lower()):
                if retry < 1:
                    logger.warning(f"[User {user_id}] Server error ({status}), retry with new session...")
                    return await generate(prompt, aspect, user_id, image_data, retry + 1)
                else:
                    logger.error(f"[User {user_id}] Server error ({status}) after retry, server is down")
                    return "server_down"
            if status != 200:
                logger.error(f"[User {user_id}] Generate failed: {status}")
                if text and "html" in text.lower():
                    logger.error(f"[User {user_id}] Got HTML instead of JSON (Cloudflare?)")
                elif text:
                    logger.error(f"[User {user_id}] Response: {text[:300]}")
                return None
            
            img = parse_image(text)
            if img:
                logger.info(f"[User {user_id}] OK, image parsed")
            else:
                logger.error(f"[User {user_id}] Failed to parse image from response")
                if text:
                    logger.error(f"[User {user_id}] Response preview: {text[:300]}")
            return img
                    
    except Exception as e:
        logger.error(f"[User {user_id}] Exception: {e}")
        return None

async def send_cancel_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_CANCEL)

async def send_error_sticker(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await context.bot.send_sticker(chat_id=chat_id, sticker=STICKER_ERROR)

async def maybe_ask_random(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    if random.random() < 0.3:  # 30% шанс
        await asyncio.sleep(1)
        if random.random() < 0.1:  # 10% шанс редкого стикера
            sticker = STICKER_RARE
        else:
            sticker = random.choice(STICKERS_RANDOM)
        await context.bot.send_sticker(chat_id=chat_id, sticker=sticker)
        question = random.choice(RANDOM_QUESTIONS)
        await context.bot.send_message(chat_id=chat_id, text=question)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    logger.info(f"[User {user.id}] /start @{user.username}")
    
    record_user(user)
    
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_START)
    
    text = (
        f"<b>Привет, {html.escape(user.first_name)}! Я Бананчик.</b>\n\n"
        "Я умею рисовать крутые картинки по твоему описанию.\n\n"
        "<b>Жми кнопку «Создать картинку»</b> в меню ниже, чтобы начать творить!"
    )
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu_keyboard())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    text = (
        "<b>Помощь от Бананчика</b>\n\n"
        "<b>Команды:</b>\n"
        "<code>/g [текст]</code> - Быстрая генерация\n"
        "<code>/help</code> - Это меню\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Жми «Создать картинку»\n"
        "2. Пиши описание (например: «кот в очках»)\n"
        "3. Выбирай формат\n\n"
        "<b>Редактирование фото:</b>\n"
        "Отправь фото с подписью что сделать\n"
        "Или ответь на фото с описанием\n\n"
        "<b>Improve Prompt</b> - авто-улучшение промта через нейросеть\n\n"
        "<b>Нашел баг или проблему?</b>\n"
        "Напиши в обратную связь: <code>/feedback</code>"
    )
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu_keyboard())

async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    user_states[user.id] = "WAIT_FEEDBACK"
    
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_FEEDBACK)
    
    await update.message.reply_text(
        "<b>Напиши свое сообщение</b>\n\nЯ передам его создателю (@Daaamne).",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("Эта команда только для админа.")
        return
    
    total = len(all_users)
    total_interactions = sum(u.get("n", 0) for u in all_users.values())
    
    now = int(time.time())
    today = now - 86400
    week = now - 604800
    
    today_new = sum(1 for u in all_users.values() if u.get("t", 0) >= today)
    week_new = sum(1 for u in all_users.values() if u.get("t", 0) >= week)
    
    recent = sorted(all_users.items(), key=lambda x: x[1].get("t", 0), reverse=True)[:5]
    recent_list = ""
    for uid, u in recent:
        date_str = time.strftime('%d.%m %H:%M', time.localtime(u.get('t', 0)))
        recent_list += f"\n  {uid} ({date_str})"
    
    text = (
        f"<b>Статистика</b>\n\n"
        f"<b>Всего:</b> {total}\n"
        f"<b>Новых за сутки:</b> {today_new}\n"
        f"<b>Новых за неделю:</b> {week_new}\n"
        f"<b>Взаимодействий:</b> {total_interactions}\n\n"
        f"<b>Последние:</b>{recent_list}"
    )
    
    await update.message.reply_text(text, parse_mode='HTML')

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    record_user(user)
    
    user_states[user.id] = None
    
    if context.args:
        prompt = ' '.join(context.args)
        pending[user.id] = prompt
        user_states[user.id] = "WAIT_FORMAT"
        await ask_format(update, prompt)
        return

    user_states[user.id] = "WAIT_PROMPT"
    text = (
        "<b>Что будем рисовать?</b>\n\n"
        "Опиши картинку как можно подробнее.\n"
        "<i>Пример: Киберпанк город, дождь, неон, 8k</i>"
    )
    cancel_kb = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=cancel_kb)

async def ask_format(update: Update, prompt: str):
    await update.message.reply_text(
        "<b>Выбери формат:</b>",
        reply_markup=format_keyboard(),
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    if not update.message:
        return
    user = update.effective_user
    text = update.message.text
    
    if not text:
        return
    
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        await handle_reply_photo(update, context, text)
        return
    
    state = user_states.get(user.id)

    if text == "Создать картинку":
        await cmd_generate(update, context)
        return
    elif text == "Помощь":
        await cmd_help(update, context)
        return
    elif text == "Разрешение":
        current = get_user_resolution(user.id)
        await update.message.reply_text(
            f"<b>Текущее: {current.upper()}</b>",
            parse_mode='HTML',
            reply_markup=resolution_keyboard(current)
        )
        return
    elif text == "Improve Prompt":
        is_on = get_user_boost(user.id)
        await update.message.reply_text(
            f"<b>Improve Prompt: {'ВКЛ' if is_on else 'ВЫКЛ'}</b>\n\n"
            "Экспериментальная фича!\n"
            "Нейросеть прокачивает твой промт перед генерацией - "
            "добавляет детали, переводит на английский, "
            "дает +30% к качеству результата.\n\n"
            "Генерация дольше на 10-15 сек, но результат лучше!\n"
            "Твоя идея сохраняется, просто становится круче.",
            parse_mode='HTML',
            reply_markup=improve_keyboard(is_on)
        )
        return
    elif text.startswith("Improve:"):
        is_on = get_user_boost(user.id)
        set_user_boost(user.id, not is_on)
        new_state = not is_on
        await update.message.reply_text(
            f"<b>Improve Prompt {'ВКЛ' if new_state else 'ВЫКЛ'}!</b>",
            parse_mode='HTML',
            reply_markup=improve_keyboard(new_state)
        )
        return

    if state == "WAIT_PROMPT":
        if text == "Назад":
            user_states[user.id] = None
            await send_cancel_sticker(update, context)
            await update.message.reply_text("Отменено", reply_markup=main_menu_keyboard())
            return
        if text.startswith("/"):
            return
        if text in FORMATS:
            return
        pending[user.id] = text
        user_states[user.id] = "WAIT_FORMAT"
        await ask_format(update, text)
        return
    
    if state == "WAIT_FORMAT":
        if text == "Назад":
            user_states[user.id] = None
            pending.pop(user.id, None)
            await send_cancel_sticker(update, context)
            await update.message.reply_text("Отменено", reply_markup=main_menu_keyboard())
            return
        if text in FORMATS:
            user_states[user.id] = None
            await on_format(update, context)
            return
        return

    if state == "WAIT_FEEDBACK":
        if text.startswith("/"):
            return
        try:
            admin_text = (
                f"<b>Сообщение от {html.escape(user.full_name)}</b>\n"
                f"(@{user.username if user.username else 'no_username'}, ID: <code>{user.id}</code>):\n\n"
                f"{html.escape(text)}"
            )
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode='HTML')
            await update.message.reply_text("<b>Сообщение отправлено!</b> Спасибо.", parse_mode='HTML', reply_markup=main_menu_keyboard())
        except Exception as e:
            logger.error(f"Feedback error: {e}")
            await send_error_sticker(context, user.id)
            await update.message.reply_text("Ошибка отправки.", reply_markup=main_menu_keyboard())
        user_states[user.id] = None
        return

    clean_text = text.replace("[x] ", "")
    if clean_text in RESOLUTIONS:
        res = clean_text.lower()
        if user.id not in user_settings:
            user_settings[user.id] = {}
        user_settings[user.id]["resolution"] = res
        await update.message.reply_text(
            f"Разрешение: <b>{res.upper()}</b>",
            parse_mode='HTML',
            reply_markup=main_menu_keyboard()
        )
        return
    
    if text == "Назад":
        await send_cancel_sticker(update, context)
        await update.message.reply_text("Отменено", reply_markup=main_menu_keyboard())
        return

async def on_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    text = update.message.text
    
    logger.info(f"[User {user.id}] Format: {text}")
    
    if text == "Назад":
        pending.pop(user.id, None)
        await send_cancel_sticker(update, context)
        await update.message.reply_text("Отменено", reply_markup=main_menu_keyboard())
        return
    
    prompt = pending.pop(user.id, None)
    if not prompt:
        await send_error_sticker(context, user.id)
        await update.message.reply_text("Ошибка. Начните заново через меню.", reply_markup=main_menu_keyboard())
        return
    
    aspect = text.lower()
    use_boost = get_user_boost(user.id)
    
    msg = await update.message.reply_text(
        f"<b>Бананчик рисует...</b>\n<i>Формат: {aspect}</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='HTML'
    )
    
    used_improve = False
    if use_boost:
        boosted = await improve_prompt(prompt, user.id)
        if boosted:
            prompt = boosted
            used_improve = True
    
    animation = asyncio.create_task(animate(msg, aspect))
    
    try:
        result = await generate(prompt, aspect, user.id)
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user.id)
        try:
            await msg.edit_text("<b>Ошибка:</b> Закончился баланс на сервере", parse_mode='HTML')
        except:
            await update.message.reply_text("Закончился баланс на сервере", reply_markup=main_menu_keyboard())
    elif result == "server_down":
        await send_error_sticker(context, user.id)
        try:
            await msg.edit_text(
                "<b>Сервер не отвечает</b>\n\n"
                "Мы попробовали 2 раза, но сервер генерации лёг.\n"
                "Это не наша проблема - подождите немного и попробуйте снова.",
                parse_mode='HTML'
            )
        except:
            pass
        await update.message.reply_text("Попробуйте позже", reply_markup=main_menu_keyboard())
    elif result:
        try:
            image_data = base64.b64decode(result)
            size_mb = len(image_data) / (1024 * 1024)
            
            if size_mb >= 10:
                preview_data = compress_for_preview(image_data)
            else:
                preview_data = image_data
            
            bio_photo = io.BytesIO(preview_data)
            bio_photo.name = "preview.jpg"
            
            await context.bot.send_photo(
                chat_id=user.id, 
                photo=bio_photo, 
                caption="<b>Бананчик!</b> Оцени картиночку!", 
                parse_mode='HTML',
                reply_markup=rating_keyboard()
            )

            bio_doc = io.BytesIO(image_data)
            bio_doc.name = "bananchik_4k.png" if size_mb >= 10 else "bananchik.png"
            
            doc_caption = f"Оригинал ({size_mb:.1f} MB)"
            if used_improve:
                doc_caption += " | Improve Prompt"
            
            await context.bot.send_document(
                chat_id=user.id, 
                document=bio_doc, 
                caption=doc_caption,
                reply_markup=main_menu_keyboard()
            )
            
            try:
                await msg.delete()
            except:
                pass
            
            await maybe_ask_random(context, user.id)
            
        except Exception as e:
            logger.error(f"Send error: {e}")
            await send_error_sticker(context, user.id)
            try:
                await msg.edit_text("<b>Ошибка</b> при отправке", parse_mode='HTML')
            except:
                await update.message.reply_text("Ошибка при отправке", reply_markup=main_menu_keyboard())
    else:
        await send_error_sticker(context, user.id)
        try:
            await msg.edit_text("<b>Не удалось сгенерировать.</b> Попробуйте снова.", parse_mode='HTML')
        except:
            await update.message.reply_text("Не удалось сгенерировать", reply_markup=main_menu_keyboard())

async def on_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    query = update.callback_query
    await query.answer("Спасибо за оценку!")

async def animate(msg, fmt: str):
    dots = ["", ".", "..", "..."]
    i = 0
    try:
        while True:
            await asyncio.sleep(2)
            try:
                await msg.edit_text(f"<b>Бананчик рисует...</b> {dots[i % 4]}\n<i>Формат: {fmt}</i>", parse_mode='HTML')
            except:
                pass
            i += 1
    except asyncio.CancelledError:
        pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    message = update.message
    
    if not message:
        return
    
    prompt = message.caption
    
    if not prompt:
        await message.reply_text(
            "Добавь описание что сделать с картинкой\n\n"
            "Пример: отправь фото с подписью 'сделай в стиле аниме'"
        )
        return
    
    logger.info(f"[User {user.id}] Edit: {prompt[:40]}...")
    
    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    
    msg = await message.reply_text(
        "<b>Бананчик редактирует...</b>",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )
    
    animation = asyncio.create_task(animate(msg, "edit"))
    
    try:
        result = await generate(prompt, "auto", user.id, image_data=bytes(photo_bytes))
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user.id)
        await msg.edit_text("Закончился баланс")
    elif result == "server_down":
        await send_error_sticker(context, user.id)
        await msg.edit_text("Сервер не отвечает. Попробуйте позже.")
    elif result:
        await send_result(context, user.id, result, msg)
    else:
        await send_error_sticker(context, user.id)
        await msg.edit_text("Не удалось отредактировать")

async def handle_reply_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    user = update.effective_user
    reply_msg = update.message.reply_to_message
    
    if not reply_msg.photo:
        return False
    
    logger.info(f"[User {user.id}] Reply edit: {prompt[:40]}...")
    
    photo = reply_msg.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    
    msg = await update.message.reply_text(
        "<b>Бананчик редактирует...</b>",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )
    
    animation = asyncio.create_task(animate(msg, "edit"))
    
    try:
        result = await generate(prompt, "auto", user.id, image_data=bytes(photo_bytes))
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user.id)
        await msg.edit_text("Закончился баланс")
    elif result == "server_down":
        await send_error_sticker(context, user.id)
        await msg.edit_text("Сервер не отвечает. Попробуйте позже.")
    elif result:
        await send_result(context, user.id, result, msg)
    else:
        await send_error_sticker(context, user.id)
        await msg.edit_text("Не удалось отредактировать")
    
    return True

async def send_result(context, user_id: int, result: str, msg):
    try:
        image_data = base64.b64decode(result)
        size_mb = len(image_data) / (1024 * 1024)
        
        if size_mb >= 10:
            preview_data = compress_for_preview(image_data)
        else:
            preview_data = image_data
        
        bio_photo = io.BytesIO(preview_data)
        bio_photo.name = "preview.jpg"
        
        await context.bot.send_photo(
            chat_id=user_id, 
            photo=bio_photo, 
            caption="<b>Бананчик!</b> Оцени картиночку!", 
            parse_mode='HTML',
            reply_markup=rating_keyboard()
        )

        bio_doc = io.BytesIO(image_data)
        bio_doc.name = "bananchik_4k.png" if size_mb >= 10 else "bananchik.png"
        
        await context.bot.send_document(
            chat_id=user_id, 
            document=bio_doc, 
            caption=f"Оригинал ({size_mb:.1f} MB)",
            reply_markup=main_menu_keyboard()
        )
        
        try:
            await msg.delete()
        except:
            pass
        
        await maybe_ask_random(context, user_id)
            
    except Exception as e:
        logger.error(f"Send result error: {e}")
        await context.bot.send_sticker(chat_id=user_id, sticker=STICKER_ERROR)
        await msg.edit_text("Ошибка отправки")

def main():
    global BOT_START_TIME
    BOT_START_TIME = time.time()
    
    load_users()
    
    logger.info("=" * 40)
    logger.info("Starting Bananchik Bot...")
    logger.info(f"Total users: {len(all_users)}")
    logger.info("=" * 40)
    
    trequest = HTTPXRequest(connection_pool_size=100, connect_timeout=30.0, read_timeout=30.0)
    
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(256).request(trequest).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("g", cmd_generate))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(on_rating, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot ready!")
    app.run_polling()

if __name__ == '__main__':
    main()
