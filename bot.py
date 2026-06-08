"""
Telegram Bot with Selenium Automation for 8-Step Signup Wizard
Designed for Render.com deployment with Gunicorn + Flask
"""

import logging
import os
import string
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import threading

from flask import Flask, request, jsonify
from telegram import Update, ForceReply
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telegram.constants import ChatAction

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Conversation states
WAITING_FOR_OTP = 1
AWAITING_USER_INPUT = 2

# Timeouts (in seconds)
ELEMENT_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 20

# Config (update with your values)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SIGNUP_URL = os.getenv("SIGNUP_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", 8000))

# Global bot instance
telegram_bot = None


class SignupAutomation:
    """Manages Selenium WebDriver and signup automation logic"""

    def __init__(self, headless: bool = True):
        """Initialize Chrome WebDriver with Render-compatible options"""
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = headless
        self._initialize_driver()

    def _initialize_driver(self):
        """Set up Chrome WebDriver with Render-compatible options"""
        try:
            options = webdriver.ChromeOptions()

            # Render.com compatibility options
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            # Additional stability options
            options.add_argument("--disable-gpu")
            options.add_argument("--single-process")
            options.add_argument("--disable-web-resources")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # Set user agent to avoid detection
            options.add_argument(
                "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            )

            # Disable logging
            options.add_argument("--disable-logging")
            options.add_argument("--disable-extensions")

            # Use webdriver-manager to automatically download ChromeDriver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            logger.info("Chrome WebDriver initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def _wait_for_element(
        self,
        by: By,
        value: str,
        timeout: int = ELEMENT_TIMEOUT,
        condition: str = "presence"
    ) -> bool:
        """
        Wait for element with explicit waits
        
        Args:
            by: Selenium By locator
            value: Locator value
            timeout: Wait timeout in seconds
            condition: "presence", "visibility", or "clickable"
        
        Returns:
            True if element found, False otherwise
        """
        try:
            wait = WebDriverWait(self.driver, timeout)

            if condition == "clickable":
                element = wait.until(EC.element_to_be_clickable((by, value)))
            elif condition == "visibility":
                element = wait.until(EC.visibility_of_element_located((by, value)))
            else:  # presence
                element = wait.until(EC.presence_of_element_located((by, value)))

            logger.info(f"✓ Element found: {by} = {value}")
            return True

        except TimeoutException:
            logger.warning(f"✗ Timeout waiting for element: {by} = {value}")
            return False
        except StaleElementReferenceException:
            logger.warning(f"✗ Stale element reference: {by} = {value}")
            return False

    def _click_element(self, by: By, value: str, timeout: int = ELEMENT_TIMEOUT) -> bool:
        """Click an element with explicit wait for clickability"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.element_to_be_clickable((by, value)))
            element.click()
            logger.info(f"✓ Clicked element: {by} = {value}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to click element {by} = {value}: {e}")
            return False

    def _send_keys(
        self,
        by: By,
        value: str,
        keys: str,
        timeout: int = ELEMENT_TIMEOUT,
        clear_first: bool = True
    ) -> bool:
        """Send keys to an input element"""
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located((by, value)))

            if clear_first:
                element.clear()

            element.send_keys(keys)
            logger.info(f"✓ Entered text in: {by} = {value}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to send keys to {by} = {value}: {e}")
            return False

    def open_signup_page(self) -> bool:
        """Step 0: Open the signup page"""
        try:
            logger.info(f"Opening signup page: {SIGNUP_URL}")
            self.driver.get(SIGNUP_URL)
            logger.info("✓ Signup page loaded")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to open signup page: {e}")
            return False

    def step_1_click_email_signup(self) -> bool:
        """Step 1: Click 'Sign up with email address' button"""
        logger.info("STEP 1: Clicking 'Sign up with email address'")

        # Replace with your actual locator
        if self._click_element(By.XPATH, "//button[contains(text(), 'Sign up with email')]"):
            return True

        # Fallback locators
        if self._click_element(By.ID, "email-signup-btn"):
            return True

        logger.error("Could not find email signup button")
        return False

    def step_2_enter_email(self, email: str) -> bool:
        """Step 2: Enter email and click Next"""
        logger.info("STEP 2: Entering email and proceeding")

        # Wait for and fill email input
        if not self._send_keys(By.NAME, "email", email):
            if not self._send_keys(By.ID, "email-input", email):
                logger.error("Could not find email input field")
                return False

        # Click Next button
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button")
                return False

        return True

    def step_3_enter_otp(self, otp: str) -> bool:
        """Step 3: Enter OTP and click Next"""
        logger.info("STEP 3: Entering OTP")

        # Wait for OTP input field
        if not self._send_keys(By.NAME, "otp", otp):
            if not self._send_keys(By.ID, "otp-input", otp):
                if not self._send_keys(By.XPATH, "//input[@type='text' and @placeholder*='OTP']", otp):
                    logger.error("Could not find OTP input field")
                    return False

        # Click Next
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button after OTP")
                return False

        return True

    def step_4_set_password(self) -> Tuple[bool, str]:
        """Step 4: Generate password and enter it"""
        logger.info("STEP 4: Setting password")

        # Generate strong 12-character password
        password = self._generate_password()
        logger.info(f"Generated password (length: {len(password)})")

        # Send password
        if not self._send_keys(By.NAME, "password", password):
            if not self._send_keys(By.ID, "password-input", password):
                if not self._send_keys(By.XPATH, "//input[@type='password']", password):
                    logger.error("Could not find password input field")
                    return False, ""

        # Click Next
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button after password")
                return False, ""

        return True, password

    def step_5_set_dob(self) -> bool:
        """Step 5: Set Date of Birth (18+ years old)"""
        logger.info("STEP 5: Setting Date of Birth")

        # Generate random DOB between 1990-2005 (ensuring 18+ years)
        year = random.randint(1990, 2005)
        month = random.randint(1, 12)
        day = random.randint(1, 28)  # Use 28 to avoid month-end issues

        dob_str = f"{day:02d}-{month:02d}-{year}"
        logger.info(f"Generated DOB: {dob_str} (Age: {datetime.now().year - year}+)")

        # Try different DOB input methods
        if not self._send_keys(By.NAME, "dob", dob_str):
            if not self._send_keys(By.ID, "dob-input", dob_str):
                if not self._send_keys(By.XPATH, "//input[@type='date']", f"{year}-{month:02d}-{day:02d}"):
                    # If it's a date picker, try selecting dropdowns
                    if self._select_dob_from_dropdowns(day, month, year):
                        pass
                    else:
                        logger.error("Could not find DOB input field")
                        return False

        # Click Next
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button after DOB")
                return False

        return True

    def _select_dob_from_dropdowns(self, day: int, month: int, year: int) -> bool:
        """Helper method to select DOB from dropdown menus"""
        try:
            # Select year dropdown
            year_select = WebDriverWait(self.driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "year"))
            )
            year_select.send_keys(str(year))

            # Select month dropdown
            month_select = WebDriverWait(self.driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "month"))
            )
            month_select.send_keys(str(month))

            # Select day dropdown
            day_select = WebDriverWait(self.driver, ELEMENT_TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "day"))
            )
            day_select.send_keys(str(day))

            logger.info("✓ DOB set via dropdowns")
            return True

        except Exception as e:
            logger.warning(f"Could not select DOB from dropdowns: {e}")
            return False

    def step_6_enter_full_name(self, full_name: str) -> bool:
        """Step 6: Enter full name and click Next"""
        logger.info("STEP 6: Entering full name")

        if not self._send_keys(By.NAME, "full_name", full_name):
            if not self._send_keys(By.ID, "name-input", full_name):
                if not self._send_keys(By.XPATH, "//input[@placeholder*='Full Name']", full_name):
                    logger.error("Could not find full name input field")
                    return False

        # Click Next
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button after full name")
                return False

        return True

    def step_7_enter_username(self, username: str) -> bool:
        """Step 7: Enter username, wait for validation tick, and click Next"""
        logger.info("STEP 7: Entering username")

        if not self._send_keys(By.NAME, "username", username):
            if not self._send_keys(By.ID, "username-input", username):
                if not self._send_keys(By.XPATH, "//input[@placeholder*='username']", username):
                    logger.error("Could not find username input field")
                    return False

        # Wait for green validation tick (adjust locator as needed)
        logger.info("Waiting for username validation...")
        import time
        time.sleep(2)

        if not self._wait_for_element(
            By.XPATH, "//span[contains(@class, 'tick')] | //i[contains(@class, 'check')]"
        ):
            logger.warning("Validation tick not found, proceeding anyway")

        # Click Next
        if not self._click_element(By.XPATH, "//button[contains(text(), 'Next')]"):
            if not self._click_element(By.ID, "next-btn"):
                logger.error("Could not find Next button after username")
                return False

        return True

    def step_8_agree_terms(self) -> bool:
        """Step 8: Agree to Terms and Policies"""
        logger.info("STEP 8: Agreeing to Terms and Policies")

        # Wait for Terms page to fully load
        if not self._wait_for_element(By.XPATH, "//button[contains(text(), 'I agree')]", condition="presence"):
            logger.error("Terms page did not load")
            return False

        # Click "I agree" button
        if not self._click_element(By.XPATH, "//button[contains(text(), 'I agree')]"):
            if not self._click_element(By.ID, "agree-btn"):
                logger.error("Could not find 'I agree' button")
                return False

        logger.info("✓ Terms and Policies agreed")
        return True

    def cleanup(self):
        """Clean up browser session"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("✓ WebDriver cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up WebDriver: {e}")

    @staticmethod
    def _generate_password() -> str:
        """Generate a strong 12-character password"""
        characters = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(random.choice(characters) for _ in range(12))
        return password


