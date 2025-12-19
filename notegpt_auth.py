"""
NoteGPT Auto-Registration [Optimized & Fast 🚀]
"""

import sys
# Force UTF-8 encoding for Windows console output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import aiohttp
import asyncio
import json
import re
import time
import random
import string
import base64
import os
from datetime import datetime
from playwright.async_api import async_playwright

# ============== CONFIGURATION ==============
TEMPMAIL_BASE = "https://tempmail.id.vn"
NOTEGPT_BASE = "https://notegpt.io"
TEMPMAIL_DOMAINS = ["hathitrannhien.edu.vn", "tempmail.id.vn"]

# ============== UTILS ==============

def generate_username(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_password(length=12):
    return ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=length))

def generate_guid():
    ts = int(time.time() * 1000)
    part1 = random.randint(10, 99)
    part2 = random.randint(10000000, 99999999)
    raw = f"{ts}|{part1}|{part2}"
    return base64.b64encode(raw.encode()).decode()

def log(msg, level="INFO"):
    """Log messages with emojis and minimal noise."""
    ts = datetime.now().strftime("%H:%M:%S")
    
    # Emoji mapping
    emojis = {
        "INFO": "🔹",
        "OK": "✅",
        "WARN": "⚠️",
        "ERROR": "❌",
        "BROWSER": "🌐",
        "MAIL": "📧",
        "AUTH": "🔐",
        "WAIT": "⏳",
        "ACTION": "⚡"
    }
    
    icon = emojis.get(level, "🔹")
    print(f"['{ts}'] {icon} {msg}")

# ============== TEMPMAIL API ==============

class TempMailClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.csrf_token = None
        self.home_snapshot = None
        self.inbox_snapshot = None
        self.mail_id = None
        self.email = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
    
    async def init_session(self):
        log("Connecting to TempMail...", "INFO")
        async with self.session.get(f"{TEMPMAIL_BASE}/en", headers=self.headers) as resp:
            html = await resp.text()
            
            csrf_match = re.search(r'data-csrf="([^"]+)"', html)
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
            else:
                log("TempMail: CSRF not found!", "ERROR")
                return False
            
            import html as html_module
            snapshot_match = re.search(r'wire:snapshot="([^"]*countMail[^"]*)"', html)
            if snapshot_match:
                self.home_snapshot = html_module.unescape(snapshot_match.group(1))
            else:
                log("TempMail: Home snapshot not found!", "ERROR")
                return False
            
            return True
    
    async def create_email(self, username: str = None, domain: str = "hathitrannhien.edu.vn"):
        username = username or generate_username()
        self.email = f"{username}@{domain}"
        log(f"Creating email: {self.email}...", "ACTION")
        
        payload = {
            "_token": self.csrf_token,
            "components": [{
                "snapshot": self.home_snapshot,
                "updates": {"domain": domain, "customMail": username},
                "calls": [{"path": "", "method": "saveCustomMail", "params": []}]
            }]
        }
        
        headers = {**self.headers, "Content-Type": "application/json", "X-Livewire": "true"}
        
        async with self.session.post(f"{TEMPMAIL_BASE}/en/livewire/update", json=payload, headers=headers) as resp:
            if resp.status == 200:
                log(f"Email created: {self.email}", "OK")
                await self._load_inbox()
                return self.email
            else:
                log(f"Failed to create email: {resp.status}", "ERROR")
                return None
    
    async def _load_inbox(self):
        async with self.session.get(f"{TEMPMAIL_BASE}/en/inbox", headers=self.headers) as resp:
            html = await resp.text()
            import html as html_module
            snapshot_match = re.search(r'wire:snapshot="([^"]*temp-mail\.inbox[^"]*)"', html) or re.search(r'wire:snapshot="([^"]*mailId[^"]*)"', html)
            
            if snapshot_match:
                self.inbox_snapshot = html_module.unescape(snapshot_match.group(1))
            else:
                log("TempMail: Inbox snapshot warning", "WARN")
    
    async def check_inbox(self):
        if not self.inbox_snapshot: return []
        
        payload = {
            "_token": self.csrf_token,
            "components": [{"snapshot": self.inbox_snapshot, "updates": {}, "calls": []}]
        }
        
        headers = {**self.headers, "Content-Type": "application/json", "X-Livewire": "true"}
        
        async with self.session.post(f"{TEMPMAIL_BASE}/en/livewire/update", json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("components"):
                    new_snap = data["components"][0].get("snapshot")
                    if new_snap: self.inbox_snapshot = new_snap
                
                html = data.get("components", [{}])[0].get("effects", {}).get("html", "")
                if "No mail yet" not in html and "fi-ta-row" in html:
                    return [{"has_mail": True, "html": html}]
                return []
            return []
    
    async def get_email_content(self):
        payload = {
            "_token": self.csrf_token,
            "components": [{"snapshot": self.inbox_snapshot, "updates": {}, "calls": []}]
        }
        headers = {**self.headers, "Content-Type": "application/json", "X-Livewire": "true"}
        
        async with self.session.post(f"{TEMPMAIL_BASE}/en/livewire/update", json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                html = data.get("components", [{}])[0].get("effects", {}).get("html", "")
                
                message_match = re.search(r'href="[^"]*(/message/[a-f0-9-]+)"', html)
                if message_match:
                    message_url = f"{TEMPMAIL_BASE}{message_match.group(1)}"
                    async with self.session.get(message_url, headers=self.headers) as msg_resp:
                        if msg_resp.status == 200:
                            return await msg_resp.text()
        return None

    async def wait_for_email(self, timeout=120, interval=1):
        log(f"Waiting for email ({timeout}s)...", "WAIT")
        start = time.time()
        while time.time() - start < timeout:
            mails = await self.check_inbox()
            if mails:
                log("Mail received!", "MAIL")
                content = await self.get_email_content()
                return {"has_mail": True, "html": content} if content else mails[0]
            await asyncio.sleep(interval)
        log("Email wait timed out", "ERROR")
        return None

# ============== NOTEGPT API ==============

class NoteGPTClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.x_guid = generate_guid()
        self.csrf_token = None
        self.user_id = None
        self.cookies = {}
    
    def get_headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
            "x-guid": self.x_guid,
            "Origin": NOTEGPT_BASE,
            "Referer": f"{NOTEGPT_BASE}/user/register"
        }
    
    async def init_session(self):
        log("Initializing NoteGPT session...", "INFO")
        async with self.session.get(f"{NOTEGPT_BASE}/user/register", headers=self.get_headers()) as resp:
            html = await resp.text()
            # Attempt to find CSRF token
            csrf_match = re.search(r'name="_csrf"\s+content="([^"]+)"', html) or \
                         re.search(r'name="csrf-token"\s+content="([^"]+)"', html) or \
                         re.search(r'"_csrf"\s*:\s*"([^"]+)"', html)
            
            if csrf_match:
                self.csrf_token = csrf_match.group(1)
            return True
    
    async def register(self, email: str, password: str):
        log(f"Registering account: {email}", "ACTION")
        headers = self.get_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.csrf_token: headers["X-CSRF-Token"] = self.csrf_token
        
        data = {
            "User[email]": email,
            "User[password]": password,
            "_csrf": self.csrf_token or ""
        }
        
        async with self.session.post(f"{NOTEGPT_BASE}/user/register", data=data, headers=headers, allow_redirects=False) as resp:
            if resp.status in [200, 302, 303]:
                log("Registration form submitted successfully", "OK")
                return True
            log(f"Registration failed: {resp.status}", "ERROR")
            return False
    
    async def confirm_email(self, token: str):
        log("Confirming email...", "ACTION")
        async with self.session.get(
            f"{NOTEGPT_BASE}/user/confirm-email",
            params={"token": token, "type": ""},
            headers=self.get_headers(),
            allow_redirects=True
        ) as resp:
            if "x-uid" in resp.headers:
                self.user_id = resp.headers["x-uid"]
                log(f"User ID confirmed: {self.user_id}", "OK")
            return resp.status == 200
    
    async def login(self, email: str, password: str):
        log("Logging in via API...", "AUTH")
        headers = self.get_headers()
        headers["Content-Type"] = "application/json"
        
        payload = {
            "email": email, "password": password,
            "client_type": 0, "client_id": "", "product_mark": "64"
        }
        
        url = f"{NOTEGPT_BASE}/api/v1/login-forwarding"
        async with self.session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("code") in ["100000", 100000]:
                    log("Login successful", "OK")
                    
                    jwt_token = resp.headers.get("X-Token")
                    if jwt_token:
                        await self._sync_session(jwt_token)
                    return True
            log("Login failed", "ERROR")
            return False
    
    async def _sync_session(self, jwt_token: str):
        headers = self.get_headers()
        sync_url = f"{NOTEGPT_BASE}/user/platform-communication/sync-user-status"
        params = {"token": f'"{jwt_token}"', "redirect_url": f"{NOTEGPT_BASE}/pricing"}
        
        async with self.session.get(sync_url, params=params, headers=headers) as resp:
             pass # Just triggering the cookie set
        
        # Access pricing to finalize cookies
        async with self.session.get(f"{NOTEGPT_BASE}/pricing", headers=headers) as resp:
             pass

    async def get_plan_quota(self):
        async with self.session.get(f"{NOTEGPT_BASE}/api/v2/plan-quota", headers=self.get_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {})
            return None

    # ============== BROWSER AUTOMATION ==============
    
    async def activate_education_plan_browser(self, email: str, password: str):
        """Optimized browser automation for Plan Activation"""
        log("Starting Browser Automation 🚀", "BROWSER")
        
        async with async_playwright() as p:
            # 🚀 FARM MODE: Headless + Low Resource Usage
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-animations',
                    '--no-sandbox',
                    '--disable-extensions'
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1024, "height": 768},
                java_script_enabled=True,
                bypass_csp=True
            )
            # Block images to save resources
            await context.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda route: route.abort())
            page = await context.new_page()
            
            try:
                # 1. Go to Home
                log(f"Navigating to {NOTEGPT_BASE}...", "BROWSER")
                await page.goto(f"{NOTEGPT_BASE}/", timeout=30000)
                
                # Close Popups Helper
                async def aggressive_popup_close():
                    try:
                        # Close Christmas/Gift popups
                        await page.evaluate('''() => {
                            const selectors = [
                                ".i-hugeicons\\\\:cancel-circle", "span.iconify[class*='cancel']",
                                "div[data-v-1d431a3d] span.iconify", "div[data-v-390d3631]",
                                "img[alt='Gift']", "span[class*='x-mark']"
                            ];
                            selectors.forEach(sel => {
                                const el = document.querySelector(sel);
                                if(el) el.click();
                            });
                        }''')
                    except: pass

                await aggressive_popup_close()

                # 2. Login
                log("Clicking Login...", "ACTION")
                try:
                    await page.click("text=Log in", timeout=5000)
                except:
                    await page.click("text=Login", timeout=5000)

                log("Selecting Email Login...", "ACTION")
                try:
                    await page.click("text=Log in with Email", timeout=3000)
                except: pass # Might be default

                log("Entering Credentials...", "AUTH")
                await page.fill("input[type='email']", email)
                await page.fill("input[type='password']", password)
                await page.click("button[type='submit']")

                log("Waiting for login...", "WAIT")
                await page.wait_for_load_state("networkidle")
                await aggressive_popup_close()

                # 3. Go to Pricing
                log("Navigating to Pricing...", "BROWSER")
                await page.goto(f"{NOTEGPT_BASE}/pricing")
                await aggressive_popup_close()

                # 4. Education Tab + Free Button with RETRY LOGIC
                MAX_RETRIES = 5
                for attempt in range(1, MAX_RETRIES + 1):
                    log(f"🔄 Attempt {attempt}/{MAX_RETRIES}: Activating Education Plan...", "ACTION")
                    
                    # Click Education Tab
                    try:
                         await page.click("text=Education", timeout=5000)
                    except: 
                         await page.evaluate("() => { const el = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Education')); if(el) el.click(); }")

                    await asyncio.sleep(1)

                    # Check if already active
                    content = await page.content()
                    if "Successfully Get 1 month Free" in content:
                        log("Plan already activated! ✅", "OK")
                        await browser.close()
                        return {"status": "success", "message": "already_activated"}

                    # Click Free Button
                    clicked = await page.evaluate('''() => {
                        const buttons = [...document.querySelectorAll('button')];
                        const target = buttons.find(b => b.textContent.includes('Get 1 month Free') || b.textContent.includes('Free Now'));
                        if (target) {
                            target.scrollIntoView();
                            target.click();
                            return true;
                        }
                        return false;
                    }''')
                    
                    if not clicked:
                        try:
                            await page.locator("button:has-text('Free')").first.click(timeout=2000)
                            clicked = True
                        except:
                            pass
                    
                    if clicked:
                        log("Clicked! Waiting for result...", "WAIT")
                        await asyncio.sleep(3)
                        
                        # Verify activation
                        education_status = await page.evaluate('''async () => {
                            try {
                                const resp = await fetch("/api/v2/payments/check-user-permissions");
                                const json = await resp.json();
                                return json.data.education.status;
                            } catch(e) { return null; }
                        }''')
                        
                        if education_status == "active":
                            log("Education plan ACTIVATED SUCCESSFULLY! 🎉", "OK")
                            await browser.close()
                            return {"status": "success"}
                        else:
                            log(f"Activation status: {education_status}", "WARN")
                    
                    # If not activated, reload and retry
                    if attempt < MAX_RETRIES:
                        log("🔁 Reloading page and retrying...", "WARN")
                        await page.reload()
                        await aggressive_popup_close()
                        await asyncio.sleep(1)
                    else:
                        log("❌ All attempts failed", "ERROR")
                else:
                    log("Could not find Free button", "ERROR")

                await browser.close()
                return {"status": "failed"}
                
            except Exception as e:
                log(f"Browser Error: {e}", "ERROR")
                await browser.close()
                return None


