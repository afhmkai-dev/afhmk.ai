# -*- coding: utf-8 -*-
import os
import secrets
import logging
import asyncio
from datetime import datetime
from flask import Flask, redirect
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد التسجيل
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البيئة
TOKEN = os.environ.get('BOT_TOKEN')
PORT = int(os.environ.get('PORT', 10000))

# إعدادات السيرفر المختصر
SHORTENER_URL = os.environ.get('SHORTENER_URL', 'https://image-link-bot.onrender.com')

# استيرادات المشروع
from utils.db import get_or_create_user, can_upload, increment_user_images, save_image_link, get_image_by_id, increment_views
from utils.storage import compress_image, upload_to_supabase

# إنشاء تطبيق Flask للروابط المختصرة
flask_app = Flask(__name__)

# =================================================================================
# دوال مساعدة
# =================================================================================

def generate_image_id() -> str:
    """إنشاء معرف فريد للصورة"""
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10]

def get_short_url(image_id: str) -> str:
    """إنشاء رابط مختصر للصورة"""
    return f"{SHORTENER_URL}/i/{image_id}"

# =================================================================================
# أوامر البوت
# =================================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /start"""
    user = update.message.from_user
    get_or_create_user(user.id, user.first_name, user.username)
    
    await update.message.reply_text(
        f"🖼️ **مرحباً {user.first_name}!**\n\n"
        f"أنا بوت تحويل الصور إلى روابط.\n\n"
        f"📤 **كيفية الاستخدام:**\n"
        f"• أرسل أي صورة وسأقوم بتحويلها إلى رابط مباشر\n"
        f"• الرابط قابل للمشاركة في أي مكان\n\n"
        f"✨ **المميزات:**\n"
        f"• ضغط تلقائي للصور\n"
        f"• روابط قصيرة وسريعة\n"
        f"• تخزين دائم\n\n"
        f"🚀 أرسل صورتك الآن!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /help"""
    await update.message.reply_text(
        f"📖 **مساعدة البوت**\n\n"
        f"• أرسل صورة ← أحصل على رابط مباشر\n"
        f"• رابط الصورة صالح للمشاركة للأبد\n"
        f"• يمكنك مشاركة الرابط في أي مكان\n\n"
        f"📊 **إحصائياتك:**\n"
        f"• يمكنك معرفة عدد صورك عبر /stats"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /stats"""
    user = update.message.from_user
    user_data = get_or_create_user(user.id, user.first_name, user.username)
    
    if user_data:
        total = user_data.get('total_images', 0)
        limit = user_data.get('daily_limit', 10)
        status = user_data.get('status', 'active')
        
        status_emoji = "✅" if status == 'active' else "❌"
        
        await update.message.reply_text(
            f"📊 **إحصائياتك**\n\n"
            f"🖼️ عدد صورك: {total}\n"
            f"📈 الحد اليومي: {limit}/{limit}\n"
            f"🔘 الحالة: {status_emoji} {status}\n\n"
            f"✨ أرسل صوراً جديدة لزيادة عدد صورك!"
        )
    else:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة مرة أخرى.")

# =================================================================================
# معالجة الصور
# =================================================================================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الصورة وتحويلها إلى رابط"""
    user = update.message.from_user
    user_id = user.id
    
    temp_raw = f"temp_raw_{user_id}.jpg"
    temp_compressed = f"temp_comp_{user_id}.jpg"
    
    try:
        # التحقق من صلاحية المستخدم
        if not can_upload(user_id):
            await update.message.reply_text(
                "⏳ **لقد وصلت للحد اليومي!**\n\n"
                f"يمكنك إرسال صور جديدة غداً.\n\n"
                f"📊 الحد اليومي: 10 صور"
            )
            return
        
        # إرسال رسالة المعالجة
        status_msg = await update.message.reply_text("🖼️ جاري معالجة الصورة...")
        
        # تحميل الصورة
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(temp_raw)
        
        # ضغط الصورة
        if not compress_image(temp_raw, temp_compressed):
            await update.message.reply_text("❌ فشل في معالجة الصورة")
            return
        
        # الحصول على حجم الملف
        file_size = os.path.getsize(temp_compressed) // 1024  # KB
        
        # إنشاء معرف فريد للصورة
        image_id = generate_image_id()
        
        # رفع الصورة إلى Supabase
        original_url = upload_to_supabase(user_id, temp_compressed, f"{image_id}.jpg")
        
        if not original_url:
            await update.message.reply_text("❌ فشل في رفع الصورة")
            return
        
        # إنشاء رابط مختصر
        short_url = get_short_url(image_id)
        
        # حفظ البيانات في قاعدة البيانات
        save_image_link(
            image_id=image_id,
            user_telegram_id=user_id,
            first_name=user.first_name,
            username=user.username,
            original_url=original_url,
            short_url=short_url,
            file_size=file_size
        )
        
        # تحديث إحصائيات المستخدم
        increment_user_images(user_id)
        
        # إرسال النتيجة
        await update.message.reply_text(
            f"✅ **تم تحويل صورتك بنجاح!**\n\n"
            f"🔗 **رابط الصورة:**\n"
            f"`{short_url}`\n\n"
            f"📏 الحجم: {file_size} KB\n"
            f"🖼️ [عرض الصورة]({short_url})\n\n"
            f"✨ الرابط صالح للأبد ويمكن مشاركته",
            disable_web_page_preview=True
        )
        
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in handle_image: {e}")
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)[:100]}")
        
    finally:
        # تنظيف الملفات المؤقتة
        for path in [temp_raw, temp_compressed]:
            if os.path.exists(path):
                os.remove(path)

# =================================================================================
# تشغيل البوت
# =================================================================================

async def set_commands(application: Application):
    """تعيين قائمة الأوامر"""
    commands = [
        BotCommand("start", "🚀 بدء الاستخدام"),
        BotCommand("help", "📖 المساعدة"),
        BotCommand("stats", "📊 إحصائياتي"),
    ]
    await application.bot.set_my_commands(commands)

def main():
    """تشغيل البوت"""
    application = Application.builder().token(TOKEN).build()
    
    # إضافة الأوامر
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    # تعيين الأوامر
    asyncio.run(set_commands(application))
    
    print("=" * 60)
    print("🖼️ Image Link Bot - تحويل الصور إلى روابط")
    print(f"✅ البوت شغال @{os.environ.get('BOT_USERNAME', 'ime_link_bot')}")
    print("=" * 60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()