class TelegramSignupBot:
    """Manages Telegram bot interactions"""

    def __init__(self, token: str):
        self.token = token
        self.app: Optional[Application] = None
        # Store user sessions: {user_id: {"full_name": "...", "username": "...", "email": "...", "automation": SignupAutomation}}
        self.user_sessions: Dict[int, Dict] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        help_text = (
            "🤖 <b>Instagram-like Signup Automation Bot</b>\n\n"
            "Use this bot to automate the 8-step signup wizard.\n\n"
            "<b>Command:</b>\n"
            "/create &lt;FullName&gt; &lt;Username&gt; &lt;Email&gt;\n\n"
            "<b>Example:</b>\n"
            "/create \"John Doe\" johndoe john@example.com\n"
        )
        await update.message.reply_html(help_text)

    async def create_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /create command to start signup automation"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # Parse command arguments
        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Invalid format.\n"
                "Usage: /create <FullName> <Username> <Email>\n"
                "Example: /create \"John Doe\" johndoe john@example.com"
            )
            return AWAITING_USER_INPUT

        full_name = context.args[0].strip('"')
        username = context.args[1]
        email = context.args[2]

        logger.info(f"Starting signup for user {user_id}: {email}")

        try:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

            # Initialize Selenium automation
            automation = SignupAutomation(headless=True)
            self.user_sessions[user_id] = {
                "full_name": full_name,
                "username": username,
                "email": email,
                "automation": automation,
                "chat_id": chat_id,
                "password": None,
            }

            await update.message.reply_text(
                f"🚀 Starting signup automation for {email}...\n"
                "Please wait..."
            )

            # Step 0: Open signup page
            if not automation.open_signup_page():
                raise Exception("Failed to open signup page")

            await update.message.reply_text("✓ Step 1: Opened signup page")

            # Step 1: Click email signup
            if not automation.step_1_click_email_signup():
                raise Exception("Failed at Step 1: Could not click email signup button")

            await update.message.reply_text("✓ Step 2: Email signup clicked")

            # Step 2: Enter email
            if not automation.step_2_enter_email(email):
                raise Exception("Failed at Step 2: Could not enter email")

            await update.message.reply_text("✓ Step 3: Email entered, waiting for OTP...")

            # Step 3: Request OTP from user
            await update.message.reply_text(
                "📧 Check your email for the OTP.\n"
                "Send the OTP here:"
            )
            return WAITING_FOR_OTP

        except Exception as e:
            logger.error(f"Error in create_account: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

            # Cleanup on error
            if user_id in self.user_sessions:
                self.user_sessions[user_id]["automation"].cleanup()
                del self.user_sessions[user_id]

            return AWAITING_USER_INPUT

    async def handle_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle OTP input from user"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        otp = update.message.text.strip()

        if user_id not in self.user_sessions:
            await update.message.reply_text("❌ No active signup session. Start with /create command.")
            return AWAITING_USER_INPUT

        session = self.user_sessions[user_id]
        automation = session["automation"]

        try:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

            logger.info(f"Processing OTP for user {user_id}")

            # Step 3: Enter OTP
            if not automation.step_3_enter_otp(otp):
                raise Exception("Failed at Step 3: Could not enter OTP")

            await update.message.reply_text("✓ Step 4: OTP verified")

            # Step 4: Set password
            success, password = automation.step_4_set_password()
            if not success:
                raise Exception("Failed at Step 4: Could not set password")

            session["password"] = password
            await update.message.reply_text(f"✓ Step 5: Password set")

            # Step 5: Set DOB
            if not automation.step_5_set_dob():
                raise Exception("Failed at Step 5: Could not set DOB")

            await update.message.reply_text("✓ Step 6: DOB set")

            # Step 6: Enter full name
            if not automation.step_6_enter_full_name(session["full_name"]):
                raise Exception("Failed at Step 6: Could not enter full name")

            await update.message.reply_text("✓ Step 7: Full name entered")

            # Step 7: Enter username
            if not automation.step_7_enter_username(session["username"]):
                raise Exception("Failed at Step 7: Could not enter username")

            await update.message.reply_text("✓ Step 8: Username entered")

            # Step 8: Agree to terms
            if not automation.step_8_agree_terms():
                raise Exception("Failed at Step 8: Could not agree to terms")

            await update.message.reply_text("✓ Step 9: Terms agreed")

            # Success message
            success_message = (
                "✅ <b>Signup Completed Successfully!</b>\n\n"
                f"📧 <b>Email:</b> {session['email']}\n"
                f"👤 <b>Username:</b> {session['username']}\n"
                f"🔐 <b>Password:</b> <code>{password}</code>\n\n"
                "Save your password securely!"
            )
            await update.message.reply_html(success_message)

            # Cleanup
            automation.cleanup()
            del self.user_sessions[user_id]

            return AWAITING_USER_INPUT

        except Exception as e:
            logger.error(f"Error processing OTP: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

            # Cleanup on error
            automation.cleanup()
            del self.user_sessions[user_id]

            return AWAITING_USER_INPUT

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle generic messages"""
        await update.message.reply_text(
            "Use /create command to start signup automation.\n"
            "Type /start for help."
        )

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log errors"""
        logger.error(f"Update {update} caused error {context.error}")

        # Cleanup sessions on fatal error
        if context.user_data and "user_id" in context.user_data:
            user_id = context.user_data["user_id"]
            if user_id in self.user_sessions:
                try:
                    self.user_sessions[user_id]["automation"].cleanup()
                except:
                    pass
                del self.user_sessions[user_id]

    def setup_handlers(self):
        """Setup conversation and message handlers"""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("create", self.create_account)],
            states={
                WAITING_FOR_OTP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_otp)
                ],
            },
            fallbacks=[CommandHandler("start", self.start)],
            allow_reentry=True,
        )

        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(conv_handler)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_error_handler(self.error_handler)

    async def initialize(self):
        """Initialize the bot"""
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot initialized and polling started")


