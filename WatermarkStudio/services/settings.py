import os
import json
from typing import Dict, Any

DEFAULT_CONFIG_FILENAME = "config.json"

class SettingsManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config_path = os.path.join(config_dir, DEFAULT_CONFIG_FILENAME)
        self.parent_dir = os.path.dirname(config_dir)

    def get_default_settings(self) -> Dict[str, Any]:
        gallery_default = os.path.join(self.parent_dir, "Gallery")
        wm_vert_default = os.path.join(self.parent_dir, "Water mark", "water mark landscape.png")
        wm_horiz_default = os.path.join(self.parent_dir, "Water mark", "water mark portrait.png")
        output_default = os.path.join(self.parent_dir, "Watermarked Gallery")

        return {
            "input_dir": gallery_default if os.path.exists(gallery_default) else self.parent_dir,
            "wm_vert_path": wm_vert_default if os.path.exists(wm_vert_default) else "",
            "wm_horiz_path": wm_horiz_default if os.path.exists(wm_horiz_default) else "",
            "output_dir": output_default,
            
            # Renaming settings
            "naming_prefix": "GGM_RECAS_KCC_P4_",
            "start_index": 1,
            "pad_digits": 2,
            "numbering_mode": "sequential_all",  # 'sequential_all' or 'separate_by_folder'
            "naming_order": "portrait_first",    # 'portrait_first' or 'alphabetical'
            "include_orientation_suffix": False,
            "preserve_original_name": False,

            # Placement & Watermark settings
            "placement_mode": "full_width_banner",  # 'full_width_banner', 'original_overlay', 'custom'
            "opacity": 1.0,                         # 0.0 to 1.0
            "horizontal_align": "center",           # 'left', 'center', 'right'
            "vertical_align": "bottom",             # 'top', 'center', 'bottom'
            "custom_scale": 1.0,                    # 0.05 to 1.5
            "margin_percent": 0.0,                  # edge margin
            "crop_padding": False,                  # whether to strip transparent padding by default

            # Export settings
            "export_format": "JPEG",                # 'JPEG', 'PNG', 'WEBP'
            "jpeg_quality": 95,                     # 1 to 100
            "background_color": "#FFFFFF",          # for RGBA to RGB flattening
            "output_structure": "folders",          # 'single', 'folders' (Portrait/Landscape), 'folders_with_square'
            "square_policy": "portrait",            # 'portrait', 'landscape', 'square'
            "max_dimension": 0,                     # 0 = keep original, or positive int (e.g. 1920)
            "preserve_metadata": False,
            "overwrite_existing": False
        }

    def load_settings(self) -> Dict[str, Any]:
        defaults = self.get_default_settings()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        defaults.update(data)
            except Exception as e:
                print(f"[SettingsManager] Error loading config: {e}")
        return defaults

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        try:
            current = self.load_settings()
            current.update(settings)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
            return True
        except Exception as e:
            print(f"[SettingsManager] Error saving config: {e}")
            return False

    @staticmethod
    def get_presets() -> Dict[str, Dict[str, Any]]:
        return {
            "full_width_banner": {
                "name": "Full-Width Bottom Banner (Default)",
                "placement_mode": "full_width_banner",
                "vertical_align": "bottom",
                "horizontal_align": "center",
                "opacity": 1.0,
                "crop_padding": False
            },
            "corner_watermark": {
                "name": "Bottom-Right Corner Logo",
                "placement_mode": "custom",
                "custom_scale": 0.25,
                "vertical_align": "bottom",
                "horizontal_align": "right",
                "margin_percent": 0.02,
                "opacity": 0.9,
                "crop_padding": True
            },
            "centered": {
                "name": "Centered Watermark",
                "placement_mode": "custom",
                "custom_scale": 0.5,
                "vertical_align": "center",
                "horizontal_align": "center",
                "margin_percent": 0.0,
                "opacity": 0.8,
                "crop_padding": True
            }
        }
