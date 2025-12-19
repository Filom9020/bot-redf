"""
NoteGPT Account Manager 🔐
SHARED POOL - all users share accounts
"""

import json
import os
import asyncio
from datetime import datetime
from typing import Optional

DATA_FILE = "user_accounts.json"

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    emojis = {"INFO": "🔹", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "ACCOUNT": "🔐"}
    print(f"[{ts}] {emojis.get(level, '🔹')} {msg}")

class AccountManager:
    def __init__(self):
        self.accounts = []  # Shared pool
        self.users = {}  # User settings only (resolution, boost)
        self.load()
    
    def load(self):
        """Load all data from files"""
        # Load main data file
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.accounts = data.get("accounts", [])
                self.users = data.get("users", {})
            except Exception as e:
                log(f"Error loading data: {e}", "ERROR")
        
        # Also merge from notegpt_account.json (created by notegpt_auth.py)
        if os.path.exists("notegpt_account.json"):
            try:
                with open("notegpt_account.json", "r", encoding="utf-8") as f:
                    new_accounts = json.load(f)
                
                if not isinstance(new_accounts, list):
                    new_accounts = [new_accounts]
                
                for acc in new_accounts:
                    email = acc.get("email")
                    # Check if not already in pool
                    if not any(a.get("email") == email for a in self.accounts):
                        flat = {
                            "email": email,
                            "password": acc.get("password"),
                            "premium_quota_left": acc.get("plan_quota", {}).get("premium_quota_left", 100)
                        }
                        self.accounts.append(flat)
                        log(f"Merged new account: {email}", "ACCOUNT")
                
                self.save()
            except Exception as e:
                log(f"Error merging accounts: {e}", "ERROR")
        
        log(f"Loaded {len(self.accounts)} accounts, {len(self.users)} users", "ACCOUNT")
    
    def save(self):
        """Save all data to single file"""
        data = {"accounts": self.accounts, "users": self.users}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_available_account(self) -> Optional[dict]:
        """Get ANY account with quota > 0 from shared pool"""
        for acc in self.accounts:
            if acc.get("premium_quota_left", 0) > 0:
                return acc
        return None
    
    def update_account_quota(self, email: str, quota: int):
        """Update quota for an account. Trigger preemptive creation if quota low."""
        LOW_QUOTA_THRESHOLD = 24  # Start creating new account when below this
        MIN_ACTIVE_ACCOUNTS = 2   # Minimum accounts we want active
        
        for acc in self.accounts:
            if acc.get("email") == email:
                old_quota = acc.get("premium_quota_left", 0)
                acc["premium_quota_left"] = quota
                self.save()
                
                # If quota exhausted, remove
                if quota <= 0:
                    log(f"Account {email} exhausted, removing...", "WARN")
                    self.remove_account(email)
                    return
                
                # Preemptive creation: if quota just dropped below threshold
                if quota < LOW_QUOTA_THRESHOLD and old_quota >= LOW_QUOTA_THRESHOLD:
                    active = sum(1 for a in self.accounts if a.get("premium_quota_left", 0) >= LOW_QUOTA_THRESHOLD)
                    if active < MIN_ACTIVE_ACCOUNTS:
                        log(f"⚠️ Quota low ({quota})! Creating backup account...", "WARN")
                        asyncio.create_task(self.auto_create_account())
                return
    
    def remove_account(self, email: str):
        """Remove account from pool"""
        self.accounts = [a for a in self.accounts if a.get("email") != email]
        self.save()
        log(f"Removed: {email}", "ACCOUNT")
        
        # Check if pool is getting low
        active = sum(1 for a in self.accounts if a.get("premium_quota_left", 0) > 0)
        if active < 2:
            log(f"Pool low! Only {active} active accounts. Creating new...", "WARN")
            asyncio.create_task(self.auto_create_account())
    
    def add_account(self, account: dict):
        """Add new account to pool"""
        self.accounts.append(account)
        self.save()
        log(f"Added: {account.get('email')}", "ACCOUNT")
    
    async def auto_create_account(self):
        """Auto-create new account when pool is low"""
        log("🔄 Starting account creation...", "ACCOUNT")
        
        try:
            process = await asyncio.create_subprocess_exec(
                "python", "notegpt_auth.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            if process.returncode == 0:
                log("✅ New account created!", "OK")
                # Merge from notegpt_account.json
                try:
                    with open("notegpt_account.json", "r", encoding="utf-8") as f:
                        new_accounts = json.load(f)
                    
                    for acc in (new_accounts if isinstance(new_accounts, list) else [new_accounts]):
                        flat = {
                            "email": acc.get("email"),
                            "password": acc.get("password"),
                            "premium_quota_left": acc.get("plan_quota", {}).get("premium_quota_left", 100)
                        }
                        if not any(a.get("email") == flat["email"] for a in self.accounts):
                            self.accounts.append(flat)
                    self.save()
                    log(f"Pool: {len(self.accounts)} accounts", "OK")
                except Exception as e:
                    log(f"Merge error: {e}", "ERROR")
            else:
                log(f"Creation failed", "ERROR")
                
        except asyncio.TimeoutError:
            log("Creation timeout", "ERROR")
        except Exception as e:
            log(f"Error: {e}", "ERROR")
    
    # User settings (resolution, boost)
    def get_user_resolution(self, user_id: int) -> str:
        return self.users.get(str(user_id), {}).get("resolution", "1k")
    
    def set_user_resolution(self, user_id: int, resolution: str):
        key = str(user_id)
        if key not in self.users:
            self.users[key] = {}
        self.users[key]["resolution"] = resolution
        self.save()
    
    def get_user_boost(self, user_id: int) -> bool:
        return self.users.get(str(user_id), {}).get("boost", True)
    
    def set_user_boost(self, user_id: int, boost: bool):
        key = str(user_id)
        if key not in self.users:
            self.users[key] = {}
        self.users[key]["boost"] = boost
        self.save()
    
    def get_stats(self) -> dict:
        total = len(self.accounts)
        active = sum(1 for a in self.accounts if a.get("premium_quota_left", 0) > 0)
        total_quota = sum(a.get("premium_quota_left", 0) for a in self.accounts)
        return {
            "total_accounts": total,
            "accounts_with_quota": active,
            "total_premium_quota": total_quota,
            "users_assigned": len(self.users)
        }

# Global instance
_manager = None

def get_manager() -> AccountManager:
    global _manager
    if _manager is None:
        _manager = AccountManager()
    return _manager
