#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import pytz
import json
import requests
import threading
import http.server
import socketserver
import gspread
import asyncio
from sheets_integration import GoogleSheetsIntegration
from google.oauth2 import service_account
from datetime import datetime, time, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, JobQueue, filters, PicklePersistence
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
import os
TOKEN = os.environ.get("BOT_TOKEN")


# Egypt timezone
EGYPT_TZ = pytz.timezone('Africa/Cairo')

# Conversation states
SELECTING_SERVICES = 0
CONFIRM_SERVICES = 1

# Callback data
QURAN_SERVICE = "quran_service"
PROPHET_PRAYER_SERVICE = "prophet_prayer_service"
DHIKR_SERVICE = "dhikr_service"
NIGHT_PRAYER_SERVICE = "night_prayer_service"
CONFIRM = "confirm"
MORE_QURAN = "more_quran"
NO_MORE_QURAN = "no_more_quran"
CONFIRM_READ = "confirm_read"  # New callback data for confirming reading
RETURN_TO_WIRD = "return_to_wird"  # Callback data for the new button
GET_USERS_COUNT = "get_users_count"  # New callback data for admin command

# Admin user ID - Ahmed A. Ismail's user ID
ADMIN_ID = 853742750

# Google Sheets Configuration
CREDENTIALS_FILE = "telegram-bot-457917-a94e41b346fe.json"
SHEET_ID = "1XDAqhMa_N9iThRotfylOzkgKhkNoq1EdliM2qCz2Qgo"
SHEET_NAME = "user_data"

# Other data storage
QURAN_TRACKER_FILE = "quran_tracker.json"
QURAN_IMAGES_LINKS_FILE = "quran_images_links.json"  # File for image links
PERSISTENCE_FILE = "persistence_data.pickle" # File for persistence data

sheets = GoogleSheetsIntegration("telegram-bot-457917-a94e41b346fe.json")

# Health check server port (for Railway deployment)
HEALTH_CHECK_PORT = int(os.environ.get("PORT", 8080))

# Initialize Google Sheets client
def init_google_sheets():
    try:
        # Create credentials from the service account file
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        
        # Create a gspread client
        client = gspread.authorize(credentials)
        
        # Open the spreadsheet and worksheet
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        
        logger.info("Successfully connected to Google Sheets")
        return sheet
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets: {e}")
        return None

# Load user data from Google Sheets
def load_user_data():
    try:
        sheet = init_google_sheets()
        if not sheet:
            logger.error("Failed to initialize Google Sheets")
            return {}
            
        # Get all records from the sheet
        records = sheet.get_all_records()
        
        # Convert to the format expected by the bot
        user_data = {}
        for record in records:
            user_id = str(record.get('user_id', ''))
            if user_id:
                user_data[user_id] = {
                    "username": record.get('username', ''),
                    "joined_date": record.get('joined_date', ''),
                    "services": {
                        QURAN_SERVICE: record.get('quran_service', False),
                        PROPHET_PRAYER_SERVICE: record.get('prophet_prayer_service', False),
                        DHIKR_SERVICE: record.get('dhikr_service', False),
                        NIGHT_PRAYER_SERVICE: record.get('night_prayer_service', False)
                    }
                }
        
        logger.info(f"Loaded {len(user_data)} users from Google Sheets")
        return user_data
    except Exception as e:
        logger.error(f"Error loading user data from Google Sheets: {e}")
        return {}

# Save user data to Google Sheets - Modified to run in a separate thread
def save_user_data(data):
    # Create a function to run in a separate thread
    def save_data_thread():
        try:
            sheet = init_google_sheets()
            if not sheet:
                logger.error("Failed to initialize Google Sheets")
                return
                
            # Convert user data to format for Google Sheets
            records = []
            for user_id, user_info in data.items():
                record = {
                    'user_id': user_id,
                    'username': user_info.get('username', ''),
                    'joined_date': user_info.get('joined_date', ''),
                    'quran_service': user_info.get('services', {}).get(QURAN_SERVICE, False),
                    'prophet_prayer_service': user_info.get('services', {}).get(PROPHET_PRAYER_SERVICE, False),
                    'dhikr_service': user_info.get('services', {}).get(DHIKR_SERVICE, False),
                    'night_prayer_service': user_info.get('services', {}).get(NIGHT_PRAYER_SERVICE, False)
                }
                records.append(record)
            
            # Clear the current sheet data (except header)
            sheet.clear()
            
            # Add header row
            header = ['user_id', 'username', 'joined_date', 'quran_service', 
                     'prophet_prayer_service', 'dhikr_service', 'night_prayer_service']
            sheet.update('A1', [header])
            
            # Add all records
            if records:
                values = []
                for record in records:
                    row = [
                        record['user_id'],
                        record['username'],
                        record['joined_date'],
                        record['quran_service'],
                        record['prophet_prayer_service'],
                        record['dhikr_service'],
                        record['night_prayer_service']
                    ]
                    values.append(row)
                
                sheet.update(f'A2:G{len(records)+1}', values)
            
            logger.info(f"Saved {len(records)} users to Google Sheets")
        except Exception as e:
            logger.error(f"Error saving user data to Google Sheets: {e}")
    
    # Start a new thread to save data
    threading.Thread(target=save_data_thread).start()

# Quran tracking now uses Google Sheets