# Flask Routes
@app.route("/", methods=["GET"])
def home():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Bot is running"}), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check for Render"""
    return jsonify({"status": "healthy"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Webhook endpoint for Telegram updates (optional)"""
    try:
        update = Update.de_json(request.get_json(), telegram_bot.app.bot)
        import asyncio
        asyncio.create_task(telegram_bot.app.process_update(update))
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/info", methods=["GET"])
def info():
    """Get bot info"""
    return jsonify({
        "status": "running",
        "signup_url": SIGNUP_URL,
        "active_sessions": len(telegram_bot.user_sessions) if telegram_bot else 0
    }), 200


def start_bot():
    """Start the Telegram bot in a separate thread"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_bot.initialize())


def main():
    """Main entry point"""
    global telegram_bot

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("TELEGRAM_BOT_TOKEN not set. Set it as an environment variable.")
        return

    if not SIGNUP_URL or SIGNUP_URL == "http://localhost:8000":
        logger.warning("SIGNUP_URL not set. Using default: http://localhost:8000")

    telegram_bot = TelegramSignupBot(TELEGRAM_BOT_TOKEN)

    # Start bot in a background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    logger.info(f"Starting Flask server on port {PORT}")
    # Run Flask app with Gunicorn (Gunicorn will call this)
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
