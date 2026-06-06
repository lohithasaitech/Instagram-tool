"""
Telegram Bot with Selenium Web Automation
Automates an 8-step multi-page signup wizard with explicit waits and user interaction
"""

import os
import re
import string
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SIGNUP_URL = os.getenv("SIGNUP_URL", "http://localhost:8000")  # Replace with your local URL
CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH")  # Optional: Path to chromedriver

# Conversation states
AWAITING_OTP = 1
AWAITING_COMMAND = 0


class SignupAutomation:
    """Handles Selenium-based signup automation with explicit waits"""

    def __init__(self, base_url: str = SIGNUP_URL, headless: bool = True):
        self.base_url = base_url
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.headless = headless
        self.generated_password: Optional[str] = None

    def setup_driver(self) -> None:
        """Initialize Chrome WebDriver with headless options"""
        chrome_options = ChromeOptions()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        try:
            if CHROME_DRIVER_PATH:
                service = Service(CHROME_DRIVER_PATH)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.wait = WebDriverWait(self.driver, timeout=15)
            logger.info("✓ Chrome WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"✗ Failed to initialize WebDriver: {str(e)}")
            raise

    def generate_password(self, length: int = 12) -> str:
        """Generate a strong random password"""
        characters = string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*"
        password = ''.join(random.choice(characters) for _ in range(length))
        self.generated_password = password
        logger.info(f"✓ Generated password: {password}")
        return password

    def generate_dob(self, min_year: int = 1990, max_year: int = 2005) -> Dict[str, int]:
        """Generate a random Date of Birth ensuring age 18+"""
        year = random.randint(min_year, max_year)
        month = random.randint(1, 12)
        day = random.randint(1, 28)  # Safe range for all months
        
        dob = {"year": year, "month": month, "day": day}
        logger.info(f"✓ Generated DOB: {day:02d}/{month:02d}/{year}")
        return dob

    def safe_click(self, element, timeout: int = 10) -> bool:
        """Safely click an element with retry logic"""
        try:
            self.wait.until(EC.element_to_be_clickable(element))
            element.click()
            return True
        except ElementClickInterceptedException:
            # Try JavaScript click if normal click fails
            self.driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            logger.warning(f"⚠ Failed to click element: {str(e)}")
            return False

    def safe_send_keys(self, element, text: str, clear_first: bool = True) -> bool:
        """Safely send keys to an element"""
        try:
            self.wait.until(EC.visibility_of(element))
            if clear_first:
                element.clear()
            element.send_keys(text)
            return True
        except Exception as e:
            logger.warning(f"⚠ Failed to send keys: {str(e)}")
            return False

    def step_1_click_signup_link(self) -> bool:
        """Step 1: Click 'Sign up with email address' button"""
        try:
            logger.info("→ Step 1: Looking for 'Sign up with email' button...")
            
            # Try multiple possible locators
            locators = [
                (By.XPATH, "//button[contains(text(), 'Sign up with email')]"),
                (By.XPATH, "//a[contains(text(), 'Sign up with email')]"),
                (By.NAME, "signup_email"),
                (By.ID, "signup_email_btn"),
            ]
            
            element = None
            for by, value in locators:
                try:
                    element = self.wait.until(EC.element_to_be_clickable((by, value)))
                    logger.info(f"✓ Found signup button using {by}: {value}")
                    break
                except TimeoutException:
                    continue
            
            if not element:
                raise NoSuchElementException("Could not find signup button with any locator")
            
            self.safe_click(element)
            logger.info("✓ Step 1 Complete: Clicked signup button")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 1 Failed: {str(e)}")
            raise

    def step_2_enter_email(self, email: str) -> bool:
        """Step 2: Enter email and click Next"""
        try:
            logger.info("→ Step 2: Entering email...")
            
            # Wait for email input to be visible
            email_input = self.wait.until(
                EC.visibility_of_element_located((By.NAME, "email"))
            )
            
            self.safe_send_keys(email_input, email)
            logger.info(f"✓ Email entered: {email}")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 2 Complete: Email submitted")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 2 Failed: {str(e)}")
            raise

    def step_3_handle_otp_manual(self, otp: str) -> bool:
        """Step 3: Enter OTP from user input"""
        try:
            logger.info("→ Step 3: Entering OTP...")
            
            # Wait for OTP input field
            otp_input = self.wait.until(
                EC.visibility_of_element_located((By.NAME, "otp"))
            )
            
            self.safe_send_keys(otp_input, otp)
            logger.info(f"✓ OTP entered: {otp}")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 3 Complete: OTP submitted")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 3 Failed: {str(e)}")
            raise

    def step_4_set_password(self, password: Optional[str] = None) -> str:
        """Step 4: Generate and enter password"""
        try:
            logger.info("→ Step 4: Setting password...")
            
            if not password:
                password = self.generate_password()
            
            # Wait for password input
            password_input = self.wait.until(
                EC.visibility_of_element_located((By.NAME, "password"))
            )
            
            self.safe_send_keys(password_input, password)
            logger.info("✓ Password entered")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 4 Complete: Password set")
            return password
            
        except Exception as e:
            logger.error(f"✗ Step 4 Failed: {str(e)}")
            raise

    def step_5_set_dob(self) -> Dict[str, int]:
        """Step 5: Set Date of Birth (18+ years old)"""
        try:
            logger.info("→ Step 5: Setting Date of Birth...")
            
            dob = self.generate_dob()
            
            # Try to find and fill DOB fields (adapt these locators to your site)
            try:
                # Look for separate year, month, day fields
                year_input = self.wait.until(
                    EC.visibility_of_element_located((By.NAME, "year"))
                )
                month_input = self.driver.find_element(By.NAME, "month")
                day_input = self.driver.find_element(By.NAME, "day")
                
                self.safe_send_keys(year_input, str(dob["year"]))
                self.safe_send_keys(month_input, str(dob["month"]))
                self.safe_send_keys(day_input, str(dob["day"]))
                
            except NoSuchElementException:
                # Try dropdown selects if individual inputs not found
                logger.info("⚠ Individual input fields not found, trying dropdowns...")
                
                year_select = Select(self.wait.until(
                    EC.presence_of_element_located((By.NAME, "dob_year"))
                ))
                year_select.select_by_value(str(dob["year"]))
                
                month_select = Select(self.driver.find_element(By.NAME, "dob_month"))
                month_select.select_by_value(str(dob["month"]).zfill(2))
                
                day_select = Select(self.driver.find_element(By.NAME, "dob_day"))
                day_select.select_by_value(str(dob["day"]).zfill(2))
            
            logger.info(f"✓ DOB set: {dob['day']:02d}/{dob['month']:02d}/{dob['year']}")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 5 Complete: DOB submitted")
            return dob
            
        except Exception as e:
            logger.error(f"✗ Step 5 Failed: {str(e)}")
            raise

    def step_6_enter_full_name(self, full_name: str) -> bool:
        """Step 6: Enter full name"""
        try:
            logger.info("→ Step 6: Entering full name...")
            
            # Wait for name input
            name_input = self.wait.until(
                EC.visibility_of_element_located((By.NAME, "full_name"))
            )
            
            self.safe_send_keys(name_input, full_name)
            logger.info(f"✓ Full name entered: {full_name}")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 6 Complete: Full name submitted")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 6 Failed: {str(e)}")
            raise

    def step_7_enter_username(self, username: str, wait_for_validation: float = 2.0) -> bool:
        """Step 7: Enter username and wait for validation (green tick)"""
        try:
            logger.info("→ Step 7: Entering username...")
            
            # Wait for username input
            username_input = self.wait.until(
                EC.visibility_of_element_located((By.NAME, "username"))
            )
            
            self.safe_send_keys(username_input, username)
            logger.info(f"✓ Username entered: {username}")
            
            # Wait for validation indicator (adapt selector to your site)
            try:
                import time
                time.sleep(wait_for_validation)
                
                validation_tick = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(@class, 'valid')] | //i[contains(@class, 'check')]"))
                )
                logger.info("✓ Username validated (green tick visible)")
            except TimeoutException:
                logger.warning("⚠ Validation indicator not found, proceeding anyway")
            
            # Click Next button
            next_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Next')]"))
            )
            self.safe_click(next_button)
            logger.info("✓ Step 7 Complete: Username submitted")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 7 Failed: {str(e)}")
            raise

    def step_8_agree_terms(self) -> bool:
        """Step 8: Accept Terms and Policies"""
        try:
            logger.info("→ Step 8: Accepting Terms and Policies...")
            
            # Wait for page to fully load
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'I agree')] | //button[contains(text(), 'Agree')]"))
            )
            
            # Click "I agree" button
            agree_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'I agree')] | //button[contains(text(), 'Agree')]"))
            )
            self.safe_click(agree_button)
            logger.info("✓ Step 8 Complete: Terms accepted")
            return True
            
        except Exception as e:
            logger.error(f"✗ Step 8 Failed: {str(e)}")
            raise

    def execute_signup_flow(self, full_name: str, username: str, email: str, otp: str) -> Dict[str, Any]:
        """Execute the complete 8-step signup flow"""
        try:
            logger.info(f"\n{'='*60}")
            logger.info("STARTING SIGNUP AUTOMATION")
            logger.info(f"{'='*60}")
            logger.info(f"Email: {email}\nUsername: {username}\nFull Name: {full_name}\n")
            
            self.setup_driver()
            self.driver.get(self.base_url)
            logger.info(f"✓ Navigated to {self.base_url}")
            
            # Execute all steps
            self.step_1_click_signup_link()
            self.step_2_enter_email(email)
            self.step_3_handle_otp_manual(otp)
            password = self.step_4_set_password()
            dob = self.step_5_set_dob()
            self.step_6_enter_full_name(full_name)
            self.step_7_enter_username(username)
            self.step_8_agree_terms()
            
            logger.info(f"{'='*60}")
            logger.info("✓ SIGNUP COMPLETED SUCCESSFULLY!")
            logger.info(f"{'='*60}\n")
            
            return {
                "success": True,
                "password": password,
                "dob": dob,
                "message": "Account created successfully!"
            }
            
        except Exception as e:
            logger.error(f"\n✗ SIGNUP FAILED: {str(e)}\n")
            return {
                "success": False,
                "error": str(e),
                "message": f"Signup failed: {str(e)}"
            }
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up browser session"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("✓ Browser session closed")
        except Exception as e:
            logger.warning(f"⚠ Error during cleanup: {str(e)}")


