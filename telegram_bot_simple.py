import asyncio
import logging
import json
import time
import base64
import io
import html
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.request import HTTPXRequest
import aiohttp
from PIL import Image

def _compress_for_preview_sync(image_data: bytes, max_size_mb: float = 9.0) -> bytes:
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

async def compress_for_preview(image_data: bytes, max_size_mb: float = 9.0) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _compress_for_preview_sync, image_data, max_size_mb)

def _detect_aspect_ratio_sync(image_data: bytes) -> str:
    """
    Detect image aspect ratio and return closest supported format.
    Supported: 1:1, 16:9, 9:16, 4:3, 3:4, 21:9
    """
    img = Image.open(io.BytesIO(image_data))
    width, height = img.size
    ratio = width / height
    
    # Supported formats with their ratios
    formats = {
        "1:1": 1.0,
        "16:9": 16/9,
        "9:16": 9/16,
        "4:3": 4/3,
        "3:4": 3/4,
        "21:9": 21/9
    }
    
    # Find closest match
    closest = min(formats.items(), key=lambda x: abs(x[1] - ratio))
    return closest[0]

async def detect_aspect_ratio(image_data: bytes) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _detect_aspect_ratio_sync, image_data)

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
        # Improved log format: [Time] [Level] Message
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

def record_user(user):
    """Records user in account manager (creates entry if needed)"""
    from account_manager import get_manager
    manager = get_manager()
    user_key = str(user.id)
    
    if user_key not in manager.users:
        manager.users[user_key] = {"emails": [], "resolution": "1k", "boost": True}
        manager.save()
        logger.info(f"New user: {user.id} @{user.username}")

# Стикеры
STICKER_START = "CAACAgIAAxkBAAEP89lpNXWLeGnKe0kIl1ImnhZPT4EpPgACrzIAAhnpSEp0UfL43ZZrSTYE"

# Остальные стикеры отключены

pending = {}
user_states = {}
FORMATS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9"]
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
    """Возвращает разрешение пользователя из Account Manager"""
    from account_manager import get_manager
    return get_manager().get_user_resolution(user_id)

def set_user_resolution(user_id: int, value: str):
    """Устанавливает разрешение пользователя через Account Manager"""
    from account_manager import get_manager
    get_manager().set_user_resolution(user_id, value)

def get_user_boost(user_id: int) -> bool:
    from account_manager import get_manager
    return get_manager().get_user_boost(user_id)

def set_user_boost(user_id: int, value: bool):
    from account_manager import get_manager
    get_manager().set_user_boost(user_id, value)

def get_user_aspect_ratio(user_id: int) -> str:
    from account_manager import get_manager
    return get_manager().get_user_aspect_ratio(user_id)

def set_user_aspect_ratio(user_id: int, value: str):
    from account_manager import get_manager
    get_manager().set_user_aspect_ratio(user_id, value)

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Создать картинку"], ["Настройки", "Improve Prompt"], ["Помощь"]],
        resize_keyboard=True
    )

def settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Формат", "Разрешение"], ["Назад"]],
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

def format_keyboard(current: str = "1:1") -> ReplyKeyboardMarkup:
    # Helper to mark current selection
    def fmt_btn(txt):
        return f"[x] {txt}" if txt == current else txt

    return ReplyKeyboardMarkup(
        [
            [fmt_btn("1:1"), fmt_btn("16:9")],
            [fmt_btn("9:16"), fmt_btn("4:3")],
            [fmt_btn("3:4"), fmt_btn("21:9")],
            ["Назад"]
        ],
        resize_keyboard=True
    )



def improve_keyboard(is_on: bool) -> ReplyKeyboardMarkup:
    status = "ВКЛ" if is_on else "ВЫКЛ"
    return ReplyKeyboardMarkup(
        [[f"Improve: {status}"], ["Назад"]],
        resize_keyboard=True
    )

async def safe_edit_text(msg, text: str, parse_mode: str = None):
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.warning(f"Edit error: {e}")
        try:
            await msg.reply_text(text, parse_mode=parse_mode)
            return True
        except:
            return False


async def improve_prompt(prompt: str, user_id: int) -> Optional[str]:
    """Улучшение промта (временно отключено)"""
    logger.info(f"[User {user_id}] Improve: disabled")
    return None