# Load Quran image links
def load_quran_image_links():
    if os.path.exists(QURAN_IMAGES_LINKS_FILE):
        with open(QURAN_IMAGES_LINKS_FILE, 'r', encoding='utf-8') as file:
            try:
                # Load the array of objects
                links_array = json.load(file)
                
                # Convert to a dictionary with page numbers as keys
                links_dict = {}
                for item in links_array:
                    # Extract page number from filename (e.g., "1.jpg" -> "1")
                    page_num = item["name"].split('.')[0]
                    links_dict[page_num] = item["url"]
                
                return links_dict
            except json.JSONDecodeError:
                logger.error(f"Error parsing {QURAN_IMAGES_LINKS_FILE}")
                return {}
    else:
        logger.error(f"File {QURAN_IMAGES_LINKS_FILE} not found")
        return {}

# Define the new messages for scheduled sending
DUA_MESSAGE = "إلهي أذهب البأس ربّ النّاس ، اشف وأنت الشّافي ، لا شفاء إلا شفاؤك ، شفاءً لا يغادر سقماً ، أذهب البأس ربّ النّاس ، بيدك الشّفاء ، لا كاشف له إلّا أنت يارب العالمين"
AYAH_MESSAGE = "﴿ ۞ وَأَيُّوبَ إِذۡ نَادَىٰ رَبَّهُۥٓ أَنِّي مَسَّنِيَ ٱلضُّرُّ وَأَنتَ أَرۡحَمُ ٱلرَّٰحِمِينَ ﴾  [ الأنبياء : ٨٣ ]"

# New callback function for Dua message
async def send_dua_message(context: ContextTypes.DEFAULT_TYPE):
    """Sends the scheduled Dua message to all users."""
    logger.info("Running scheduled job: send_dua_message")
    user_data = load_user_data()
    if not user_data:
        logger.info("No users found to send Dua message.")
        return
    for user_id in user_data.keys():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=DUA_MESSAGE)
            logger.info(f"Sent Dua message to user {user_id}")
        except Exception as e:
            # Handle potential errors like user blocking the bot
            logger.error(f"Failed to send Dua message to user {user_id}: {e}")

# New callback function for Ayah message
async def send_ayah_message(context: ContextTypes.DEFAULT_TYPE):
    """Sends the scheduled Ayah message to all users."""
    logger.info("Running scheduled job: send_ayah_message")
    user_data = load_user_data()
    if not user_data:
        logger.info("No users found to send Ayah message.")
        return
    for user_id in user_data.keys():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=AYAH_MESSAGE)
            logger.info(f"Sent Ayah message to user {user_id}")
        except Exception as e:
            # Handle potential errors like user blocking the bot
            logger.error(f"Failed to send Ayah message to user {user_id}: {e}")

# New callback function for Global Saturday Reminder
async def send_global_saturday_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Sends the scheduled Saturday reminder to all users."""
    logger.info("Running scheduled job: send_global_saturday_reminder")
    user_data = load_user_data()
    if not user_data:
        logger.info("No users found to send Saturday reminder.")
        return
    for user_id in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="🟣 بدايه اسبوع جديد وحاول تبعد عن الذنوب وخصوصا الكبائر عشان بتسبب مشاكل و تعب نفسي و نقص الرزق و عدم استجابه الدعاء و عدم التوفيق و غيره الكثير"
            )
            await context.bot.send_message(
                chat_id=int(user_id),
                text="بعض من الكبائر : ترك الصلاة , العقوق , الكذب , الغيبة , النميمة , الربا ( من ضمنها القروض ) , شرب الخمر والمخدرات , شتم الاهل ( اهل اي حد ) , الزنا , أكل المال الحرام , الرياء ( التظاهر بالصلاح ) , شهادة الزور , قطع صله الرحم"
            )
            logger.info(f"Sent Saturday reminder to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send Saturday reminder to user {user_id}: {e}")

# New callback function for Global Thursday Reminder
async def send_global_thursday_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Sends the scheduled Thursday reminder to all users."""
    logger.info("Running scheduled job: send_global_thursday_reminder")
    user_data = load_user_data()
    if not user_data:
        logger.info("No users found to send Thursday reminder.")
        return
    for user_id in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="مِن مغرب الخَميس إلى مغرب الجُمعة كُلّ ثانية فيها خزائن من الحسناتِ والرّحمات وتفريج الكُربات\nفليُكثر المرء من الصَّلاة على النَّبي ﷺ"
            )
            await context.bot.send_message(
                chat_id=int(user_id),
                text="﴿ إِنَّ اللَّهَ وَمَلائِكَتَهُ يُصَلّونَ عَلَى النَّبِيِّ يا أَيُّهَا الَّذينَ آمَنوا صَلّوا عَلَيهِ وَسَلِّموا تَسليمًا ﴾ [ الأحزاب : ٥٦ ]"
            )
            logger.info(f"Sent Thursday reminder and additional message to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send Thursday reminder to user {user_id}: {e}")

# Helper function to convert Egypt time to UTC
def egypt_time_to_utc(hour, minute=0, second=0):
    # Create a datetime object for today with the specified time in Egypt timezone
    now = datetime.now()
    egypt_dt = EGYPT_TZ.localize(datetime(now.year, now.month, now.day, hour, minute, second))
    # Convert to UTC
    utc_dt = egypt_dt.astimezone(pytz.UTC)
    # Return just the time component
    return utc_dt.time()

# Simple HTTP request handler for health checks
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Bot is running')
        
    def log_message(self, format, *args):
        # Suppress log messages
        return

