# -*- coding: utf-8 -*-
import os
from flask import Flask, redirect, send_from_directory
from utils.db import get_image_by_id, increment_views

app = Flask(__name__)

# إعدادات
PORT = int(os.environ.get('PORT', 10000))

# =================================================================================
# المسار الرئيسي
# =================================================================================

@app.route('/')
def home():
    return {
        "service": "Image Link Bot",
        "status": "running",
        "endpoints": ["/i/{image_id} - عرض الصورة"]
    }

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

# =================================================================================
# مسار الصور المختصرة
# =================================================================================

@app.route('/i/<image_id>')
def show_image(image_id):
    """عرض الصورة باستخدام المعرف المختصر"""
    try:
        # جلب بيانات الصورة
        image_data = get_image_by_id(image_id)
        
        if not image_data:
            return "⚠️ الصورة غير موجودة أو تم حذفها", 404
        
        # زيادة عدد المشاهدات
        increment_views(image_id)
        
        # إعادة توجيه إلى الرابط الأصلي
        original_url = image_data.get('original_url')
        if original_url:
            return redirect(original_url, 302)
        else:
            return "⚠️ رابط الصورة غير صالح", 404
            
    except Exception as e:
        print(f"Error: {e}")
        return "حدث خطأ في الخادم", 500

# =================================================================================
# تشغيل السيرفر
# =================================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🖼️ Image Link Server - خدمة الروابط المختصرة")
    print(f"🌐 Running on port: {PORT}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)