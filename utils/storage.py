import os
import secrets
from datetime import datetime
from PIL import Image

# =================================================================================
# إعدادات الضغط
# =================================================================================
COMPRESS_QUALITY = 60
MAX_IMAGE_SIZE = (800, 800)

# =================================================================================
# دوال الضغط والمعالجة
# =================================================================================

def compress_image(input_path, output_path, quality=COMPRESS_QUALITY, max_size=MAX_IMAGE_SIZE):
    """ضغط وتصغير الصورة"""
    try:
        with Image.open(input_path) as img:
            # تحويل إلى RGB (إزالة الشفافية)
            if img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            
            # تصغير الأبعاد إذا كانت أكبر من الحد
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # حفظ الصورة المضغوطة
            img.save(output_path, "JPEG", optimize=True, quality=quality)
            return True
    except Exception as e:
        print(f"Error compressing image: {e}")
        return False

def generate_image_id() -> str:
    """إنشاء معرف فريد للصورة"""
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10]

# =================================================================================
# دوال رفع الصور
# =================================================================================

def upload_to_supabase(supabase_client, user_id: int, file_path: str, image_id: str = None) -> dict:
    """
    رفع الصورة إلى Supabase Storage وإرجاع البيانات المطلوبة
    
    Returns:
        dict: {
            'image_id': str,
            'original_url': str,
            'file_size': int,
            'storage_path': str
        }
    """
    try:
        # إنشاء معرف فريد إذا لم يتم توفيره
        if not image_id:
            image_id = generate_image_id()
        
        # مسار التخزين (user_id/image_id.jpg)
        storage_path = f"{user_id}/{image_id}.jpg"
        
        # رفع الملف
        with open(file_path, 'rb') as f:
            supabase_client.storage.from_("image-links").upload(
                path=storage_path,
                file=f,
                file_options={
                    "content-type": "image/jpeg",
                    "upsert": "true"
                }
            )
        
        # بناء الرابط الأصلي (طريقة يدوية مضمونة)
        supabase_url = os.environ.get('SUPABASE_URL')
        bucket_name = "image-links"
        original_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{storage_path}"
        
        # حجم الملف بالكيلوبايت
        file_size = os.path.getsize(file_path) // 1024
        
        return {
            'image_id': image_id,
            'original_url': original_url,
            'file_size': file_size,
            'storage_path': storage_path
        }
        
    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

def delete_image(supabase_client, user_id: int, image_id: str):
    """حذف صورة من التخزين"""
    try:
        storage_path = f"{user_id}/{image_id}.jpg"
        supabase_client.storage.from_("image-links").remove([storage_path])
        return True
    except Exception as e:
        print(f"Error deleting image: {e}")
        return False

def get_public_url(supabase_client, user_id: int, image_id: str) -> str:
    """الحصول على الرابط العام لصورة"""
    try:
        storage_path = f"{user_id}/{image_id}.jpg"
        return supabase_client.storage.from_("image-links").get_public_url(storage_path)
    except Exception as e:
        print(f"Error getting public URL: {e}")
        return None