# Start a simple HTTP server for health checks
def start_health_check_server():
    handler = HealthCheckHandler
    try:
        # Allow socket reuse to prevent "Address already in use" errors on restart
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("0.0.0.0", HEALTH_CHECK_PORT), handler)
        logger.info(f"Starting health check server on port {HEALTH_CHECK_PORT}")
        
        try:
            # Run the server with exception handling
            httpd.serve_forever()
        except Exception as e:
            logger.error(f"Health check server error: {e}")
        finally:
            # Ensure server is properly closed if an exception occurs
            httpd.server_close()
            logger.info("Health check server closed")
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")

# Admin command handler to get user count only
async def get_users_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the user is admin
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("هذا الأمر متاح فقط للمسؤول")
        return
        
    user_data = load_user_data()
    user_count = len(user_data)

    # Send user count only
    await update.message.reply_text(f"عدد مستخدمي البوت الحاليين : {user_count}")

# Admin command handler to get detailed user information
async def get_users_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the user is admin
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("هذا الأمر متاح فقط للمسؤول")
        return
        
    user_data = load_user_data()
    
    # Get detailed user information with the requested format
    user_details = []
    for user_id, data in user_data.items():
        username = data.get("username", "غير معروف")
        joined_date = data.get("joined_date", "غير معروف")
        
        services = []
        if data.get("services", {}).get(QURAN_SERVICE, False):
            services.append("القرآن")
        if data.get("services", {}).get(PROPHET_PRAYER_SERVICE, False):
            services.append("الصلاة على النبي")
        if data.get("services", {}).get(DHIKR_SERVICE, False):
            services.append("الأذكار")
        if data.get("services", {}).get(NIGHT_PRAYER_SERVICE, False):
            services.append("قيام الليل")
        
        services_str = ", ".join(services) if services else "لا يوجد"
        
        # Format join date to show only the date part (remove time)
        try:
            date_only = joined_date.split(" ")[0] if " " in joined_date else joined_date
        except:
            date_only = joined_date
            
        user_details.append(f"- اسم المستخدم: {username} ({user_id})\n- تاريخ الانضمام: {date_only}\n- الخدمات: {services_str}\n")
    
    # Send detailed user information
    if user_details:
        details_message = "معلومات المستخدمين:\n\n" + "\n".join(user_details)
        await update.message.reply_text(details_message)
    else:
        await update.message.reply_text("لا يوجد مستخدمين مسجلين حالياً")

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    
    # Create services selection keyboard
    keyboard = [
        [
            InlineKeyboardButton("القرآن الكريم", callback_data=QURAN_SERVICE),
        ],
        [
            InlineKeyboardButton("الصلاة على النبي", callback_data=PROPHET_PRAYER_SERVICE),
        ],
        [
            InlineKeyboardButton("الأدعية وذكر الله", callback_data=DHIKR_SERVICE),
        ],
        [
            InlineKeyboardButton("قيام الليل", callback_data=NIGHT_PRAYER_SERVICE),
        ],
        [
            InlineKeyboardButton("🔵 تأكيد الاختيارات 🔵", callback_data=CONFIRM),
        ],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Initialize user data if not exists
    user_data = load_user_data()
    user_info = update.effective_user
    username = user_info.username if user_info.username else f"{user_info.first_name} {user_info.last_name if user_info.last_name else ''}".strip()
    
    if user_id not in user_data:
        user_data[user_id] = {
            "username": username, # Store username
            "services": {
                QURAN_SERVICE: False,
                PROPHET_PRAYER_SERVICE: False,
                DHIKR_SERVICE: False,
                NIGHT_PRAYER_SERVICE: False
            },
            "joined_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_user_data(user_data)
    # Update username if user already exists but username might have changed
    elif user_data[user_id].get("username") != username:
        user_data[user_id]["username"] = username
        save_user_data(user_data)
    # Initialize quran tracker if not exists
    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    if user_id not in quran_tracker:
        quran_tracker[user_id] = {
            "last_page": 0,
            "total_pages_read": 0,
            "unread_pages": [],  # Track unread pages
            "last_read_confirmed": True,  # Track if last reading was confirmed
            "last_reminder_message_id": None, # Track confirmation message ID
            "last_wird_reminder_message_id": None # Track the 'متنساش' reminder message ID
        }
        sheets.update_quran_tracking(quran_tracker)
    
    await update.message.reply_text(
        "مرحباً بك في بوت \"اذكر الله\"!\n\n"
        "يرجى اختيار الخدمات التي ترغب في الاشتراك بها:",
        reply_markup=reply_markup
    )
    
    return SELECTING_SERVICES

# Service selection handler - MODIFIED to improve performance and fix Google Sheets update
async def service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    callback_data = query.data
    
    # Load user data
    user_data = load_user_data()
    
    # Handle confirmation
    if callback_data == CONFIRM:
        selected_services = []
        if user_data[user_id]["services"][QURAN_SERVICE]:
            selected_services.append("القرآن الكريم")
        if user_data[user_id]["services"][PROPHET_PRAYER_SERVICE]:
            selected_services.append("الصلاة على النبي")
        if user_data[user_id]["services"][DHIKR_SERVICE]:
            selected_services.append("الأدعية وذكر الله")
        if user_data[user_id]["services"][NIGHT_PRAYER_SERVICE]:
            selected_services.append("قيام الليل")
        
        if not selected_services:
            await query.edit_message_text(
                "لم تقم باختيار أي خدمة. يرجى اختيار خدمة واحدة على الأقل.",
                reply_markup=query.message.reply_markup
            )
            return SELECTING_SERVICES
        
        try:
            # First confirmation message - IMMEDIATELY CONFIRM to user
            await query.edit_message_text("تم تأكيد اختياراتك بنجاح!")
            
            # Save to Google Sheets in background thread
            save_user_data(user_data)
            
            # Schedule jobs in background task
            asyncio.create_task(schedule_jobs_background(context, user_id))
            
            # Create second message with service timings
            schedule_text = "مواعيد التذكيرات:\n\n"
            
            if user_data[user_id]["services"][QURAN_SERVICE]:
                schedule_text += "1- خدمة القرآن الكريم: يومياً الساعة 12:00 ظهراً\n\n"
            
            if user_data[user_id]["services"][PROPHET_PRAYER_SERVICE]:
                schedule_text += "2- خدمة الصلاة على النبي: كل ساعة بداية من الساعة 12:15 ظهراً\n\n"
            
            if user_data[user_id]["services"][DHIKR_SERVICE]:
                schedule_text += "3- خدمة الأدعية وذكر الله: في مواعيد متفرقه\n\n"

            if user_data[user_id]["services"][NIGHT_PRAYER_SERVICE]:
                schedule_text += "4- خدمة قيام الليل: يومياً الساعة 12:00 منتصف الليل\n\n"
            
            schedule_text += "شكراً لاختيارك بوت \"اذكر الله\". ستبدأ في تلقي التذكيرات حسب المواعيد المذكورة أعلاه."
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=schedule_text
            )
                
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error in confirmation: {e}")
            await query.edit_message_text(
                f"حدث خطأ أثناء تأكيد اختياراتك. يرجى المحاولة مرة أخرى أو التواصل مع مسؤول البوت.\n\nتفاصيل الخطأ: {str(e)}",
                reply_markup=query.message.reply_markup
            )
            return SELECTING_SERVICES
    
    # Toggle service selection
    if callback_data in user_data[user_id]["services"]:
        user_data[user_id]["services"][callback_data] = not user_data[user_id]["services"][callback_data]
        
        # Update keyboard with selected services
        keyboard = [
            [
                InlineKeyboardButton(
                    " ✅ القرآن الكريم" if user_data[user_id]["services"][QURAN_SERVICE] else "القرآن الكريم", 
                    callback_data=QURAN_SERVICE
                ),
            ],
            [
                InlineKeyboardButton(
                    " ✅ الصلاة على النبي" if user_data[user_id]["services"][PROPHET_PRAYER_SERVICE] else "الصلاة على النبي", 
                    callback_data=PROPHET_PRAYER_SERVICE
                ),
            ],
            [
                InlineKeyboardButton(
                    " ✅ الأدعية وذكر الله" if user_data[user_id]["services"][DHIKR_SERVICE] else "الأدعية وذكر الله", 
                    callback_data=DHIKR_SERVICE
                ),
            ],
            [
                InlineKeyboardButton(
                    " ✅ قيام الليل" if user_data[user_id]["services"][NIGHT_PRAYER_SERVICE] else "قيام الليل", 
                    callback_data=NIGHT_PRAYER_SERVICE
                ),
            ],
            [
                InlineKeyboardButton("🔵 تأكيد الاختيارات 🔵", callback_data=CONFIRM),
            ],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "يرجى اختيار الخدمات التي ترغب في الاشتراك بها:",
            reply_markup=reply_markup
        )
    
    return SELECTING_SERVICES

# Return to Wird callback handler
async def return_to_wird_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Answer callback query first

    user_id = str(query.from_user.id)
    chat_id = query.message.chat_id

    # Attempt to delete the message that contained the "العوده للوِرد" button
    # This is the message that triggered this callback
    original_message_id = query.message.message_id
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=original_message_id)
        logger.info(f"Deleted original message {original_message_id} for user {user_id} in return_to_wird_callback")
    except Exception as e:
        logger.info(f"Could not delete original message {original_message_id} for user {user_id} in return_to_wird_callback: {e}")

    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    quran_links = load_quran_image_links()

    if user_id not in quran_tracker:
        await context.bot.send_message(chat_id=chat_id, text="عذراً، لم يتم العثور على بيانات التتبع الخاصة بك.")
        return

    unread_pages = quran_tracker[user_id].get("unread_pages", [])

    if not unread_pages:
        await context.bot.send_message(chat_id=chat_id, text="لا يوجد ورد حالي مسجل لك للعودة إليه.")
        return
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="إليك الورد الذي لم تقرأه بعد:" # Message indicating re-sending
    )

    for page_num in unread_pages: # Iterate through all unread pages
        page_num_str = str(page_num)
        if page_num_str in quran_links:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=quran_links[page_num_str],
                caption=f"صفحة {page_num}"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"عذراً، لم يتم العثور على رابط لصفحة {page_num}."
            )
    
    # Ask if user read the pages
    read_keyboard = [
        [
            InlineKeyboardButton("نعم ✅", callback_data=CONFIRM_READ)
        ]
    ]
    read_reply_markup = InlineKeyboardMarkup(read_keyboard)
    
    confirmation_message = await context.bot.send_message(
        chat_id=chat_id,
        text="هل قرأت الوِرد؟",
        reply_markup=read_reply_markup
    )
    
    # Save confirmation message ID for later deletion in confirm_reading
    quran_tracker[user_id]["last_reminder_message_id"] = confirmation_message.message_id
    sheets.update_quran_tracking(quran_tracker)

