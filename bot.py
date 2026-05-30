# -*- coding: utf-8 -*-
import os
import secrets
import logging
import threading
from datetime import datetime, date
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
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')  # ✅ استخدم هذا
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
        print(f"Error in compress_image: {e}")
        return False

# =================================================================================
# دوال المستخدمين والخطط (باستخدام جدول image_plans)
# =================================================================================

def get_plan_from_db(plan_name: str):
    """جلب بيانات الخطة من جدول image_plans"""
    try:
        result = supabase.table("image_plans").select("*").eq("plan_name", plan_name).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"Error in get_plan_from_db: {e}")
        return None

def get_user_plan_from_db(telegram_id: int):
    """الحصول على خطة المستخدم من قاعدة البيانات"""
    try:
        user = supabase.table("image_users").select("plan").eq("telegram_id", telegram_id).execute()
        if not user.data:
            return 'free'
        return user.data[0].get('plan', 'free')
    except Exception as e:
        print(f"Error in get_user_plan_from_db: {e}")
        return 'free'

def get_user_daily_limit_from_plan(telegram_id: int) -> int:
    """الحصول على الحد اليومي للمستخدم من جدول الخطط"""
    try:
        plan_name = get_user_plan_from_db(telegram_id)
        plan = get_plan_from_db(plan_name)
        if plan:
            return plan.get('daily_limit', 5)
        return 5
    except Exception as e:
        print(f"Error in get_user_daily_limit_from_plan: {e}")
        return 5

def get_or_create_image_user(telegram_id: int, first_name: str = None, username: str = None):
    """الحصول على مستخدم أو إنشاؤه"""
    try:
        # البحث عن المستخدم
        result = supabase.table("image_users").select("*").eq("telegram_id", telegram_id).execute()
        
        if result.data:
            return result.data[0]
        
        # ✅ جلب الحد الافتراضي من جدول الخطط للخطة المجانية
        default_plan = get_plan_from_db('free')
        default_limit = default_plan.get('daily_limit', 5) if default_plan else 5
        
        user_data = {
            "telegram_id": telegram_id,
            "first_name": first_name or "",
            "username": username or "",
            "status": "active",
            "total_images": 0,
            "daily_limit": default_limit,
            "plan": "free",
            "last_use_at": datetime.now().isoformat()
        }
        
        print(f"Creating user: {telegram_id} with daily_limit: {default_limit}")
        
        new_user = supabase.table("image_users").insert(user_data).execute()
        return new_user.data[0]
        
    except Exception as e:
        print(f"Error in get_or_create_image_user: {e}")
        return None