# ============== NOTEGPT GENERATION ==============
import hmac
import hashlib
from account_manager import get_manager

NOTEGPT_BASE = "https://notegpt.io"
SECRET_KEY = "nc_ng_ai_image"

def generate_sign(params: dict) -> str:
    """HMAC-SHA256 signature for NoteGPT API"""
    def format_val(k, v):
        if isinstance(v, list):
            return f"{k}=[]" if len(v) == 0 else f"{k}=[{', '.join([repr(x) for x in v])}]"
        return f"{k}={v}"
    
    sorted_keys = sorted(params.keys())
    param_str = "&".join([format_val(k, params[k]) for k in sorted_keys])
    return hmac.new(SECRET_KEY.encode(), param_str.encode(), hashlib.sha256).hexdigest()

async def notegpt_login(session, email: str, password: str) -> bool:
    """Login to NoteGPT with detailed logging"""
    payload = {"email": email, "password": password, "client_type": 0, "client_id": "", "product_mark": "64"}
    headers = {"Content-Type": "application/json", "Origin": NOTEGPT_BASE}
    
    try:
        async with session.post(f"{NOTEGPT_BASE}/api/v1/login-forwarding", json=payload, headers=headers) as resp:
            logger.info(f"🔐 Login response status: {resp.status}")
            
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"🔐 Login HTTP error: {resp.status} - {text[:200]}")
                return False
            
            data = await resp.json()
            code = data.get("code")
            message = data.get("message", "")
            
            logger.info(f"🔐 Login API response: code={code}, message={message}")
            
            if str(code) != "100000":
                logger.error(f"🔐 Login failed: {message}")
                return False
            
            jwt = resp.headers.get("X-Token")
            if jwt:
                await session.get(f"{NOTEGPT_BASE}/user/platform-communication/sync-user-status",
                                params={"token": f'"{jwt}"', "redirect_url": NOTEGPT_BASE})
                logger.info(f"🔐 Session synced for {email}")
            return True
    except Exception as e:
        logger.error(f"🔐 Login exception: {e}")
        return False

async def notegpt_check_quota(session) -> int:
    """Check remaining generations"""
    async with session.get(f"{NOTEGPT_BASE}/api/v2/images/left-times",
                          params={"type": "60", "sub_type": "3"}) as resp:
        if resp.status == 200:
            data = await resp.json()
            if data.get("code") == 100000:
                return data.get("data", {}).get("times_left", 0)
    return 0