# New background task for scheduling jobs
async def schedule_jobs_background(context: ContextTypes.DEFAULT_TYPE, user_id: str):
    """Schedule jobs in a background task to avoid blocking the main thread"""
    try:
        # Load user data
        user_data = load_user_data()
        
        # Check if job_queue exists
        if not hasattr(context, 'job_queue') or context.job_queue is None:
            logger.error("Job queue is not available in context")
            raise ValueError("Job queue is not initialized. Please restart the bot.")
        
        # Remove existing jobs for this user
        current_jobs = context.job_queue.get_jobs_by_name(user_id)
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
        
        # Notify user that scheduling is in progress
        await context.bot.send_message(
            chat_id=int(user_id),
            text="جاري جدولة التذكيرات..."
        )
        
        # Schedule Quran service (daily at 12:00 PM Egypt time)
        if user_data[user_id]["services"][QURAN_SERVICE]:
            # Convert to UTC for job queue
            utc_time = egypt_time_to_utc(12, 0)  # 12:00 PM Egypt time
            
            context.job_queue.run_daily(
                send_quran_reminder,
                time=utc_time,
                chat_id=int(user_id),
                name=f"{user_id}_quran",
                data=user_id
            )
        
        # Schedule Prophet prayer service (hourly starting at 12:15 PM Egypt time)
        if user_data[user_id]["services"][PROPHET_PRAYER_SERVICE]:
            # First reminder at 12:15 PM Egypt time
            utc_time = egypt_time_to_utc(12, 15)  # 12:15 PM Egypt time
            
            # Schedule hourly job
            context.job_queue.run_daily(
                send_prophet_prayer,
                time=utc_time,
                chat_id=int(user_id),
                name=f"{user_id}_prophet_first",
                data=user_id
            )
            
            # Schedule remaining hourly reminders
            now = datetime.now()
            egypt_dt = EGYPT_TZ.localize(datetime(now.year, now.month, now.day, 12, 15))
            
            for hour in range(1, 24):
                next_dt = egypt_dt + timedelta(hours=hour)
                next_utc_time = next_dt.astimezone(pytz.UTC).time()
                
                context.job_queue.run_daily(
                    send_prophet_prayer,
                    time=next_utc_time,
                    chat_id=int(user_id),
                    name=f"{user_id}_prophet_{hour}",
                    data=user_id
                )
        
        # Schedule Dhikr service
        if user_data[user_id]["services"][DHIKR_SERVICE]:
            # Daily at 4:30 PM Egypt time
            utc_time_430pm = egypt_time_to_utc(16, 30)  # 4:30 PM Egypt time
            
            context.job_queue.run_daily(
                send_daily_dhikr,
                time=utc_time_430pm,
                chat_id=int(user_id),
                name=f"{user_id}_daily_dhikr",
                data=user_id
            )
            
            # Every 12 hours starting at 12:00 PM Egypt time
            utc_time_1145am = egypt_time_to_utc(11, 45)  # 11:45 AM Egypt time
            
            context.job_queue.run_daily(
                send_12hour_dhikr,
                time=utc_time_1145am,
                chat_id=int(user_id),
                name=f"{user_id}_12hour_dhikr_noon",
                data=user_id
            )
            
            # 12 hours later (11:45 PM)
            utc_time_1145pm = egypt_time_to_utc(23, 45)  # 11:45 PM Egypt time
            
            context.job_queue.run_daily(
                send_12hour_dhikr,
                time=utc_time_1145pm,
                chat_id=int(user_id),
                name=f"{user_id}_12hour_dhikr_midnight",
                data=user_id
            )
            
            # Thursday Dhikr (now global) - REMOVED FROM HERE
            
            # Saturday Dhikr (now global) - REMOVED FROM HERE

            # Schedule Dua message for Dhikr service users
            # Tue, Thu, Sat at 4:30:10 PM Egypt time
            utc_time_dhikr_dua = egypt_time_to_utc(16, 30, 10)
            dhikr_dua_days = (1, 3, 5) # Tuesday, Thursday, Saturday

            context.job_queue.run_daily(
                send_dua_message, # Reusing the existing global send_dua_message function
                time=utc_time_dhikr_dua,
                days=dhikr_dua_days,
                chat_id=int(user_id), # Specific to this user
                name=f"{user_id}_dhikr_dua_schedule"
            )
            logger.info(f"Scheduled Dhikr Dua message for user {user_id} on Tue, Thu, Sat at 16:30:10 Egypt time.")

            # Schedule Ayah message for Dhikr service users
            # Tue, Thu, Sat at 4:30:15 PM Egypt time
            utc_time_dhikr_ayah = egypt_time_to_utc(16, 30, 15)
            dhikr_ayah_days = (1, 3, 5) # Tuesday, Thursday, Saturday

            context.job_queue.run_daily(
                send_ayah_message, # Reusing the existing global send_ayah_message function
                time=utc_time_dhikr_ayah,
                days=dhikr_ayah_days,
                chat_id=int(user_id), # Specific to this user
                name=f"{user_id}_dhikr_ayah_schedule"
            )
            logger.info(f"Scheduled Dhikr Ayah message for user {user_id} on Tue, Thu, Sat at 16:30:15 Egypt time.")    
        # Schedule Night prayer service (daily at 12:00 AM Egypt time)
        if user_data[user_id]["services"][NIGHT_PRAYER_SERVICE]:
            # Convert to UTC for job queue
            utc_time = egypt_time_to_utc(0, 0)  # 12:00 AM Egypt time
            
            context.job_queue.run_daily(
                send_night_prayer,
                time=utc_time,
                chat_id=int(user_id),
                name=f"{user_id}_night_prayer",
                data=user_id
            )
        
        logger.info(f"Successfully scheduled all jobs for user {user_id} in background")
    except Exception as e:
        logger.error(f"Error in background job scheduling for user {user_id}: {e}")

