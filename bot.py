# -*- coding: utf-8 -*-
import os
import secrets
import logging
import threading
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client
from PIL import Image

# =================================================================================
# خادم Flask (لإبقاء السيرفر نشطاً)
# =================================================================================
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health_check():
    return jsonify({"status": "ok", "service": "image-link-bot"}), 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# =================================================================================
# إعدادات البيئة
# =================================================================================
TOKEN = os.environ.get('BOT_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
RENDER_URL = os.environ.get('RENDER_URL', 'ime-link-bot.onrender.com')
SHORTENER_URL = f"https://{RENDER_URL}"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# =================================================================================
# دوال المساعدة
# =================================================================================
def generate_image_id() -> str:
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10]

def compress_image(input_path, output_path):
    try:
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            if img.width > 800 or img.height > 800:
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            img.save(output_path, "JPEG", optimize=True, quality=60)
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False

# =================================================================================
# أوامر البوت
# =================================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖼️ أرسل صورة وسأعطيك رابطاً مباشراً")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    temp_raw = f"temp_raw_{user_id}.jpg"
    temp_comp = f"temp_comp_{user_id}.jpg"
    
    try:
        await update.message.reply_text("🖼️ جاري المعالجة...")
        
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(temp_raw)
        
        if not compress_image(temp_raw, temp_comp):
            await update.message.reply_text("❌ فشل في معالجة الصورة")
            return
        
        image_id = generate_image_id()
        
        with open(temp_comp, 'rb') as f:
            supabase.storage.from_("image-links").upload(
                path=f"{user_id}/{image_id}.jpg",
                file=f,
                file_options={"content-type": "image/jpeg", "upsert": "true"}
            )
        
        short_url = f"{SHORTENER_URL}/i/{image_id}"
        
        await update.message.reply_text(
            f"✅ **تم تحويل صورتك!**\n\n"
            f"🔗 {short_url}",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")
    finally:
        for path in [temp_raw, temp_comp]:
            if os.path.exists(path):
                os.remove(path)

# =================================================================================
# تشغيل البوت
# =================================================================================
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    print("✅ Image Link Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()