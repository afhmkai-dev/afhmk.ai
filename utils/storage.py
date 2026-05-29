import os
from PIL import Image
from utils.db import supabase

# إعدادات الضغط
COMPRESS_QUALITY = 60
MAX_IMAGE_SIZE = (800, 800)

def compress_image(input_path, output_path, quality=COMPRESS_QUALITY, max_size=MAX_IMAGE_SIZE):
    """ضغط وتصغير الصورة"""
    try:
        with Image.open(input_path) as img:
            # تحويل إلى RGB
            if img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            
            # تصغير الأبعاد
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # حفظ الصورة
            img.save(output_path, "JPEG", optimize=True, quality=quality)
            return True
    except Exception as e:
        print(f"Error compressing image: {e}")
        return False

def upload_to_supabase(user_id: int, file_path: str, file_name: str = None) -> str:
    """رفع الصورة إلى Supabase Storage وإرجاع الرابط العام"""
    try:
        if not file_name:
            import secrets
            file_name = f"{secrets.token_hex(8)}.jpg"
        
        storage_path = f"{user_id}/{file_name}"
        
        with open(file_path, 'rb') as f:
            supabase.storage.from_("image-links").upload(
                path=storage_path,
                file=f,
                file_options={
                    "content-type": "image/jpeg",
                    "upsert": "true"
                }
            )
        
        public_url = supabase.storage.from_("image-links").get_public_url(storage_path)
        return public_url
        
    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

def delete_image(user_id: int, file_name: str):
    """حذف صورة من التخزين"""
    try:
        storage_path = f"{user_id}/{file_name}"
        supabase.storage.from_("image-links").remove([storage_path])
        return True
    except Exception as e:
        print(f"Error deleting image: {e}")
        return False