# Schedule jobs based on user's selected services - KEPT FOR COMPATIBILITY
async def schedule_jobs(context: ContextTypes.DEFAULT_TYPE, user_id: str):
    # Create a background task to handle the scheduling
    asyncio.create_task(schedule_jobs_background(context, user_id))

# Quran reminder handler - MODIFIED to send 5 pages and add reading confirmation
async def send_quran_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    user_id = job.data
    
    # Load quran tracker
    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    
    # Check if user has unread pages
    if quran_tracker[user_id]["unread_pages"]:
        # Create the button
        keyboard = [
            [
                InlineKeyboardButton(" اعاده ارسال الوِرد ", callback_data=RETURN_TO_WIRD)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text="🔴 لديك صفحات لم تقرأها بعد. يرجى قراءتها أولاً.",
            reply_markup=reply_markup
        )
        return
    
    # Get user's last page
    last_page = quran_tracker[user_id]["last_page"]
    
    # Determine pages to send (5 pages)
    start_page = last_page + 1
    end_page = start_page + 4  # Send 5 pages
    
    # Cap at 604 (total Quran pages)
    if start_page > 604:
        start_page = 1
    if end_page > 604:
        end_page = 604
    
    # Send initial message
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔵 إليك ورد اليوم من القرآن الكريم ( من {start_page} إلى {end_page} ) :"
    )
    
    # Send pages
    quran_links = load_quran_image_links()
    pages_to_send = list(range(start_page, end_page + 1))
    
    for page_num in pages_to_send:
        page_num_str = str(page_num)
        if page_num_str in quran_links:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=quran_links[page_num_str],
                caption=f"صفحة {page_num}"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"عذراً، لم يتم العثور على رابط لصفحة {page_num}."
            )
    
    # Update quran tracker
    quran_tracker[user_id]["last_page"] = end_page
    quran_tracker[user_id]["unread_pages"] = pages_to_send
    quran_tracker[user_id]["last_read_confirmed"] = False
    quran_tracker[user_id]["total_pages_read"] += len(pages_to_send)
    sheets.update_quran_tracking(quran_tracker)
    
    # Ask if user read the pages
    read_keyboard = [
        [
            InlineKeyboardButton("نعم ✅", callback_data=CONFIRM_READ)
        ]
    ]
    read_reply_markup = InlineKeyboardMarkup(read_keyboard)
    
    message = await context.bot.send_message(
        chat_id=chat_id,
        text="هل قرأت الوِرد؟",
        reply_markup=read_reply_markup
    )
    
    # Save message ID for later reference
    quran_tracker[user_id]["last_reminder_message_id"] = message.message_id
    sheets.update_quran_tracking(quran_tracker)
    
    # Schedule reminder at 11:50 PM Egypt time if not confirmed
    now_egypt = datetime.now(EGYPT_TZ)
    # Create the specific datetime for 11:50 PM today in Egypt timezone
    reminder_dt_egypt = now_egypt.replace(hour=23, minute=50, second=0, microsecond=0)

    # Convert the reminder datetime to UTC for the job queue
    reminder_dt_utc = reminder_dt_egypt.astimezone(pytz.utc)

    # Ensure the reminder time is in the future relative to the current UTC time
    # This prevents scheduling reminders for the past if the main job runs late or if it's already past 11:50 PM Egypt time
    if reminder_dt_utc > datetime.now(pytz.utc):
        context.job_queue.run_once(
            send_reading_reminder,
            reminder_dt_utc, # Use the specific datetime object
            chat_id=chat_id,
            name=f"{user_id}_reading_reminder_{now_egypt.date()}", # Add date to name for uniqueness
            data=user_id
        )