async def notegpt_upload_image(session, image_data: bytes) -> Optional[str]:
    """
    Upload image for Image to Image using Aliyun OSS.
    1. Get STS token from NoteGPT
    2. Upload to Aliyun OSS
    3. Return CDN URL
    """
    import uuid as uuid_lib
    from datetime import datetime
    
    t = int(time.time())
    
    # Try different sign formats
    sign_variants = [
        ("hmac", generate_sign({"t": t})),
        ("sha+key", hashlib.sha256(f"t={t}{SECRET_KEY}".encode()).hexdigest()),
        ("key+sha", hashlib.sha256(f"{SECRET_KEY}t={t}".encode()).hexdigest()),
    ]
    
    logger.info(f"STS: trying 3 sign variants for t={t}")
    
    sts = None
    for sign_name, sign in sign_variants:
        try:
            async with session.get(
                f"{NOTEGPT_BASE}/api/v1/oss/sts-token-enc",
                params={"t": t, "sign": sign}
            ) as resp:
                sts_data = await resp.json()
                if sts_data.get("code") == 100000:
                    logger.info(f"✅ STS worked with {sign_name}!")
                    sts = sts_data.get("data", {})
                    break
                else:
                    logger.info(f"  {sign_name}: {sts_data.get('code')}")
        except Exception as e:
            logger.error(f"  {sign_name} error: {e}")
    
    if not sts:
        logger.error("All STS sign variants failed!")
        return None
    
    access_key_id = sts.get("access_key_id")
    access_key_secret = sts.get("access_key_secret")
    security_token = sts.get("security_token")
    bucket = sts.get("bucket", "nc-cdn")
    region = sts.get("region", "oss-us-west-1")
    
    if not all([access_key_id, access_key_secret, security_token]):
        logger.error("Missing STS credentials")
        return None
    
    # Step 2: Generate unique filename
    file_uuid = str(uuid_lib.uuid4())
    object_key = f"notegpt/web3in1/{file_uuid}.jpg"
    oss_url = f"https://{bucket}.{region}.aliyuncs.com/{object_key}"
    cdn_url = f"https://cdn.notegpt.io/{object_key}"
    
    # Step 3: Upload to OSS
    date_str = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    # OSS signature
    string_to_sign = f"PUT\n\nimage/jpeg\n{date_str}\nx-oss-date:{date_str}\nx-oss-security-token:{security_token}\n/{bucket}/{object_key}"
    signature = base64.b64encode(
        hmac.new(access_key_secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    
    headers = {
        "Content-Type": "image/jpeg",
        "x-oss-date": date_str,
        "x-oss-security-token": security_token,
        "Authorization": f"OSS {access_key_id}:{signature}",
        "Host": f"{bucket}.{region}.aliyuncs.com",
        "Origin": NOTEGPT_BASE
    }
    
    try:
        async with aiohttp.ClientSession() as oss_session:
            async with oss_session.put(oss_url, data=image_data, headers=headers) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Image uploaded: {cdn_url[:60]}...")
                    return cdn_url
                else:
                    body = await resp.text()
                    logger.error(f"OSS upload failed: {resp.status} - {body[:200]}")
    except Exception as e:
        logger.error(f"OSS upload error: {e}")
    
    return None

async def notegpt_generate(session, prompt: str, aspect: str, resolution: str) -> Optional[str]:
    """Generate image and return URL (Text to Image only)"""
    t = int(time.time())
    upscale = {"1k": 1, "2k": 2, "4k": 4}.get(resolution.lower(), 2)
    
    params = {
        "image_urls": [], "type": 60, "user_prompt": prompt,
        "aspect_ratio": aspect, "num": 1, "model": "",
        "sub_type": 11, "upscale": upscale, "resolution": resolution.lower(), "t": t
    }
    params["sign"] = generate_sign(params)
    
    headers = {"Content-Type": "application/json", "Origin": NOTEGPT_BASE, "Referer": f"{NOTEGPT_BASE}/nano-banana-pro"}
    
    async with session.post(f"{NOTEGPT_BASE}/api/v2/images/start", json=params, headers=headers) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if data.get("code") != 100000:
            return None
        
        session_id = data.get("data", {}).get("session_id")
        if not session_id:
            return None
        
        # Poll for result
        return await notegpt_poll(session, session_id)

async def notegpt_poll(session, session_id: str, timeout: int = 180) -> Optional[str]:
    """Poll for generation result with logging"""
    start = time.time()
    poll_count = 0
    
    while time.time() - start < timeout:
        poll_count += 1
        elapsed = int(time.time() - start)
        logger.info(f"⏳ Polling #{poll_count} ({elapsed}s)...")
        
        try:
            async with session.get(
                f"{NOTEGPT_BASE}/api/v2/images/status",
                params={"session_id": session_id},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 100000:
                        status = data.get("data", {}).get("status")
                        results = data.get("data", {}).get("results", [])
                        
                        logger.info(f"⏳ Status: {status}")
                        
                        if status == "succeeded" and results:
                            url = results[0].get("url")
                            if url:
                                logger.info(f"✅ Generation complete! URL received")
                                return url
                        elif status == "failed":
                            error = results[0].get("error") if results else "Unknown"
                            logger.error(f"❌ Generation failed: {error}")
                            if "SERVER_IS_BUSY" in str(error):
                                return "server_busy"
                            return None
                else:
                    logger.warning(f"⏳ Poll response: {resp.status}")
        except asyncio.TimeoutError:
            logger.warning(f"⏳ Poll timeout, retrying...")
        except Exception as e:
            logger.warning(f"⏳ Poll error: {e}")
        
        await asyncio.sleep(4)
    
    logger.error(f"❌ Generation timeout after {timeout}s")
    return None

async def generate(prompt: str, aspect: str, user_id: int, image_data: bytes = None, retry: int = 0) -> tuple[Optional[bytes], Optional[str]]:
    """
    Generate image using shared NoteGPT account pool
    Returns: (image_bytes, error_text)
    """
    manager = get_manager()
    resolution = get_user_resolution(user_id)
    
    # Get ANY available account from shared pool
    account = manager.get_available_account()
    
    if not account:
        logger.error(f"[User {user_id}] No accounts in pool! Starting auto-create...")
        asyncio.create_task(manager.auto_create_account())
        return None, "Аккаунты закончились! Создаю новый... Попробуйте через 2-3 минуты."
    
    email = account.get("email")
    password = account.get("password")
    
    logger.info(f"[User {user_id}] Using: {email}")
    
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
        # Login
        if not await notegpt_login(session, email, password):
            logger.warning(f"[User {user_id}] Login failed for {email}")
            return None, "Ошибка входа в аккаунт"
        
        # Check quota before generating
        quota = await notegpt_check_quota(session)
        logger.info(f"[User {user_id}] Quota: {quota}")
        
        if quota <= 0:
            logger.warning(f"[User {user_id}] {email} exhausted, removing...")
            manager.update_account_quota(email, 0)  # This triggers removal + auto-create
            return None, "Аккаунт исчерпан, переключаюсь... Попробуйте ещё раз!"
        
        # Generate (Text to Image only)
        image_url = await notegpt_generate(session, prompt, aspect, resolution)
        
        if image_url == "server_busy":
            logger.warning(f"[User {user_id}] Server busy")
            return None, "Сервер занят. Попробуйте через минуту."
        
        if image_url and image_url.startswith("http"):
            logger.info(f"[User {user_id}] ✅ Got URL")
            
            # Download image
            try:
                async with aiohttp.ClientSession() as dl_session:
                    async with dl_session.get(image_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            image_bytes = await resp.read()
                            logger.info(f"[User {user_id}] 📥 Downloaded: {len(image_bytes)} bytes")
                            
                            # Update quota after generation
                            new_quota = await notegpt_check_quota(session)
                            manager.update_account_quota(email, new_quota)
                            logger.info(f"[User {user_id}] 💎 Quota now: {new_quota}")
                            
                            return image_bytes, None
                        else:
                            logger.error(f"[User {user_id}] Download failed: {resp.status}")
            except Exception as e:
                logger.error(f"[User {user_id}] Download error: {e}")
        else:
            logger.warning(f"[User {user_id}] Generation failed")
    
    return None, "Генерация не удалась. Попробуйте позже."

async def send_cancel_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_CANCEL)
    pass

async def send_error_sticker(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    # await context.bot.send_sticker(chat_id=chat_id, sticker=STICKER_ERROR)
    pass

async def maybe_ask_random(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    # Отключено для уменьшения количества сообщений
    pass

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    logger.info(f"[User {user.id}] /start @{user.username}")
    
    record_user(user)
    
    try:
        await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_START)
    except:
        pass  # User might have blocked bot
    
    text = (
        f"<b>Привет, {html.escape(user.first_name)}!</b>\n\n"
        "Я помогу создать уникальные изображения по твоему описанию.\n"
        "Просто нажми кнопку ниже, чтобы начать."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    text = (
        "<b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "<code>/g [текст]</code> - Быстрая генерация\n"
        "<code>/help</code> - Это меню\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Нажми «Создать картинку»\n"
        "2. Введи описание (например: «кот в космосе»)\n"
        "3. Выбери формат\n\n"
        "<b>Improve Prompt</b> - улучшение твоего описания нейросетью\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

async def cmd_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    user_states[user.id] = "WAIT_FEEDBACK"
    
    
    # await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKER_FEEDBACK)
    
    await update.message.reply_text(
        "<b>Напиши свое сообщение</b>\n\nОно будет отправлено разработчику.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    
    if user.id != ADMIN_ID:
        await update.message.reply_text("Эта команда только для админа.")
        return
    
    manager = get_manager()
    stats = manager.get_stats()
    users = manager.users
    
    total = stats['users_assigned']
    accounts = stats['total_accounts']
    active = stats['accounts_with_quota']
    premium = stats['total_premium_quota']
    
    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"<b>👥 Юзеров:</b> {total}\n"
        f"<b>🔑 Аккаунтов:</b> {accounts} (активных: {active})\n"
        f"<b>💎 Premium квота:</b> {premium}\n\n"
        f"<b>Юзеры:</b>\n"
    )
    
    for uid, data in list(users.items())[:10]:
        res = data.get('resolution', '1k')
        boost = '🚀' if data.get('boost') else ''
        text += f"  {uid}: {res} {boost}\n"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_old_message(update):
        return
    user = update.effective_user
    record_user(user)
    
    user_states[user.id] = None
    
    if context.args:
        prompt = ' '.join(context.args)
        # Immediate generation with saved settings
        await start_generation(update, context, prompt, user.id)
        return

    user_states[user.id] = "WAIT_PROMPT"
    
    # Get current settings for display
    fmt = get_user_aspect_ratio(user.id)
    res = get_user_resolution(user.id)
    
    text = (
        "<b>Что будем рисовать?</b>\n\n"
        f"⚙️ <i>Текущие настройки: {fmt} | {res.upper()}</i>\n\n"
        "Опиши картинку как можно подробнее.\n"
        "<i>Пример: Киберпанк город, дождь, неон, 8k</i>"
    )
    cancel_kb = ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=cancel_kb)

async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, user_id: int):
    # Retrieve settings
    aspect = get_user_aspect_ratio(user_id)
    resolution = get_user_resolution(user_id)
    use_boost = get_user_boost(user_id)
    
    msg = await update.message.reply_text(
        f"<b>Генерация...</b>\n<i>Формат: {aspect} | Разрешение: {resolution.upper()}</i>",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    used_improve = False
    if use_boost:
        # Boost logic here (if applicable)
        # boosted = await improve_prompt(prompt, user_id)
        # if boosted: prompt = boosted
        pass
    
    animation = asyncio.create_task(animate(msg, aspect, resolution))
    
    try:
        result, text_resp = await generate(prompt, aspect, user_id)
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user_id)
        try:
            await safe_edit_text(msg, "<b>Ошибка:</b> Закончился баланс на сервере", parse_mode='HTML')
        except:
            await update.message.reply_text("Закончился баланс на сервере", reply_markup=main_menu_keyboard())
    elif result == "server_down":
        await send_error_sticker(context, user_id)
        try:
            await safe_edit_text(msg,
                "<b>Сервер не отвечает</b>\n\n"
                "Мы попробовали 2 раза, но сервер генерации лёг.\n"
                "Это не наша проблема - подождите немного и попробуйте снова.",
                parse_mode='HTML'
            )
        except:
            pass
        await update.message.reply_text("Попробуйте позже", reply_markup=main_menu_keyboard())
    elif result == "white_screen":
        await send_error_sticker(context, user_id)
        try:
            await safe_edit_text(msg, "<b>Ошибка доступа (White Screen)</b>\n\nСервер вернул HTML страницу вместо данных (возможно Cloudflare). Попробуйте позже.", parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text("Ошибка доступа (White Screen)", reply_markup=main_menu_keyboard())
    elif result:
        await send_result(context, user_id, result, msg, update.message.message_id)
    else:
        await send_error_sticker(context, user_id)
        if text_resp:
            cleaned_text = text_resp.replace('**', '').replace('\n\n', '\n')
            if len(cleaned_text) > 800:
                cleaned_text = cleaned_text[:800] + "..."
            try:
                await safe_edit_text(msg, f"<b>Не удалось сгенерировать.</b>\n\nОтвет нейросети:\n{html.escape(cleaned_text)}", parse_mode='HTML')
            except:
                await update.message.reply_text("Не удалось сгенерировать", reply_markup=main_menu_keyboard())
        else:
            try:
                await safe_edit_text(msg, "<b>Не удалось сгенерировать.</b> Попробуйте снова.", parse_mode='HTML')
            except:
                await update.message.reply_text("Не удалось сгенерировать", reply_markup=main_menu_keyboard())

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
        
        # User entered prompt -> Generate immediately
        user_states[user.id] = None
        await start_generation(update, context, text, user.id)
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

    # Handle Settings Submenu
    if text == "Настройки":
        await update.message.reply_text("⚙️ <b>Настройки генерации</b>", parse_mode='HTML', reply_markup=settings_keyboard())
        return
        
    if text == "Формат":
        current = get_user_aspect_ratio(user.id)
        await update.message.reply_text(
            f"<b>Выберите формат (Aspect Ratio)</b>\nТекущий: {current}", 
            parse_mode='HTML', 
            reply_markup=format_keyboard(current)
        )
        return

    if text == "Разрешение":
        current = get_user_resolution(user.id)
        await update.message.reply_text(
            f"<b>Выберите разрешение</b>\nТекущее: {current.upper()}",
            parse_mode='HTML',
            reply_markup=resolution_keyboard(current)
        )
        return

    # Handle Format Selection
    clean_text = text.replace("[x] ", "")
    if clean_text in FORMATS:
        set_user_aspect_ratio(user.id, clean_text)
        await update.message.reply_text(f"✅ Формат установлен: <b>{clean_text}</b>", parse_mode='HTML', reply_markup=settings_keyboard())
        return

    # Handle Resolution Selection
    if clean_text in RESOLUTIONS:
        res = clean_text.lower()
        set_user_resolution(user.id, res)
        logger.info(f"[User {user.id}] Set resolution: {res.upper()}")
        await update.message.reply_text(
            f"✅ Разрешение установлено: <b>{res.upper()}</b>",
            parse_mode='HTML',
            reply_markup=settings_keyboard()
        )
        return
    
    if text == "Назад":
        # Always return to main menu
        await send_cancel_sticker(update, context)
        await update.message.reply_text("Главное меню", reply_markup=main_menu_keyboard())
        return






async def animate(msg, fmt: str, resolution: str = "1k"):
    dots = ["", ".", "..", "..."]
    i = 0
    try:
        while True:
            await asyncio.sleep(2)
            try:
                await msg.edit_text(f"<b>Генерация...</b> {dots[i % 4]}\n<i>Формат: {fmt} | Разрешение: {resolution.upper()}</i>", parse_mode=ParseMode.HTML)
            except:
                pass
            i += 1
    except asyncio.CancelledError:
        pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo with caption - use Text to Image with caption as prompt"""
    if is_old_message(update):
        return
    user = update.effective_user
    message = update.message
    
    if not message:
        return
    
    prompt = message.caption
    
    if not prompt:
        await message.reply_text(
            "📝 Добавь описание для генерации!\n\n"
            "Пример: отправь фото с подписью 'девушка в аниме стиле'"
        )
        return
    
    logger.info(f"[User {user.id}] Photo prompt: {prompt[:40]}...")
    
    # Use Text to Image with auto format detection from photo
    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = bytes(await file.download_as_bytearray())
    aspect = await detect_aspect_ratio(photo_bytes)
    
    msg = await message.reply_text(
        f"<b>Генерация по описанию...</b>\n<i>Формат: {aspect}</i>\n\n"
        "⚠️ Image-to-Image временно недоступен, использую текст",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )
    
    animation = asyncio.create_task(animate(msg, aspect))
    
    try:
        # Text to Image only (no image_data)
        result, text_resp = await generate(prompt, aspect, user.id)
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user.id)
        await safe_edit_text(msg, "Закончился баланс")
    elif result == "server_down":
        await send_error_sticker(context, user.id)
        await safe_edit_text(msg, "Сервер не отвечает. Попробуйте позже.")
    elif result:
        await send_result(context, user.id, result, msg)
    else:
        await send_error_sticker(context, user.id)
        if text_resp:
            cleaned_text = text_resp.replace('**', '').replace('\n\n', '\n')
            if len(cleaned_text) > 800:
                cleaned_text = cleaned_text[:800] + "..."
            await safe_edit_text(msg, f"<b>Не удалось отредактировать.</b>\n\n{html.escape(cleaned_text)}", parse_mode='HTML')
        else:
            await safe_edit_text(msg, "Не удалось отредактировать")

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
        "<b>Обработка...</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    
    animation = asyncio.create_task(animate(msg, "edit"))
    
    try:
        result, text_resp = await generate(prompt, "auto", user.id, image_data=bytes(photo_bytes))
    finally:
        animation.cancel()
    
    if result == "no_balance":
        await send_error_sticker(context, user.id)
        await safe_edit_text(msg, "Закончился баланс")
    elif result == "server_down":
        await send_error_sticker(context, user.id)
        await safe_edit_text(msg, "Сервер не отвечает. Попробуйте позже.")
    elif result:
        await send_result(context, user.id, result, msg)
    else:
        await send_error_sticker(context, user.id)
        if text_resp:
            cleaned_text = text_resp.replace('**', '').replace('\n\n', '\n')
            if len(cleaned_text) > 800:
                cleaned_text = cleaned_text[:800] + "..."
            await safe_edit_text(msg, f"<b>Не удалось отредактировать.</b>\n\n{html.escape(cleaned_text)}", parse_mode='HTML')
        else:
            await safe_edit_text(msg, "Не удалось отредактировать")
    
    return True


async def send_result(context, user_id: int, result, msg, original_msg_id: int = None):
    """
    Send result image. result can be bytes or base64 string.
    Replies to original_msg_id if possible.
    """
    
    UPDATE_TEXT = (
        "\n\n📢 <b>БОТ ОБНОВЛЯЕТСЯ!</b>\n"
        "Подождите чуть-чуть, мы внедряем новые модели, функции и исправляем баги.\n"
        "Наше сообщество: t.me/Geometry90"
    )

    try:
        # Handle both bytes and base64 string
        if isinstance(result, bytes):
            image_data = result
        else:
            image_data = base64.b64decode(result)
        
        size_mb = len(image_data) / (1024 * 1024)
        
        if size_mb >= 4:
            preview_data = await compress_for_preview(image_data)
        else:
            preview_data = image_data
        
        bio_photo = io.BytesIO(preview_data)
        bio_photo.name = "preview.jpg"
        
        try:
            await context.bot.send_photo(
                chat_id=user_id, 
                photo=bio_photo, 
                caption=f"<b>Результат</b>{UPDATE_TEXT}", 
                parse_mode='HTML',
                reply_to_message_id=original_msg_id
            )
        except Exception as e:
            logger.warning(f"Preview send failed: {e}")
            # If reply fails (e.g. msg deleted), try sending without reply
            try:
                await context.bot.send_photo(
                    chat_id=user_id, 
                    photo=bio_photo, 
                    caption=f"<b>Результат</b>{UPDATE_TEXT}", 
                    parse_mode='HTML'
                )
            except Exception as e2:
                 logger.error(f"Fallback send failed: {e2}")
                 await context.bot.send_message(chat_id=user_id, text="⚠️ Ошибка отправки превью.")

        bio_doc = io.BytesIO(image_data)
        bio_doc.name = "bananchik_4k.png" if size_mb >= 10 else "bananchik.png"
        
        try:
            await context.bot.send_document(
                chat_id=user_id, 
                document=bio_doc, 
                caption=f"Оригинал ({size_mb:.1f} MB)",
                reply_markup=main_menu_keyboard(),
                reply_to_message_id=original_msg_id
            )
        except:
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
        await safe_edit_text(msg, "Ошибка отправки")

async def post_init(application: Application):
    """
    Initial check for accounts and startup tasks.
    """
    from account_manager import get_manager
    manager = get_manager()
    stats = manager.get_stats()
    
    logger.info("=" * 40)
    logger.info("🍌 Starting Bananchik Bot...")
    logger.info(f"📊 Users: {stats['users_assigned']} | Accounts: {stats['total_accounts']} (with quota: {stats['accounts_with_quota']})")
    logger.info(f"💎 Total premium: {stats['total_premium_quota']}")
    
    # Check pool on startup
    MIN_ACCOUNTS = 5
    active_accounts = stats['accounts_with_quota']
    
    if active_accounts < MIN_ACCOUNTS:
        need = MIN_ACCOUNTS - active_accounts
        logger.info(f"🔄 Pool low! Starting background creation for {need} accounts...")
        for _ in range(need):
            asyncio.create_task(manager.auto_create_account())

def main():
    global BOT_START_TIME
    BOT_START_TIME = time.time()
    
    trequest = HTTPXRequest(connection_pool_size=100, connect_timeout=30.0, read_timeout=30.0)
    
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(256).request(trequest).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("g", cmd_generate))
    app.add_handler(CommandHandler("feedback", cmd_feedback))
    app.add_handler(CommandHandler("stats", cmd_stats))
    # app.add_handler(CallbackQueryHandler(on_rating, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot configured and ready to poll!")
    app.run_polling()

if __name__ == '__main__':
    main()
