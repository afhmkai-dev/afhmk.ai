# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from supabase import create_client

# إعدادات Flask
admin_app = Flask(__name__)
admin_app.secret_key = os.environ.get('ADMIN_SECRET_KEY', 'your-secret-key-here')

# الاتصال بـ Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# كلمة مرور الدخول للوحة التحكم (يمكن تغييرها)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# =================================================================================
# دوال مساعدة
# =================================================================================

def check_auth():
    """التحقق من المصادقة"""
    auth_token = request.cookies.get('admin_auth')
    return auth_token == ADMIN_PASSWORD

def get_stats():
    """جلب الإحصائيات العامة"""
    try:
        # إجمالي المستخدمين
        users_result = supabase.table("image_users").select("*", count="exact").execute()
        total_users = users_result.count or 0
        
        # المستخدمين المميزين
        premium_result = supabase.table("image_users").select("*", count="exact").eq("plan", "premium_monthly").execute()
        premium_monthly = premium_result.count or 0
        
        premium_yearly_result = supabase.table("image_users").select("*", count="exact").eq("plan", "premium_yearly").execute()
        premium_yearly = premium_yearly_result.count or 0
        
        premium_users = premium_monthly + premium_yearly
        free_users = total_users - premium_users
        
        # إجمالي الصور المحولة
        images_result = supabase.table("image_links").select("*", count="exact").execute()
        total_images = images_result.count or 0
        
        # إجمالي المشاهدات
        views_result = supabase.table("image_links").select("views_count").execute()
        total_views = sum(item.get('views_count', 0) or 0 for item in views_result.data)
        
        # الصور اليوم
        today = datetime.now().date().isoformat()
        today_images = 0
        for item in images_result.data:
            created_at = item.get('created_at')
            if created_at and created_at.startswith(today):
                today_images += 1
        
        return {
            "total_users": total_users,
            "premium_users": premium_users,
            "free_users": free_users,
            "premium_monthly": premium_monthly,
            "premium_yearly": premium_yearly,
            "total_images": total_images,
            "total_views": total_views,
            "today_images": today_images,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"Error in get_stats: {e}")
        return {}

def get_all_users():
    """جلب جميع المستخدمين مع إحصائياتهم"""
    try:
        users_result = supabase.table("image_users").select("*").order("created_at", desc=True).execute()
        users = users_result.data
        
        today = datetime.now().date().isoformat()
        user_list = []
        
        for user in users:
            telegram_id = user.get('telegram_id')
            
            # جلب عدد صور المستخدم اليوم
            today_count = supabase.table("image_links").select("*", count="exact").eq("user_telegram_id", telegram_id).gte("created_at", today).execute()
            
            # جلب إجمالي صور المستخدم
            total_count = supabase.table("image_links").select("*", count="exact").eq("user_telegram_id", telegram_id).execute()
            
            # جلب إجمالي مشاهدات صور المستخدم
            views_result = supabase.table("image_links").select("views_count").eq("user_telegram_id", telegram_id).execute()
            total_views = sum(item.get('views_count', 0) or 0 for item in views_result.data)
            
            user_list.append({
                "user_id": telegram_id,
                "first_name": user.get('first_name', '-'),
                "username": user.get('username', '-'),
                "status": "premium" if user.get('plan') != 'free' else "free",
                "plan": user.get('plan', 'free'),
                "daily_limit": user.get('daily_limit', 5),
                "today_count": today_count.count or 0,
                "total_images": total_count.count or 0,
                "total_views": total_views,
                "created_at": user.get('created_at', '')
            })
        
        return user_list
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        return []

def get_plans():
    """جلب جميع الخطط من قاعدة البيانات"""
    try:
        result = supabase.table("image_plans").select("*").execute()
        return {plan['plan_name']: plan for plan in result.data}
    except Exception as e:
        print(f"Error in get_plans: {e}")
        return {}

def get_settings():
    """جلب الإعدادات من قاعدة البيانات"""
    try:
        result = supabase.table("image_settings").select("*").execute()
        return {item['setting_key']: item['setting_value'] for item in result.data}
    except Exception as e:
        print(f"Error in get_settings: {e}")
        return {}

# =================================================================================
# صفحات الواجهة الأمامية
# =================================================================================