# Reading reminder handler
async def send_reading_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    user_id = job.data
    
    # Load quran tracker
    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    
    # Check if reading was confirmed
    if not quran_tracker[user_id]["last_read_confirmed"]:
        # Create the button
        keyboard = [
            [
                InlineKeyboardButton(" اعاده ارسال الوِرد ", callback_data=RETURN_TO_WIRD)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the reminder message with the button
        message = await context.bot.send_message(
            chat_id=chat_id,
            text="🔴 متنساش تقرأ الوِرد",
            reply_markup=reply_markup
        )
        # Store the message ID
        quran_tracker[user_id]["last_wird_reminder_message_id"] = message.message_id
        sheets.update_quran_tracking(quran_tracker)

# Reading confirmation handler
async def confirm_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Load quran tracker
    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    
    # Mark reading as confirmed
    quran_tracker[user_id]["last_read_confirmed"] = True
    quran_tracker[user_id]["unread_pages"] = []
    
    # Try to delete the "متنساش" reminder message if it exists
    wird_reminder_message_id = quran_tracker[user_id].get("last_wird_reminder_message_id")
    if wird_reminder_message_id:
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=wird_reminder_message_id)
        except Exception as e:
            logger.info(f"Could not delete wird reminder message {wird_reminder_message_id} for user {user_id}: {e}")
        # Reset the ID after attempting deletion
        quran_tracker[user_id]["last_wird_reminder_message_id"] = None
        
    sheets.update_quran_tracking(quran_tracker)
    
    # Delete the confirmation message ("هل قرأت الورد؟")
    await query.delete_message()
    
    # Send completion message showing total pages read
    total_read = quran_tracker[user_id]["total_pages_read"]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"أنت خلصت {total_read} صفحات من القرآن الكريم"
    )
    
    # Ask if user wants more
    keyboard = [
        [
            InlineKeyboardButton("نعم", callback_data=MORE_QURAN),
            InlineKeyboardButton("لا", callback_data=NO_MORE_QURAN)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="هل تريد المزيد؟",
        reply_markup=reply_markup
    )

# More Quran handler - MODIFIED to send 5 pages
async def more_quran_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    # Get user's last page
    quran_tracker = sheets.get_quran_tracking()  # from Google Sheets
    last_page = quran_tracker[user_id]["last_page"]
    
    # Determine pages to send (5 more pages)
    start_page = last_page + 1
    end_page = start_page + 4  # Send 5 pages
    
    # Cap at 604 (total Quran pages)
    if start_page > 604:
        start_page = 1
    if end_page > 604:
        end_page = 604
    
    await query.edit_message_text("جاري إرسال المزيد من الصفحات...")
    
    # Send pages
    quran_links = load_quran_image_links()
    for page_num in range(start_page, end_page + 1):
        page_num_str = str(page_num)
        if page_num_str in quran_links:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=quran_links[page_num_str],
                caption=f"صفحة {page_num}"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"عذراً، لم يتم العثور على رابط لصفحة {page_num}."
            )
    
    # Update quran tracker
    quran_tracker[user_id]["last_page"] = end_page
    quran_tracker[user_id]["total_pages_read"] += (end_page - start_page + 1)
    
    # Add these pages to unread pages
    new_pages = list(range(start_page, end_page + 1))
    quran_tracker[user_id]["unread_pages"].extend(new_pages)
    sheets.update_quran_tracking(quran_tracker)
    
    # Ask if user read the pages
    read_keyboard = [
        [
            InlineKeyboardButton("نعم ✅", callback_data=CONFIRM_READ)
        ]
    ]
    read_reply_markup = InlineKeyboardMarkup(read_keyboard)
    
    message = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="هل قرأت الورد؟",
        reply_markup=read_reply_markup
    )
    
    # Save message ID for later reference
    quran_tracker[user_id]["last_reminder_message_id"] = message.message_id
    sheets.update_quran_tracking(quran_tracker)