class TelegramSignupBot:
    """Telegram bot for managing signup automation"""

    def __init__(self, token: str):
        self.token = token
        self.app: Optional[Application] = None
        self.user_sessions: Dict[int, Dict[str, Any]] = {}  # Store user signup data

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 Signup Automation Bot\n\n"
            "Use: `/create <FullName> <Username> <Email>`\n\n"
            "Example: `/create John Doe johndoe john@example.com`\n\n"
            "The bot will automate the signup process and ask for OTP."
        )
        return AWAITING_COMMAND

    async def create_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /create command to start signup"""
        user_id = update.effective_user.id
        
        try:
            # Parse command arguments
            if len(context.args) < 3:
                await update.message.reply_text(
                    "❌ Invalid format!\n"
                    "Use: `/create <FullName> <Username> <Email>`\n"
                    "Example: `/create John Doe johndoe john@example.com`"
                )
                return AWAITING_COMMAND
            
            full_name = context.args[0]
            username = context.args[1]
            email = context.args[2]
            
            # Validate email format
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                await update.message.reply_text("❌ Invalid email format!")
                return AWAITING_COMMAND
            
            # Store user data
            self.user_sessions[user_id] = {
                "full_name": full_name,
                "username": username,
                "email": email,
                "otp": None
            }
            
            await update.message.reply_text(
                f"⏳ Starting signup automation...\n\n"
                f"📧 Email: {email}\n"
                f"👤 Username: {username}\n"
                f"📝 Full Name: {full_name}\n\n"
                f"⏸️ Please provide the OTP you receive to complete the process."
            )
            
            logger.info(f"User {user_id} initiated signup for {email}")
            return AWAITING_OTP
            
        except Exception as e:
            logger.error(f"Error in create_account: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            return AWAITING_COMMAND

    async def handle_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle OTP input from user"""
        user_id = update.effective_user.id
        
        try:
            if user_id not in self.user_sessions:
                await update.message.reply_text("❌ No active signup session. Use `/create` to start.")
                return AWAITING_COMMAND
            
            otp = update.message.text.strip()
            
            # Validate OTP format (usually 4-6 digits)
            if not otp.isdigit() or len(otp) < 4 or len(otp) > 6:
                await update.message.reply_text(
                    "❌ Invalid OTP format!\n"
                    "Please enter a 4-6 digit OTP."
                )
                return AWAITING_OTP
            
            # Update user session
            self.user_sessions[user_id]["otp"] = otp
            
            # Show typing indicator
            await context.bot.send_chat_action(user_id, ChatAction.TYPING)
            await update.message.reply_text("⏳ Processing signup automation, please wait...")
            
            # Execute signup automation
            user_data = self.user_sessions[user_id]
            automation = SignupAutomation()
            
            result = automation.execute_signup_flow(
                full_name=user_data["full_name"],
                username=user_data["username"],
                email=user_data["email"],
                otp=user_data["otp"]
            )
            
            # Send result to user
            if result["success"]:
                response = (
                    f"✅ Account Created Successfully!\n\n"
                    f"📧 Email: {user_data['email']}\n"
                    f"👤 Username: {user_data['username']}\n"
                    f"📝 Full Name: {user_data['full_name']}\n\n"
                    f"🔐 Generated Password: `{result['password']}`\n"
                    f"📅 DOB: {result['dob']['day']:02d}/{result['dob']['month']:02d}/{result['dob']['year']}\n\n"
                    f"⚠️ Save your password in a secure location!"
                )
            else:
                response = f"❌ Signup Failed\n\n{result['message']}"
            
            await update.message.reply_text(response)
            
            # Clean up session
            del self.user_sessions[user_id]
            logger.info(f"Signup process completed for user {user_id}")
            
            return AWAITING_COMMAND
            
        except Exception as e:
            logger.error(f"Error in handle_otp: {str(e)}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            return AWAITING_OTP

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /cancel command"""
        user_id = update.effective_user.id
        
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        await update.message.reply_text("❌ Signup cancelled.")
        return AWAITING_COMMAND

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Update {update} caused error: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                f"⚠️ An error occurred: {str(context.error)}"
            )

    def run(self) -> None:
        """Run the Telegram bot"""
        try:
            self.app = Application.builder().token(self.token).build()
            
            # Create conversation handler
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("create", self.create_account)],
                states={
                    AWAITING_OTP: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_otp),
                        CommandHandler("cancel", self.cancel),
                    ],
                    AWAITING_COMMAND: [
                        CommandHandler("create", self.create_account),
                    ],
                },
                fallbacks=[
                    CommandHandler("cancel", self.cancel),
                    CommandHandler("start", self.start),
                ],
            )
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(conv_handler)
            self.app.add_error_handler(self.error_handler)
            
            logger.info("🤖 Bot started. Press Ctrl+C to stop.")
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Failed to start bot: {str(e)}")
            raise


def main():
    """Main entry point"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ TELEGRAM_BOT_TOKEN not set. Please set the environment variable.")
        return
    
    bot = TelegramSignupBot(TELEGRAM_BOT_TOKEN)
    bot.run()


if __name__ == "__main__":
    main()
