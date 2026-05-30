# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, redirect, url_for, make_response
from supabase import create_client

# =================================================================================
# إعدادات البيئة
# =================================================================================
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-here')

logging.basicConfig(level=logging.INFO)

# =================================================================================
# دوال المساعدة للمشاهدة
# =================================================================================

def get_image_by_id(image_id: str):
    try:
        result = supabase.table("image_links").select("*").eq("image_id", image_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logging.error(f"Error get_image_by_id: {e}")
        return None

def increment_views(image_id: str):
    try:
        result = supabase.table("image_links").select("views_count").eq("image_id", image_id).execute()
        if result.data:
            current_views = result.data[0].get('views_count', 0) or 0
            supabase.table("image_links").update({"views_count": current_views + 1}).eq("image_id", image_id).execute()
    except Exception as e:
        logging.error(f"Error increment_views: {e}")

# =================================================================================
# دوال المساعدة للوحة التحكم
# =================================================================================

def check_auth():
    auth_token = request.cookies.get('admin_auth')
    return auth_token == ADMIN_PASSWORD

def get_stats():
    try:
        users_result = supabase.table("image_users").select("*", count="exact").execute()
        total_users = users_result.count or 0
        
        premium_monthly = supabase.table("image_users").select("*", count="exact").eq("plan", "premium_monthly").execute()
        premium_yearly = supabase.table("image_users").select("*", count="exact").eq("plan", "premium_yearly").execute()
        
        premium_users = (premium_monthly.count or 0) + (premium_yearly.count or 0)
        free_users = total_users - premium_users
        
        images_result = supabase.table("image_links").select("*", count="exact").execute()
        total_images = images_result.count or 0
        
        views_result = supabase.table("image_links").select("views_count").execute()
        total_views = sum(item.get('views_count', 0) or 0 for item in views_result.data)
        
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
            "premium_monthly": premium_monthly.count or 0,
            "premium_yearly": premium_yearly.count or 0,
            "total_images": total_images,
            "total_views": total_views,
            "today_images": today_images,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logging.error(f"Error get_stats: {e}")
        return {}

def get_all_users():
    try:
        users_result = supabase.table("image_users").select("*").order("created_at", desc=True).execute()
        users = users_result.data
        today = datetime.now().date().isoformat()
        user_list = []
        
        for user in users:
            telegram_id = user.get('telegram_id')
            today_count = supabase.table("image_links").select("*", count="exact").eq("user_telegram_id", telegram_id).gte("created_at", today).execute()
            total_count = supabase.table("image_links").select("*", count="exact").eq("user_telegram_id", telegram_id).execute()
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
        logging.error(f"Error get_all_users: {e}")
        return []

# =================================================================================
# مسارات عرض الصور (الوظيفة الأساسية)
# =================================================================================

@app.route('/')
def index():
    return jsonify({"status": "ok", "service": "image-link-server"})

@app.route('/health')
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route('/i/<image_id>')
def show_image(image_id):
    try:
        image = get_image_by_id(image_id)
        if not image:
            return "⚠️ الصورة غير موجودة", 404
        
        increment_views(image_id)
        
        original_url = image.get('original_url')
        if original_url:
            return redirect(original_url)
        
        return "⚠️ رابط الصورة غير صالح", 404
    except Exception as e:
        logging.error(f"Error show_image: {e}")
        return "⚠️ حدث خطأ", 500

# =================================================================================
# مسارات لوحة التحكم الإدارية
# =================================================================================

ADMIN_LOGIN_HTML = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - لوحة الإدارة</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            width: 90%;
            max-width: 400px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        h1 { color: #667eea; margin-bottom: 10px; text-align: center; }
        p { color: #6c757d; text-align: center; margin-bottom: 30px; }
        input {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
            margin-bottom: 20px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
        }
        .error { color: #dc3545; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>🔐 تسجيل الدخول</h1>
        <p>لوحة إدارة بوت تحويل الصور</p>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <input type="password" name="password" placeholder="كلمة المرور" required>
            <button type="submit">دخول</button>
        </form>
    </div>
</body>
</html>
'''

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            resp = make_response(redirect(url_for('admin_dashboard')))
            resp.set_cookie('admin_auth', password, max_age=86400)
            return resp
        return render_template_string(ADMIN_LOGIN_HTML, error="كلمة المرور غير صحيحة")
    return render_template_string(ADMIN_LOGIN_HTML)

@app.route('/admin/logout')
def admin_logout():
    resp = make_response(redirect(url_for('admin_login')))
    resp.set_cookie('admin_auth', '', expires=0)
    return resp

@app.route('/admin/dashboard')
def admin_dashboard():
    if not check_auth():
        return redirect(url_for('admin_login'))
    
    stats = get_stats()
    users = get_all_users()
    
    DASHBOARD_HTML = '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>لوحة الإدارة - بوت الصور</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background: #f5f7fa; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; padding: 25px; border-radius: 20px;
                margin-bottom: 25px; display: flex; justify-content: space-between;
                align-items: center; flex-wrap: wrap;
            }
            .stats-grid {
                display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px; margin-bottom: 25px;
            }
            .stat-card {
                background: white; border-radius: 16px; padding: 15px;
                text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }
            .stat-number { font-size: 1.8rem; font-weight: bold; color: #667eea; }
            .stat-label { color: #6c757d; font-size: 0.75rem; margin-top: 5px; }
            .users-section { background: white; border-radius: 20px; padding: 20px; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; font-size: 0.75rem; }
            th, td { padding: 10px 6px; text-align: center; border-bottom: 1px solid #e9ecef; }
            th { background: #f8f9fa; color: #495057; }
            .premium-badge { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 3px 8px; border-radius: 20px; font-size: 0.7rem; display: inline-block; }
            .free-badge { background: #e9ecef; color: #6c757d; padding: 3px 8px; border-radius: 20px; font-size: 0.7rem; }
            .upgrade-btn { background: #28a745; color: white; border: none; padding: 4px 8px; border-radius: 6px; cursor: pointer; }
            .downgrade-btn { background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 6px; cursor: pointer; }
            .search-box { display: flex; gap: 10px; margin-bottom: 20px; }
            .search-input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 12px; }
            .search-btn { background: #667eea; color: white; border: none; padding: 10px 18px; border-radius: 12px; cursor: pointer; }
            .refresh-btn { background: #48bb78; color: white; border: none; padding: 10px 18px; border-radius: 12px; cursor: pointer; }
            .header-btn { background: rgba(255,255,255,0.2); color: white; padding: 8px 16px; border-radius: 10px; text-decoration: none; }
            .footer { text-align: center; margin-top: 25px; padding: 20px; color: #6c757d; font-size: 0.7rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div><h1>🖼️ لوحة إدارة بوت الصور</h1><p>@ime_link_bot</p></div>
                <div><a href="/admin/logout" class="header-btn">🚪 خروج</a></div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-number">{{ stats.total_users }}</div><div class="stat-label">👥 المستخدمين</div></div>
                <div class="stat-card"><div class="stat-number">{{ stats.premium_users }}</div><div class="stat-label">👑 المميزين</div></div>
                <div class="stat-card"><div class="stat-number">{{ stats.free_users }}</div><div class="stat-label">🎁 المجانيين</div></div>
                <div class="stat-card"><div class="stat-number">{{ stats.total_images }}</div><div class="stat-label">🖼️ الصور</div></div>
                <div class="stat-card"><div class="stat-number">{{ stats.total_views }}</div><div class="stat-label">👁️ المشاهدات</div></div>
                <div class="stat-card"><div class="stat-number">{{ stats.today_images }}</div><div class="stat-label">📅 صور اليوم</div></div>
            </div>
            
            <div class="users-section">
                <div class="search-box">
                    <input type="text" id="searchInput" class="search-input" placeholder="🔍 بحث..." onkeyup="filterUsers()">
                    <button class="search-btn" onclick="filterUsers()">بحث</button>
                    <button class="refresh-btn" onclick="location.reload()">تحديث</button>
                </div>
                <table>
                    <thead><tr><th>المعرف</th><th>الاسم</th><th>الحالة</th><th>الخطة</th><th>الحد</th><th>اليوم</th><th>الإجمالي</th><th>الإجراءات</th></tr></thead>
                    <tbody>
                        {% for user in users %}
                        <tr data-name="{{ user.first_name }}" data-id="{{ user.user_id }}">
                            <td>{{ user.user_id }}</td>
                            <td>{{ user.first_name[:20] }}</td>
                            <td>{% if user.status == 'premium' %}<span class="premium-badge">مميز</span>{% else %}<span class="free-badge">مجاني</span>{% endif %}</td>
                            <td>{{ user.plan }}</td>
                            <td>{{ user.daily_limit }}</td>
                            <td>{{ user.today_count }}</td>
                            <td>{{ user.total_images }}</td>
                            <td>
                                {% if user.status == 'free' %}
                                <form method="POST" action="/admin/upgrade-user" style="display: inline;">
                                    <input type="hidden" name="user_id" value="{{ user.user_id }}">
                                    <select name="plan_name" style="padding: 2px 4px; font-size: 0.7rem;">
                                        <option value="premium_monthly">🌙 شهري</option>
                                        <option value="premium_yearly">🎉 سنوي</option>
                                    </select>
                                    <button type="submit" class="upgrade-btn">⭐ ترقية</button>
                                </form>
                                {% else %}
                                <form method="POST" action="/admin/downgrade-user" style="display: inline;">
                                    <input type="hidden" name="user_id" value="{{ user.user_id }}">
                                    <button type="submit" class="downgrade-btn">📉 خفض</button>
                                </form>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <div class="footer">@ime_link_bot | آخر تحديث: {{ stats.last_update }}</div>
        </div>
        <script>
            function filterUsers() {
                const term = document.getElementById('searchInput').value.toLowerCase();
                const rows = document.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const text = (row.getAttribute('data-name') || '') + (row.getAttribute('data-id') || '');
                    row.style.display = text.toLowerCase().includes(term) ? '' : 'none';
                });
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(DASHBOARD_HTML, stats=stats, users=users)

@app.route('/admin/upgrade-user', methods=['POST'])
def upgrade_user():
    if not check_auth():
        return redirect(url_for('admin_login'))
    try:
        user_id = request.form.get('user_id')
        plan_name = request.form.get('plan_name')
        plan = supabase.table("image_plans").select("*").eq("plan_name", plan_name).execute()
        if plan.data:
            daily_limit = plan.data[0].get('daily_limit', 100)
            supabase.table("image_users").update({"plan": plan_name, "daily_limit": daily_limit}).eq("telegram_id", user_id).execute()
    except Exception as e:
        logging.error(f"Error upgrade_user: {e}")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/downgrade-user', methods=['POST'])
def downgrade_user():
    if not check_auth():
        return redirect(url_for('admin_login'))
    try:
        user_id = request.form.get('user_id')
        free_plan = supabase.table("image_plans").select("*").eq("plan_name", "free").execute()
        daily_limit = free_plan.data[0].get('daily_limit', 5) if free_plan.data else 5
        supabase.table("image_users").update({"plan": "free", "daily_limit": daily_limit}).eq("telegram_id", user_id).execute()
    except Exception as e:
        logging.error(f"Error downgrade_user: {e}")
    return redirect(url_for('admin_dashboard'))

# =================================================================================
# تشغيل التطبيق
# =================================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)