def get_user(telegram_id: int):
    """جلب بيانات مستخدم"""
    try:
        result = supabase.table("image_users").select("*").eq("telegram_id", telegram_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error in get_user: {e}")
        return None

def can_user_upload(telegram_id: int):
    """التحقق من إمكانية رفع الصورة (الحد اليومي)"""
    try:
        user = get_or_create_image_user(telegram_id)
        if not user:
            return False, "حدث خطأ في النظام"
        
        # التحقق من الحظر
        if user.get('status') == 'blocked':
            return False, "⛔ تم حظر حسابك، يرجى التواصل مع الدعم"
        
        # ✅ جلب الحد اليومي من جدول الخطط
        daily_limit = get_user_daily_limit_from_plan(telegram_id)
        
        # ✅ تحديث daily_limit في جدول المستخدم إذا تغير (مهم عند ترقية المستخدم)
        current_limit = user.get('daily_limit', 5)
        if current_limit != daily_limit:
            supabase.table("image_users").update({
                "daily_limit": daily_limit
            }).eq("telegram_id", telegram_id).execute()
            print(f"Updated daily_limit for user {telegram_id}: {current_limit} -> {daily_limit}")
        
        today = date.today().isoformat()
        
        # جلب عدد الصور المرفوعة اليوم من جدول image_links
        result = supabase.table("image_links").select("id", "created_at").eq("user_telegram_id", telegram_id).execute()
        
        daily_count = 0
        for link in result.data:
            created_at = link.get('created_at')
            if created_at and created_at.startswith(today):
                daily_count += 1
        
        if daily_count >= daily_limit:
            plan_name = user.get('plan', 'free')
            if plan_name == 'free':
                return False, f"⏳ **لقد وصلت للحد اليومي!**\n\n📊 الحد اليومي: {daily_limit} صورة\n💎 لرفع المزيد، اشترك في الباقة المميزة عبر /premium"
            else:
                return False, f"⏳ **لقد وصلت للحد اليومي!**\n\n📊 الحد اليومي: {daily_limit} صورة\n🔄 يمكنك المحاولة غداً"
        
        remaining = daily_limit - daily_count
        return True, remaining
        
    except Exception as e:
        print(f"Error in can_user_upload: {e}")
        return False, "حدث خطأ في النظام"

def increment_user_upload(telegram_id: int):
    """زيادة عدد الصور المحولة للمستخدم"""
    try:
        user = get_user(telegram_id)
        if user:
            new_total = (user.get('total_images', 0) or 0) + 1
            
            supabase.table("image_users").update({
                "total_images": new_total,
                "last_use_at": datetime.now().isoformat()
            }).eq("telegram_id", telegram_id).execute()
            
            print(f"Updated user {telegram_id}: total_images={new_total}")
        
    except Exception as e:
        print(f"Error in increment_user_upload: {e}")

# =================================================================================
# أوامر البوت
# =================================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    
    # تسجيل المستخدم في قاعدة البيانات
    user = get_or_create_image_user(user_id, first_name, username)
    
    # جلب الحد اليومي من جدول الخطط
    daily_limit = get_user_daily_limit_from_plan(user_id)
    
    await update.message.reply_text(
        f"🖼️ **مرحباً بك في بوت تحويل الصور!**\n\n"
        f"📤 أرسل لي أي صورة وسأقوم بـ:\n"
        f"• ضغطها تلقائياً\n"
        f"• رفعها إلى السحابة\n"
        f"• إعطائك رابطاً مختصراً\n\n"
        f"📊 **حدك اليومي:** {daily_limit} صورة\n"
        f"💎 اشترك في الباقة المميزة للحصول على 100 صورة يومياً!\n\n"
        f"🔧 **الأوامر المتاحة:**\n"
        f"/stats - عرض إحصائياتك\n"
        f"/myplan - عرض خطتك الحالية\n"
        f"/premium - معلومات الاشتراك المميز"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /stats - عرض إحصائيات المستخدم"""
    user_id = update.message.from_user.id
    
    user = get_or_create_image_user(user_id, update.message.from_user.first_name, update.message.from_user.username)
    
    if user:
        total = user.get('total_images', 0) or 0
        plan = user.get('plan', 'free')
        
        # ✅ جلب الحد اليومي من جدول الخطط
        daily_limit = get_user_daily_limit_from_plan(user_id)
        
        # حساب عدد الصور اليوم من جدول image_links
        today = date.today().isoformat()
        result = supabase.table("image_links").select("id", "created_at").eq("user_telegram_id", user_id).execute()
        
        daily_count = 0
        for link in result.data:
            created_at = link.get('created_at')
            if created_at and created_at.startswith(today):
                daily_count += 1
        
        remaining = daily_limit - daily_count if daily_limit - daily_count > 0 else 0
        
        plan_emoji = "💎" if plan != 'free' else "🎁"
        plan_name = "مميز" if plan != 'free' else "مجاني"
        
        await update.message.reply_text(
            f"📊 **إحصائياتك الشخصية**\n\n"
            f"{plan_emoji} **الخطة:** {plan_name}\n"
            f"🖼️ **إجمالي الصور:** {total}\n"
            f"📈 **اليوم:** {daily_count} / {daily_limit}\n"
            f"⏳ **المتبقي اليوم:** {remaining}\n\n"
            f"✨ أرسل صوراً جديدة لزيادة رصيدك!"
        )
    else:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة مرة أخرى")

async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /myplan - عرض خطة المستخدم الحالية"""
    user_id = update.message.from_user.id
    user = get_or_create_image_user(user_id)
    
    if user:
        plan = user.get('plan', 'free')
        daily_limit = get_user_daily_limit_from_plan(user_id)
        
        # جلب تفاصيل الخطة من جدول image_plans
        plan_details = get_plan_from_db(plan)
        
        if plan != 'free' and plan_details:
            price = plan_details.get('price', 0)
            duration = plan_details.get('duration_days', 0)
            duration_text = f"{duration} يوماً" if duration == 30 else f"{duration} يوماً"
            
            await update.message.reply_text(
                f"💎 **خطتك الحالية: مميز**\n\n"
                f"📊 حدك اليومي: {daily_limit} صورة\n"
                f"💰 السعر: {price}$ لكل {duration_text}\n\n"
                f"لتجديد اشتراكك، استخدم الأمر /premium"
            )
        else:
            # جلب سعر الخطة المميزة
            premium_plan = get_plan_from_db('premium_monthly')
            premium_price = premium_plan.get('price', 5) if premium_plan else 5
            
            await update.message.reply_text(
                f"🎁 **خطتك الحالية: مجانية**\n\n"
                f"📊 حدك اليومي: {daily_limit} صورة\n\n"
                f"💎 للترقية إلى الخطة المميزة:\n"
                f"• {daily_limit} → 100 صورة يومياً\n"
                f"• السعر: {premium_price}$ فقط\n\n"
                f"استخدم الأمر /premium للاشتراك"
            )
    else:
        await update.message.reply_text("❌ حدث خطأ")

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /premium - عرض خطط الاشتراك من قاعدة البيانات"""
    try:
        # جلب الخطط من قاعدة البيانات
        result = supabase.table("image_plans").select("*").eq("is_active", True).execute()
        plans = result.data
        
        if not plans:
            await update.message.reply_text("💎 خطط الاشتراك غير متاحة حالياً، يرجى المحاولة لاحقاً")
            return
        
        message = "💎 **باقات الاشتراك المميز**\n\n"
        
        for plan in plans:
            plan_name = plan.get('plan_name')
            daily_limit = plan.get('daily_limit')
            price = plan.get('price')
            duration = plan.get('duration_days')
            
            if plan_name == 'free':
                message += f"🎁 **مجاني:**\n• {daily_limit} صورة يومياً\n• السعر: مجاني\n\n"
            elif duration == 30:
                message += f"💎 **شهري:**\n• {daily_limit} صورة يومياً\n• السعر: {price}$ / شهر\n\n"
            elif duration == 365:
                message += f"👑 **سنوي:**\n• {daily_limit} صورة يومياً\n• السعر: {price}$ / سنة (توفير 16%)\n\n"
        
        message += "✨ **طرق الدفع المتاحة قريباً:**\n• ⭐ نجوم Telegram\n• 💳 بطاقات الائتمان\n\nللاشتراك، تواصل مع المطور: @Alshabany_Ai"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        print(f"Error in premium_command: {e}")
        await update.message.reply_text("❌ حدث خطأ في عرض الخطط")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    
    temp_raw = f"temp_raw_{user_id}.jpg"
    temp_comp = f"temp_comp_{user_id}.jpg"
    
    try:
        # ✅ التحقق من الحد اليومي
        can_upload, message = can_user_upload(user_id)
        if not can_upload:
            await update.message.reply_text(message)
            return
        
        await update.message.reply_text("🖼️ جاري المعالجة...")
        
        # تحميل الصورة
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(temp_raw)
        
        # ضغط الصورة
        if not compress_image(temp_raw, temp_comp):
            await update.message.reply_text("❌ فشل في معالجة الصورة")
            return
        
        # إنشاء معرف فريد
        image_id = generate_image_id()
        
        # رفع الصورة إلى Supabase Storage
        with open(temp_comp, 'rb') as f:
            supabase.storage.from_("image-links").upload(
                path=f"{user_id}/{image_id}.jpg",
                file=f,
                file_options={"content-type": "image/jpeg", "upsert": "true"}
            )
        
        # الحصول على الرابط الأصلي
        bucket_name = "image-links"
        file_path = f"{user_id}/{image_id}.jpg"
        original_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}"
        
        # الرابط المختصر
        short_url = f"{SHORTENER_URL}/i/{image_id}"
        
        # حفظ البيانات في جدول image_links
        file_size = os.path.getsize(temp_comp) // 1024
        supabase.table("image_links").insert({
            "image_id": image_id,
            "user_telegram_id": user_id,
            "first_name": first_name,
            "username": username,
            "original_url": original_url,
            "short_url": short_url,
            "file_size": file_size
        }).execute()
        
        # ✅ زيادة العداد
        increment_user_upload(user_id)
        
        # إرسال الرابط للمستخدم مع المتبقي
        await update.message.reply_text(
            f"✅ **تم تحويل صورتك!**\n\n"
            f"🔗 {short_url}\n\n"
            f"📊 متبقي لك اليوم: {message} صورة\n"
            f"💡 استخدم /stats لعرض إحصائياتك",
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Error in handle_image: {e}")
        await update.message.reply_text(f"❌ حدث خطأ: حاول مرة أخرى")
    finally:
        for path in [temp_raw, temp_comp]:
            if os.path.exists(path):
                os.remove(path)

# =================================================================================
# تشغيل البوت
# =================================================================================
def main():
    application = Application.builder().token(TOKEN).build()
    
    # الأوامر الأساسية
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("myplan", myplan_command))
    application.add_handler(CommandHandler("premium", premium_command))
    
    # معالجة الصور
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    # إعداد أوامر البوت في واجهة تليجرام
    bot_commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("stats", "إحصائياتك الشخصية"),
        BotCommand("myplan", "عرض خطتك الحالية"),
        BotCommand("premium", "معلومات الاشتراك المميز"),
    ]
    
    print("✅ Image Link Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()