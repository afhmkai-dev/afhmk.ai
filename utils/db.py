import os
from supabase import create_client

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
        
        # إنشاء مستخدم جديد
        user_data = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "username": username,
            "status": "active",
            "total_images": 0,
            "daily_limit": 10
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

def can_upload(telegram_id: int) -> bool:
    """التحقق من أن المستخدم يمكنه رفع صورة (الحد اليومي)"""
    try:
        user = get_user(telegram_id)
        if not user:
            return True
        
        if user.get('status') == 'blocked':
            return False
        
        total_today = user.get('total_images', 0)
        daily_limit = user.get('daily_limit', 10)
        
        return total_today < daily_limit
        
    except Exception as e:
        print(f"Error in can_upload: {e}")
        return True

def increment_user_images(telegram_id: int):
    """زيادة عدد الصور المحولة للمستخدم"""
    try:
        user = get_user(telegram_id)
        if user:
            new_count = user.get('total_images', 0) + 1
            supabase.table("image_users").update({"total_images": new_count, "last_use_at": "now()"}).eq("telegram_id", telegram_id).execute()
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
            current_views = result.data[0].get('views_count', 0)
            new_views = current_views + 1
            supabase.table("image_links").update({"views_count": new_views}).eq("image_id", image_id).execute()
    except Exception as e:
        print(f"Error in increment_views: {e}")