# No more Quran handler
async def no_more_quran_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("حسناً، سنرسل لك المزيد غداً إن شاء الله.")

# Prophet prayer handler
async def send_prophet_prayer(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="🟢 اللهم صلِ وسلم و زِد و بارك علي سيدنا محمد وعلي آله و صحبه اچمعين"
    )

# Daily Dhikr handler
async def send_daily_dhikr(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="🟡 ادعيه و ذكر اللّه :"
    )
    
    dhikr_messages = [
        "لا حول ولا قوة إلا باللًٰه العليّ العظيم",
        "سبحان الله عدد خلقه و رضا نفسه و زنه عرشه و مداد كلماته",
        "استغفر الله العظيم الذي لا اله إلا هو الحي القيوم واتوب إليه",
        "لا اله الا الله وحده لا شريك له ، له الملك وله الحمد وهو علي كل شئ قدير",
        "اللهم اغفر للمؤمنين و المؤمنات , المسلمين و المسلمات الاحياء منهم والاموات",
        "اللهم أنت ربي لا إله إلا أنت ، خلقتني وأنا عبدك وأنا على عهدك و وعدك ما استطعت ، أعوذ بك من شر ما صنعت ، أبوء لك بنعمتك عليّْ ، وأبوء بذنبي فاغفر لي فإنه لا يغفر الذنوب إلا أنت",
        "آيه الكرسي : \n« ٱللَّهُ لَاۤ إِلَـٰهَ إِلَّا هُوَ ٱلۡحَیُّ ٱلۡقَيُّومُۚ لَا تَأۡخُذُهُۥ سِنَةࣱ وَلَا نَوۡمࣱۚ لَّهُۥ مَا فِی ٱلسَّمَـٰوَ ٰتِ وَمَا فِی ٱلۡأَرۡضِۗ مَن ذَا ٱلَّذِی يَشۡفَعُ عِندَهُۥۤ إِلَّا بِإِذۡنِهِۦۚ يَعۡلَمُ مَا بَيۡنَ أَيۡدِيهِمۡ وَمَا خَلۡفَهُمۡۖ وَلَا يُحِيطُونَ بِشَیۡءࣲ مِّنۡ عِلۡمِهِۦۤ إِلَّا بِمَا شَاۤءَۚ وَسِعَ كُرۡسِيُّهُ ٱلسَّمَـٰوَ ٰتِ وَٱلۡأَرۡضَۖ وَلَا يَـُٔودُهُۥ حِفۡظُهُمَاۚ وَهُوَ ٱلۡعَلِیُّ ٱلۡعَظِيمُ »",
        "اللهم إني أسألك من الخير كله : عاجله وآجله ، ما علمت منه وما لم أعلم ، وأعوذ بك من الشر كله عاجله وآجله ، ما علمت منه وما لم أعلم. اللهم إني أسألك من خير ما سألك عبدك ونبيك ، وأعوذ بك من شر ما استعاذ بك عبدك ونبيك. اللهم إني أسألك الجنة ، وما قرب إليها من قول أو عمل ، وأعوذ بك من النار ، وما قرب إليها من قول أو عمل ، وأسألك أن تجعل كل قضاء قضيته لي خيرا."

    ]
    
    for message in dhikr_messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text=message
        )

