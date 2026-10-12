import os
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ImageEnhance

class WatermarkEngine:
    """
    High-precision watermark compositing engine.
    Supports full-width bottom banners, original overlays, and custom positioning
    with alpha preservation, opacity control, and edge margins.
    """

    @staticmethod
    def load_watermark_image(path: str) -> Optional[Image.Image]:
        if not path or not os.path.exists(path):
            return None
        try:
            img = Image.open(path)
            return img.convert("RGBA")
        except Exception as e:
            print(f"[WatermarkEngine] Error loading {path}: {e}")
            return None

    @classmethod
    def get_watermark_for_photo(
        cls,
        orientation: str,
        vert_path: str,
        horiz_path: str,
        square_policy: str = "portrait"
    ) -> Tuple[Optional[Image.Image], str]:
        """
        Selects the appropriate watermark asset based on orientation.
        Note: The asset named 'water mark landscape.png' has 900x1600 (vertical) canvas,
        and 'water mark portrait.png' has 1600x900 (horizontal) canvas.
        """
        chosen_path = ""
        if orientation == "portrait":
            chosen_path = vert_path
        elif orientation == "landscape":
            chosen_path = horiz_path
        else:  # square
            chosen_path = vert_path if square_policy == "portrait" else horiz_path

        wm_img = cls.load_watermark_image(chosen_path)
        return wm_img, chosen_path

    @classmethod
    def apply_watermark(
        cls,
        base_img: Image.Image,
        watermark_img: Image.Image,
        config: Dict[str, Any]
    ) -> Image.Image:
        """
        Composites watermark_img onto base_img according to config rules.
        Preserves base_img dimensions and aspect ratio.
        """
        if not watermark_img:
            return base_img.copy()

        # Ensure base image is in RGBA mode for compositing
        base_rgba = base_img.convert("RGBA")
        bw, bh = base_rgba.size

        wm = watermark_img.copy()

        # 1. Opacity Adjustment
        opacity = float(config.get("opacity", 1.0))
        opacity = max(0.0, min(1.0, opacity))
        if opacity < 1.0:
            r, g, b, a = wm.split()
            a = a.point(lambda p: int(p * opacity))
            wm = Image.merge("RGBA", (r, g, b, a))

        placement_mode = config.get("placement_mode", "full_width_banner")

        # 2. Placement Calculations
        if placement_mode == "full_width_banner":
            # Extract non-transparent banner or use full canvas if no alpha
            alpha = wm.getchannel("A")
            bbox = alpha.getbbox()
            banner = wm.crop(bbox) if bbox else wm

            banner_w, banner_h = banner.size
            scale = bw / banner_w
            target_h = max(1, round(banner_h * scale))

            # Prevent banner from exceeding image height
            if target_h > bh:
                scale = bh / banner_h
                target_w = max(1, round(banner_w * scale))
                target_h = bh
                resized_banner = banner.resize((target_w, target_h), Image.Resampling.LANCZOS)
                pos_x = (bw - target_w) // 2
                pos_y = bh - target_h
            else:
                target_w = bw
                resized_banner = banner.resize((target_w, target_h), Image.Resampling.LANCZOS)
                pos_x = 0
                pos_y = bh - target_h

            overlay_canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            overlay_canvas.paste(resized_banner, (pos_x, pos_y), resized_banner)
            return Image.alpha_composite(base_rgba, overlay_canvas)

        elif placement_mode == "original_overlay":
            # Fit watermark proportionally within image bounds
            wm_w, wm_h = wm.size
            scale = min(bw / wm_w, bh / wm_h)
            new_w = max(1, round(wm_w * scale))
            new_h = max(1, round(wm_h * scale))
            resized_wm = wm.resize((new_w, new_h), Image.Resampling.LANCZOS)

            pos_x = (bw - new_w) // 2
            pos_y = bh - new_h  # align to bottom

            overlay_canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            overlay_canvas.paste(resized_wm, (pos_x, pos_y), resized_wm)
            return Image.alpha_composite(base_rgba, overlay_canvas)

        else:  # 'custom' scale & position
            crop_padding = bool(config.get("crop_padding", False))
            if crop_padding:
                alpha = wm.getchannel("A")
                bbox = alpha.getbbox()
                if bbox:
                    wm = wm.crop(bbox)

            wm_w, wm_h = wm.size
            custom_scale = float(config.get("custom_scale", 0.3))
            custom_scale = max(0.05, min(2.0, custom_scale))

            # Scale proportional to smaller dimension of base image
            ref_dim = min(bw, bh)
            target_w = max(1, round(ref_dim * custom_scale))
            aspect = wm_h / wm_w
            target_h = max(1, round(target_w * aspect))

            resized_wm = wm.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # Margins
            margin_pct = float(config.get("margin_percent", 0.02))
            margin_x = round(bw * margin_pct)
            margin_y = round(bh * margin_pct)

            h_align = config.get("horizontal_align", "right")
            v_align = config.get("vertical_align", "bottom")

            if h_align == "left":
                pos_x = margin_x
            elif h_align == "center":
                pos_x = (bw - target_w) // 2
            else:  # right
                pos_x = bw - target_w - margin_x

            if v_align == "top":
                pos_y = margin_y
            elif v_align == "center":
                pos_y = (bh - target_h) // 2
            else:  # bottom
                pos_y = bh - target_h - margin_y

            # Clamp coordinates inside canvas
            pos_x = max(0, min(bw - target_w, pos_x))
            pos_y = max(0, min(bh - target_h, pos_y))

            overlay_canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            overlay_canvas.paste(resized_wm, (pos_x, pos_y), resized_wm)
            return Image.alpha_composite(base_rgba, overlay_canvas)
