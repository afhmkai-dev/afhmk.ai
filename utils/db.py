import os
from supabase import create_client
from datetime import date, datetime

# الاتصال بـ Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =================================================================================
# دوال المستخدمين
# =================================================================================

def get_or_create_user(telegram_id: int, first_name: str = None, username: str = None):
    """الحصول على مستخدم أو إنشاؤه إذا لم يكن موجوداً"""
    try:
        # البحث عن المستخدم
        result = supabase.table("image_users").select("*").eq("telegram_id", telegram_id).execute()
        
        if result.data:
            return result.data[0]
        
        # إنشاء مستخدم جديد (متوافق مع هيكل الجدول)
        user_data = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "username": username,
            "status": "active",
            "plan": "free",           # ✅ بدلاً من daily_limit
            "total_images": 0,
            "daily_count": 0,          # ✅ العداد اليومي
            "last_upload_date": None   # ✅ تاريخ آخر رفع
        }
        
        new_user = supabase.table("image_users").insert(user_data).execute()
        return new_user.data[0]
        
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        return None

def get_user(telegram_id: int):
    """جلب بيانات مستخدم"""
    try:
        result = supabase.table("image_users").select("*").eq("telegram_id", telegram_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error in get_user: {e}")
        return None

def get_user_plan_limit(telegram_id: int) -> int:
    """الحصول على الحد اليومي للمستخدم حسب خطته"""
    try:
        user = get_user(telegram_id)
        if not user:
            return 5
        
        plan_name = user.get('plan', 'free')
        
        # جلب الحد من جدول الخطط
        plan = supabase.table("image_plans").select("daily_limit").eq("plan_name", plan_name).execute()
        if plan.data:
            return plan.data[0].get('daily_limit', 5)
        
        return 5
    except Exception as e:
        print(f"Error in get_user_plan_limit: {e}")
        return 5

def can_upload(telegram_id: int):
    """التحقق من أن المستخدم يمكنه رفع صورة (الحد اليومي)"""
    try:
        user = get_or_create_user(telegram_id)
        if not user:
            return False, "حدث خطأ في النظام"
        
        # التحقق من الحظر
        if user.get('status') == 'blocked':
            return False, "⛔ تم حظر حسابك"
        
        daily_limit = get_user_plan_limit(telegram_id)
        
        # التحقق من التاريخ (إعادة تعيين العداد اليومي)
        last_date = user.get('last_upload_date')
        today = date.today()
        
        if last_date != str(today):
            # يوم جديد، إعادة تعيين العداد
            supabase.table("image_users").update({
                "daily_count": 0,
                "last_upload_date": today.isoformat()
            }).eq("telegram_id", telegram_id).execute()
            daily_count = 0
        else:
            daily_count = user.get('daily_count', 0) or 0
        
        # التحقق من الحد اليومي
        if daily_count >= daily_limit:
            plan_name = user.get('plan', 'free')
            if plan_name == 'free':
                return False, f"⏳ وصلت للحد اليومي! ({daily_limit}/5)\n💎 اشترك في الباقة المميزة عبر /premium"
            else:
                return False, f"⏳ وصلت للحد اليومي! ({daily_limit}/100)\n🔄 حاول غداً"
        
        remaining = daily_limit - daily_count
        return True, remaining
        
    except Exception as e:
        print(f"Error in can_upload: {e}")
        return False, "حدث خطأ في النظام"

def increment_user_images(telegram_id: int):
    """زيادة عدد الصور المحولة للمستخدم (يومي وإجمالي)"""
    try:
        today = date.today()
        
        # جلب القيم الحالية
        user = get_user(telegram_id)
        if user:
            new_daily = (user.get('daily_count', 0) or 0) + 1
            new_total = (user.get('total_images', 0) or 0) + 1
            
            supabase.table("image_users").update({
                "daily_count": new_daily,
                "total_images": new_total,
                "last_upload_date": today.isoformat()
            }).eq("telegram_id", telegram_id).execute()
            
            print(f"Updated user {telegram_id}: daily={new_daily}, total={new_total}")
            
    except Exception as e:
        print(f"Error in increment_user_images: {e}")

# =================================================================================
# دوال الصور
# =================================================================================

def save_image_link(image_id: str, user_telegram_id: int, first_name: str, username: str, original_url: str, short_url: str, file_size: int):
    """حفظ رابط الصورة في قاعدة البيانات"""
    try:
        data = {
            "image_id": image_id,
            "user_telegram_id": user_telegram_id,
            "first_name": first_name,
            "username": username,
            "original_url": original_url,
            "short_url": short_url,
            "file_size": file_size,
            "views_count": 0
        }
        result = supabase.table("image_links").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error in save_image_link: {e}")
        return None

def get_image_by_id(image_id: str):
    """جلب بيانات الصورة عن طريق المعرف"""
    try:
        result = supabase.table("image_links").select("*").eq("image_id", image_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error in get_image_by_id: {e}")
        return None

def increment_views(image_id: str):
    """زيادة عدد المشاهدات"""
    try:
        # الطريقة الصحيحة: جلب العدد الحالي ثم زيادته
        result = supabase.table("image_links").select("views_count").eq("image_id", image_id).execute()
        if result.data:
            current_views = result.data[0].get('views_count', 0) or 0
            new_views = current_views + 1
            supabase.table("image_links").update({"views_count": new_views}).eq("image_id", image_id).execute()
            print(f"Updated views for {image_id}: {new_views}")
    except Exception as e:
        print(f"Error in increment_views: {e}")

def get_user_stats(telegram_id: int):
    """الحصول على إحصائيات المستخدم الكاملة"""
    try:
        user = get_user(telegram_id)
        if not user:
            return None
        
        daily_limit = get_user_plan_limit(telegram_id)
        daily_count = user.get('daily_count', 0) or 0
        total_images = user.get('total_images', 0) or 0
        plan = user.get('plan', 'free')
        
        return {
            "total_images": total_images,
            "daily_count": daily_count,
            "daily_limit": daily_limit,
            "remaining": daily_limit - daily_count,
            "plan": plan,
            "status": user.get('status', 'active')
        }
    except Exception as e:
        print(f"Error in get_user_stats: {e}")
        return None