@admin_app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """صفحة تسجيل الدخول"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            resp = redirect(url_for('admin_dashboard'))
            resp.set_cookie('admin_auth', password, max_age=86400)  # 24 ساعة
            return resp
        return render_template('admin_login.html', error="كلمة المرور غير صحيحة")
    return render_template('admin_login.html')

@admin_app.route('/admin/logout')
def admin_logout():
    """تسجيل الخروج"""
    resp = redirect(url_for('admin_login'))
    resp.set_cookie('admin_auth', '', expires=0)
    return resp

@admin_app.route('/admin/dashboard')
def admin_dashboard():
    """لوحة التحكم الرئيسية"""
    if not check_auth():
        return redirect(url_for('admin_login'))
    
    stats = get_stats()
    users = get_all_users()
    plans = get_plans()
    settings = get_settings()
    
    # الحد اليومي المجاني من الإعدادات أو من الخطط
    free_limit = plans.get('free', {}).get('daily_limit', 5)
    
    return render_template('admin.html', 
                          stats=stats, 
                          users=users, 
                          plans=plans,
                          settings=settings,
                          free_limit=free_limit)

@admin_app.route('/admin/prices', methods=['GET', 'POST'])
def admin_prices():
    """صفحة إدارة الأسعار والخطط"""
    if not check_auth():
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        try:
            # تحديث الخطط في جدول image_plans
            plans_data = {
                'free': {'daily_limit': int(request.form.get('free_limit', 5))},
                'premium_monthly': {
                    'daily_limit': int(request.form.get('premium_limit', 100)),
                    'price': int(request.form.get('price_monthly', 5)),
                    'duration_days': int(request.form.get('duration_monthly', 30))
                },
                'premium_yearly': {
                    'daily_limit': int(request.form.get('premium_limit', 100)),
                    'price': int(request.form.get('price_yearly', 50)),
                    'duration_days': int(request.form.get('duration_yearly', 365))
                }
            }
            
            for plan_name, plan_data in plans_data.items():
                supabase.table("image_plans").update(plan_data).eq("plan_name", plan_name).execute()
            
            # تحديث الإعدادات
            settings_data = {
                'free_daily_limit': str(request.form.get('free_limit', 5)),
                'premium_daily_limit': str(request.form.get('premium_limit', 100)),
                'max_file_size_mb': request.form.get('max_file_size', '5')
            }
            
            for key, value in settings_data.items():
                supabase.table("image_settings").update({"setting_value": value}).eq("setting_key", key).execute()
            
            return render_template('prices.html', 
                                  plans=plans_data,
                                  settings=settings_data,
                                  msg="تم حفظ الإعدادات بنجاح!",
                                  msg_type="success")
        except Exception as e:
            return render_template('prices.html', 
                                  plans={},
                                  settings={},
                                  msg=f"خطأ: {e}",
                                  msg_type="error")
    
    # عرض الصفحة
    plans = get_plans()
    settings = get_settings()
    
    return render_template('prices.html', plans=plans, settings=settings)

# =================================================================================
# API endpoints
# =================================================================================

@admin_app.route('/admin/upgrade-user', methods=['POST'])
def upgrade_user():
    """ترقية مستخدم"""
    if not check_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    try:
        user_id = request.form.get('user_id')
        plan_name = request.form.get('plan_name')
        
        # جلب تفاصيل الخطة
        plan = supabase.table("image_plans").select("*").eq("plan_name", plan_name).execute()
        if not plan.data:
            return jsonify({"success": False, "message": "الخطة غير موجودة"})
        
        plan_data = plan.data[0]
        daily_limit = plan_data.get('daily_limit', 100)
        
        # تحديث المستخدم
        supabase.table("image_users").update({
            "plan": plan_name,
            "daily_limit": daily_limit
        }).eq("telegram_id", user_id).execute()
        
        return jsonify({"success": True, "message": f"تم ترقية المستخدم إلى {plan_name}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@admin_app.route('/admin/downgrade-user', methods=['POST'])
def downgrade_user():
    """خفض مستخدم إلى مجاني"""
    if not check_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    try:
        user_id = request.form.get('user_id')
        
        # جلب الحد المجاني
        free_plan = supabase.table("image_plans").select("*").eq("plan_name", "free").execute()
        daily_limit = free_plan.data[0].get('daily_limit', 5) if free_plan.data else 5
        
        supabase.table("image_users").update({
            "plan": "free",
            "daily_limit": daily_limit
        }).eq("telegram_id", user_id).execute()
        
        return jsonify({"success": True, "message": "تم خفض المستخدم إلى خطة مجانية"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@admin_app.route('/admin/update-user-limit', methods=['POST'])
def update_user_limit():
    """تعديل الحد اليومي لمستخدم"""
    if not check_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    try:
        user_id = request.form.get('user_id')
        daily_limit = int(request.form.get('daily_limit', 5))
        
        supabase.table("image_users").update({
            "daily_limit": daily_limit
        }).eq("telegram_id", user_id).execute()
        
        return jsonify({"success": True, "message": "تم تحديث الحد اليومي"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@admin_app.route('/admin/send-notification', methods=['POST'])
def send_notification():
    """إرسال إشعار للمستخدمين (API للبوت)"""
    if not check_auth():
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    try:
        data = request.get_json()
        target = data.get('target')
        user_id = data.get('user_id')
        message = data.get('message')
        
        # هنا ستضيف دالة إرسال الإشعار عبر البوت
        # يمكن تخزين الإشعارات في قاعدة بيانات ليرسلها البوت لاحقاً
        
        return jsonify({"success": True, "message": "تم إرسال الإشعار"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# =================================================================================
# تشغيل التطبيق (للتطوير المحلي)
# =================================================================================
if __name__ == '__main__':
    admin_app.run(host='0.0.0.0', port=5001, debug=True)