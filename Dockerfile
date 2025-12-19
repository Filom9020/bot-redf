# Use playwright's pre-built image with browsers
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install chromium

# Copy app files
COPY telegram_bot_simple.py .
COPY account_manager.py .
COPY notegpt_auth.py .

# Create empty data file if not exists
RUN echo '{"accounts": [], "users": {}}' > user_accounts.json

# Run the bot
CMD ["python", "telegram_bot_simple.py"]