# 12-hour Dhikr handler
async def send_12hour_dhikr(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    message_text = " 🟡 بسم الله الذي لايضر مع اسمه شئ في الارض ولا في السماء وهو السميع العليم '' ثلاث مرات '' "
    for _ in range(1):
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text
        )

# Thursday Dhikr handler
async def send_thursday_dhikr(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="مِن مغرب الخَميس إلى مغرب الجُمعة كُلّ ثانية فيها خزائن من الحسناتِ والرّحمات وتفريج الكُربات\n🟣 فليُكثر المرء من الصَّلاة على النَّبي ﷺ",
    )

# Saturday Dhikr handler
async def send_saturday_dhikr(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="🟣 بدايه اسبوع جديد وحاول تبعد عن الذنوب وخصوصا الكبائر عشان بتسبب مشاكل و تعب نفسي و نقص الرزق و عدم استجابه الدعاء و عدم التوفيق و غيره الكثير"
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="بعض من الكبائر : ترك الصلاة , العقوق , الكذب , الغيبة , النميمة , الربا ( من ضمنها القروض ) , شرب الخمر والمخدرات , شتم الاهل ( اهل اي حد ) , الزنا , أكل المال الحرام , الرياء ( التظاهر بالصلاح ) , شهادة الزور , قطع صله الرحم"
    )

# Night prayer handler
async def send_night_prayer(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=" 🟤 تذكير قيام الليل : "
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="وإن لم تستطع فا قرائه اخر آيتان من سوره البقره كفتاه :"
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="بسم الله الرحمن الرحيم ﴿ آمَنَ الرَّسُولُ بِمَا أُنْزِلَ إِلَيْهِ مِنْ رَبِّهِ وَالْمُؤْمِنُونَ ۚ كُلٌّ آمَنَ بِاللَّهِ وَمَلَائِكَتِهِ وَكُتُبِهِ وَرُسُلِهِ لَا نُفَرِّقُ بَيْنَ أَحَدٍ مِنْ رُسُلِهِ ۚ وَقَالُوا سَمِعْنَا وَأَطَعْنَا ۖ غُفْرَانَكَ رَبَّنَا وَإِلَيْكَ الْمَصِيرُ ( ٢٨٥ ) لَا يُكَلِّفُ اللَّهُ نَفْسًا إِلَّا وُسْعَهَا لَهَا مَا كَسَبَتْ وَعَلَيْهَا مَا اكْتَسَبَتْ رَبَّنَا لَا تُؤَاخِذْنَا إِنْ نَسِينَا أَوْ أَخْطَأْنَا رَبَّنَا وَلَا تَحْمِلْ عَلَيْنَا إِصْرًا كَمَا حَمَلْتَهُ عَلَى الَّذِينَ مِنْ قَبْلِنَا رَبَّنَا وَلَا تُحَمِّلْنَا مَا لَا طَاقَةَ لَنَا بِهِ وَاعْفُ عَنَّا وَاغْفِرْ لَنَا وَارْحَمْنَا أَنْتَ مَوْلَانَا فَانْصُرْنَا عَلَى الْقَوْمِ الْكَافِرِينَ ( ٢٨٦ ) ﴾"
    )

# Main function
async def main():
    # Create the Application with persistence
    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    # Add conversation handler for service selection
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_SERVICES: [
                CallbackQueryHandler(service_selection, pattern=f"^({QURAN_SERVICE}|{PROPHET_PRAYER_SERVICE}|{DHIKR_SERVICE}|{NIGHT_PRAYER_SERVICE}|{CONFIRM})$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        name="service_selection",
        persistent=True,
    )
    
    application.add_handler(conv_handler)
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(confirm_reading, pattern=f"^{CONFIRM_READ}$"))
    application.add_handler(CallbackQueryHandler(return_to_wird_callback, pattern=f"^{RETURN_TO_WIRD}$"))
    application.add_handler(CallbackQueryHandler(more_quran_callback, pattern=f"^{MORE_QURAN}$"))
    application.add_handler(CallbackQueryHandler(no_more_quran_callback, pattern=f"^{NO_MORE_QURAN}$"))
    
    # Add admin command handlers
    application.add_handler(CommandHandler("users_count", get_users_count))
    application.add_handler(CommandHandler("users_info", get_users_info))
    
    # Schedule global reminders (for all users)
    # Thursday reminder at 4:00 PM Egypt time
    thursday_time = egypt_time_to_utc(16, 0)  # 4:00 PM Egypt time
    application.job_queue.run_daily(
        send_global_thursday_reminder,
        time=thursday_time,
        days=(3,),  # Thursday (0 is Monday in python-telegram-bot)
        name="global_thursday_reminder"
    )
    
    # Saturday reminder at 9:00 AM Egypt time
    saturday_time = egypt_time_to_utc(9, 0)  # 9:00 AM Egypt time
    application.job_queue.run_daily(
        send_global_saturday_reminder,
        time=saturday_time,
        days=(5,),  # Saturday (0 is Monday in python-telegram-bot)
        name="global_saturday_reminder"
    )
    
    # Start the health check server in a separate thread
    threading.Thread(target=start_health_check_server, daemon=True).start()
    
    # Start the bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Run the bot until the user presses Ctrl-C
    await application.idle()

if __name__ == "__main__":
    asyncio.run(main())
