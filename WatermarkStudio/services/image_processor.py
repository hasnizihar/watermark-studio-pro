import os
import io
import base64
import hashlib
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageOps, ImageColor

class ImageProcessor:
    """
    Handles image decoding, EXIF orientation normalization, orientation classification,
    format conversion, background flattening, and thumbnail caching.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), "..", ".cache_thumbs")
        os.makedirs(self.cache_dir, exist_ok=True)

    @staticmethod
    def inspect_image(filepath: str, square_policy: str = "portrait") -> Dict[str, Any]:
        """
        Opens image, applies EXIF transpose, and extracts orientation and dimensions.
        """
        try:
            with Image.open(filepath) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                w, h = img.size

                if w > h:
                    orientation = "landscape"
                elif h > w:
                    orientation = "portrait"
                else:
                    orientation = "square"

                size_bytes = os.path.getsize(filepath)
                return {
                    "valid": True,
                    "width": w,
                    "height": h,
                    "raw_width": raw_img.size[0],
                    "raw_height": raw_img.size[1],
                    "orientation": orientation,
                    "aspect_ratio": round(w / h, 3),
                    "size_bytes": size_bytes,
                    "size_kb": round(size_bytes / 1024, 1),
                    "format": raw_img.format or "JPEG"
                }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "width": 0,
                "height": 0,
                "orientation": "unknown"
            }

    @staticmethod
    def load_normalized_image(filepath: str) -> Optional[Image.Image]:
        """
        Loads image and applies EXIF orientation normalization.
        """
        try:
            with Image.open(filepath) as raw_img:
                img = ImageOps.exif_transpose(raw_img)
                return img.copy()
        except Exception as e:
            print(f"[ImageProcessor] Error loading {filepath}: {e}")
            return None

    def get_or_create_thumbnail(self, filepath: str, max_size: int = 260) -> Optional[str]:
        """
        Generates and caches a small JPEG thumbnail on disk. Returns path to thumbnail.
        """
        try:
            stat = os.stat(filepath)
            cache_key = hashlib.md5(f"{filepath}_{stat.st_mtime}_{max_size}".encode()).hexdigest()
            cache_path = os.path.join(self.cache_dir, f"{cache_key}.jpg")

            if os.path.exists(cache_path):
                return cache_path

            img = self.load_normalized_image(filepath)
            if not img:
                return None

            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            rgb_thumb = self.flatten_to_rgb(img, background_color="#181b22")
            rgb_thumb.save(cache_path, format="JPEG", quality=80)
            return cache_path
        except Exception as e:
            print(f"[ImageProcessor] Thumbnail error {filepath}: {e}")
            return None

    @staticmethod
    def flatten_to_rgb(img: Image.Image, background_color: str = "#FFFFFF") -> Image.Image:
        """
        Flattens RGBA/P image onto background color without dark fringes.
        """
        if img.mode in ("RGB", "L"):
            return img.convert("RGB")

        rgba = img.convert("RGBA")
        try:
            bg_color = ImageColor.getrgb(background_color)
        except Exception:
            bg_color = (255, 255, 255)

        bg = Image.new("RGBA", rgba.size, bg_color + (255,))
        composite = Image.alpha_composite(bg, rgba)
        return composite.convert("RGB")

    @classmethod
    def export_image(
        cls,
        img: Image.Image,
        dest_path: str,
        config: Dict[str, Any]
    ) -> bool:
        """
        Exports composited image to dest_path with format conversion, quality, and optional resizing.
        Ensures EXIF rotation is not duplicated.
        """
        export_format = config.get("export_format", "JPEG").upper()
        quality = int(config.get("jpeg_quality", 95))
        bg_color = config.get("background_color", "#FFFFFF")
        max_dim = int(config.get("max_dimension", 0))

        processed = img.copy()

        # Optional maximum dimension downscale
        if max_dim > 0 and (processed.width > max_dim or processed.height > max_dim):
            processed.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        tmp_path = dest_path + ".tmp"

        try:
            if export_format in ("JPEG", "JPG"):
                rgb_img = cls.flatten_to_rgb(processed, background_color=bg_color)
                # Save without copying old EXIF orientation to avoid double rotation
                rgb_img.save(
                    tmp_path,
                    format="JPEG",
                    quality=quality,
                    subsampling=0,
                    optimize=True
                )
            elif export_format == "PNG":
                processed.convert("RGBA").save(tmp_path, format="PNG", optimize=True)
            elif export_format == "WEBP":
                processed.convert("RGBA").save(tmp_path, format="WEBP", quality=quality)
            else:
                rgb_img = cls.flatten_to_rgb(processed, background_color=bg_color)
                rgb_img.save(tmp_path, format="JPEG", quality=quality)

            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.replace(tmp_path, dest_path)
            return True
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise e