# ============== MAIN FLOW ==============

async def full_registration():
    log("Starting NoteGPT Registration Process 🚀", "INFO")
    
    conn = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=conn, cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        # 1. TempMail
        tempmail = TempMailClient(session)
        if not await tempmail.init_session(): return None
        
        email = await tempmail.create_email()
        if not email: return None
        
        password = generate_password()
        
        # 2. Register NoteGPT
        notegpt = NoteGPTClient(session)
        await notegpt.init_session()
        
        if not await notegpt.register(email, password): return None
        
        # 3. Confirm Email
        mail = await tempmail.wait_for_email()
        if not mail: return None
        
        token_match = re.search(r'confirm-email\?token=([^&"\']+)', mail.get("html", ""))
        if not token_match:
            log("Token not found in email", "ERROR")
            return None
            
        if not await notegpt.confirm_email(token_match.group(1)): return None
        
        # 4. Login & Activate
        await notegpt.login(email, password)
        
        education_result = await notegpt.activate_education_plan_browser(email, password)
        
        # 5. Get Quota Info
        plan_quota = await notegpt.get_plan_quota()
        
        # Simplify quota
        simple_quota = {}
        if plan_quota:
            simple_quota = {
                "quota_left": plan_quota.get("quota_left"),
                "premium_quota_left": plan_quota.get("premium_quota_left"),
                "is_educational": plan_quota.get("is_educational")
            }

        result = {
            "email": email,
            "password": password,
            "user_id": notegpt.user_id,
            "education_plan": education_result,
            "plan_quota": simple_quota
        }
        
        log(f"Process Complete! 🏁\nEmail: {email}\nPassword: {password}", "OK")
        if plan_quota:
            log(f"Plan Limit: {plan_quota.get('total_limit', 'N/A')} | Used: {plan_quota.get('used', 'N/A')}", "INFO")
            
        return result

if __name__ == "__main__":
    result = asyncio.run(full_registration())
    if result:
        filename = "notegpt_account.json"
        existing_data = []
        
        # Read existing data
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        loaded = json.loads(content)
                        if isinstance(loaded, list):
                            existing_data = loaded
                        else:
                            existing_data = [loaded]
            except Exception as e:
                log(f"Error reading existing accounts: {e}", "WARN")
        
        # Append new account
        existing_data.append(result)
        
        # Write back
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
            
        log(f"Account saved to {filename} (Total: {len(existing_data)})", "OK") 
