# -*- coding: utf-8 -*-
import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, redirect, url_for, make_response
from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({"status": "ok", "service": "image-link-server"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/i/<image_id>')
def show_image(image_id):
    try:
        result = supabase.table("image_links").select("*").eq("image_id", image_id).execute()
        if result.data:
            image = result.data[0]
            views = image.get('views_count', 0) + 1
            supabase.table("image_links").update({"views_count": views}).eq("image_id", image_id).execute()
            return redirect(image.get('original_url', '/'))
        return "⚠️ الصورة غير موجودة", 404
    except Exception as e:
        return f"⚠️ خطأ: {e}", 500

# قالب تسجيل الدخول
LOGIN_HTML = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تسجيل الدخول</title>
    <style>
        body {
            font-family: Arial;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0;
        }
        .login-card {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 350px;
            text-align: center;
        }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 1px solid #ddd;
            border-radius: 10px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
        }
        .error { color: red; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h1>🔐 تسجيل الدخول</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
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
        if request.form.get('password') == ADMIN_PASSWORD:
            resp = make_response(redirect(url_for('admin_dashboard')))
            resp.set_cookie('admin_auth', ADMIN_PASSWORD, max_age=86400)
            return resp
        return render_template_string(LOGIN_HTML, error="كلمة المرور غير صحيحة")
    return render_template_string(LOGIN_HTML)

def check_auth():
    return request.cookies.get('admin_auth') == ADMIN_PASSWORD

@app.route('/admin/dashboard')
def admin_dashboard():
    if not check_auth():
        return redirect(url_for('admin_login'))
    
    # جلب البيانات
    users = supabase.table("image_users").select("*").execute()
    stats = supabase.table("image_links").select("*", count="exact").execute()
    
    DASHBOARD_HTML = '''
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>لوحة الإدارة</title>
        <style>
            body { font-family: Arial; background: #f5f7fa; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: #667eea; color: white; padding: 20px; border-radius: 20px; margin-bottom: 20px; display: flex; justify-content: space-between; }
            .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 15px; margin-bottom: 20px; }
            .stat-card { background: white; padding: 15px; border-radius: 16px; text-align: center; }
            .stat-number { font-size: 28px; font-weight: bold; color: #667eea; }
            table { width: 100%; background: white; border-radius: 16px; overflow: hidden; }
            th, td { padding: 10px; text-align: center; border-bottom: 1px solid #ddd; }
            .premium-badge { background: #28a745; color: white; padding: 4px 8px; border-radius: 20px; }
            .free-badge { background: #6c757d; color: white; padding: 4px 8px; border-radius: 20px; }
            .upgrade-btn { background: #28a745; color: white; border: none; padding: 4px 8px; border-radius: 6px; cursor: pointer; }
            .downgrade-btn { background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 6px; cursor: pointer; }
            .logout { background: rgba(255,255,255,0.2); color: white; padding: 8px 16px; border-radius: 10px; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🖼️ لوحة إدارة بوت الصور</h1>
                <a href="/admin/logout" class="logout">🚪 خروج</a>
            </div>
            <div class="stats">
                <div class="stat-card"><div class="stat-number">{{ users_count }}</div><div>👥 المستخدمين</div></div>
                <div class="stat-card"><div class="stat-number">{{ images_count }}</div><div>🖼️ الصور</div></div>
            </div>
            <h2>📋 المستخدمين</h2>
            <table>
                <thead><tr><th>المعرف</th><th>الاسم</th><th>اليوزرنيم</th><th>الخطة</th><th>الحد</th><th>الإجراءات</th></tr></thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td>{{ user.telegram_id }}</td>
                        <td>{{ user.first_name }}</td>
                        <td>@{{ user.username }}</td>
                        <td>{% if user.plan != 'free' %}<span class="premium-badge">مميز</span>{% else %}<span class="free-badge">مجاني</span>{% endif %}</td>
                        <td>{{ user.daily_limit }}</td>
                        <td>
                            {% if user.plan == 'free' %}
                            <form method="POST" action="/admin/upgrade-user" style="display:inline">
                                <input type="hidden" name="user_id" value="{{ user.telegram_id }}">
                                <select name="plan_name">
                                    <option value="premium_monthly">🌙 شهري</option>
                                    <option value="premium_yearly">🎉 سنوي</option>
                                </select>
                                <button type="submit" class="upgrade-btn">⭐ ترقية</button>
                            </form>
                            {% else %}
                            <form method="POST" action="/admin/downgrade-user" style="display:inline">
                                <input type="hidden" name="user_id" value="{{ user.telegram_id }}">
                                <button type="submit" class="downgrade-btn">📉 خفض</button>
                            </form>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    
    return render_template_string(DASHBOARD_HTML, 
                                  users=users.data,
                                  users_count=len(users.data),
                                  images_count=stats.count or 0)

@app.route('/admin/upgrade-user', methods=['POST'])
def upgrade_user():
    if not check_auth():
        return redirect(url_for('admin_login'))
    user_id = request.form.get('user_id')
    plan_name = request.form.get('plan_name')
    supabase.table("image_users").update({"plan": plan_name, "daily_limit": 100}).eq("telegram_id", user_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/downgrade-user', methods=['POST'])
def downgrade_user():
    if not check_auth():
        return redirect(url_for('admin_login'))
    user_id = request.form.get('user_id')
    supabase.table("image_users").update({"plan": "free", "daily_limit": 5}).eq("telegram_id", user_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    resp = make_response(redirect(url_for('admin_login')))
    resp.set_cookie('admin_auth', '', expires=0)
    return resp

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)