import os
import re
import shutil
from typing import List, Dict, Any, Tuple, Optional

INVALID_WIN_CHARS = r'[<>:"/\\|?*\x00-\x1f]'

class FileManager:
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

    @staticmethod
    def sanitize_filename_part(part: str, fallback: str = "item") -> str:
        """Sanitizes a string to be a safe Windows filename component."""
        cleaned = re.sub(INVALID_WIN_CHARS, "_", part).strip(". ")
        return cleaned if cleaned else fallback

    @staticmethod
    def is_safe_path(base_dir: str, target_path: str) -> bool:
        """Verifies target_path does not escape base_dir."""
        try:
            base_abs = os.path.abspath(base_dir)
            target_abs = os.path.abspath(target_path)
            common = os.path.commonpath([base_abs, target_abs])
            return common == base_abs
        except Exception:
            return False

    @classmethod
    def scan_directory(cls, input_dir: str, output_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scans input_dir recursively for supported image files.
        Safely excludes output_dir to prevent recursive re-import.
        """
        if not input_dir or not os.path.isdir(input_dir):
            return []

        input_abs = os.path.abspath(input_dir)
        output_abs = os.path.abspath(output_dir) if output_dir and os.path.isdir(output_dir) else None

        found_files = []
        for root, dirs, files in os.walk(input_abs):
            # Skip output folder if nested inside input folder
            if output_abs:
                dirs[:] = [
                    d for d in dirs 
                    if os.path.abspath(os.path.join(root, d)) != output_abs
                    and not os.path.abspath(os.path.join(root, d)).startswith(output_abs + os.sep)
                ]

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in cls.SUPPORTED_EXTENSIONS:
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, input_abs)
                    try:
                        size_bytes = os.path.getsize(abs_path)
                    except Exception:
                        size_bytes = 0

                    found_files.append({
                        "name": f,
                        "rel_path": rel_path,
                        "abs_path": abs_path,
                        "size_bytes": size_bytes,
                        "size_kb": round(size_bytes / 1024, 1),
                        "ext": ext
                    })

        # Natural deterministic sort by relative path
        found_files.sort(key=lambda x: x["rel_path"].lower())
        return found_files

    @classmethod
    def generate_planned_filenames(
        cls,
        images: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Calculates output filenames and destinations for a list of images deterministically.
        Detects and resolves potential filename collisions.
        """
        prefix = cls.sanitize_filename_part(config.get("naming_prefix", "GGM_RECAS_KCC_P4_"))
        start_idx = max(1, int(config.get("start_index", 1)))
        pad_digits = max(1, min(8, int(config.get("pad_digits", 2))))
        numbering_mode = config.get("numbering_mode", "sequential_all")
        naming_order = config.get("naming_order", "portrait_first")
        output_dir = os.path.abspath(config.get("output_dir", ""))
        output_structure = config.get("output_structure", "folders")
        export_format = config.get("export_format", "JPEG").upper()
        target_ext = ".jpg" if export_format == "JPEG" else f".{export_format.lower()}"
        include_suffix = config.get("include_orientation_suffix", False)
        preserve_orig = config.get("preserve_original_name", False)

        # Segregate by orientation
        portraits = [img for img in images if img.get("orientation") == "portrait"]
        landscapes = [img for img in images if img.get("orientation") == "landscape"]
        squares = [img for img in images if img.get("orientation") == "square"]

        ordered_groups: List[Tuple[str, List[Dict[str, Any]]]] = []
        if naming_order == "portrait_first":
            ordered_groups = [("portrait", portraits), ("landscape", landscapes), ("square", squares)]
        else:
            # alphabetical by original filename
            all_sorted = sorted(images, key=lambda x: x["name"].lower())
            ordered_groups = [("mixed", all_sorted)]

        planned_items: List[Dict[str, Any]] = []
        global_index = start_idx

        # Helper to determine target subfolder
        def get_target_folder(orientation: str) -> str:
            if output_structure == "folders":
                sub = "Portrait" if orientation == "portrait" else ("Landscape" if orientation == "landscape" else "Square")
                return os.path.join(output_dir, sub)
            elif output_structure == "folders_with_square":
                sub = orientation.capitalize()
                return os.path.join(output_dir, sub)
            return output_dir

        for orient_name, group_imgs in ordered_groups:
            group_index = start_idx
            for img in group_imgs:
                img_orient = img.get("orientation", "landscape")
                target_folder = get_target_folder(img_orient)
                
                curr_num = global_index if numbering_mode == "sequential_all" else group_index
                idx_str = str(curr_num).zfill(pad_digits)
                
                parts = [f"{prefix}{idx_str}"]
                if include_suffix:
                    suf = "P" if img_orient == "portrait" else ("L" if img_orient == "landscape" else "S")
                    parts.append(suf)
                if preserve_orig:
                    orig_stem = os.path.splitext(img["name"])[0]
                    parts.append(cls.sanitize_filename_part(orig_stem))

                filename_base = "_".join(parts)
                final_filename = f"{filename_base}{target_ext}"
                final_path = os.path.join(target_folder, final_filename)

                planned_items.append({
                    **img,
                    "target_folder": target_folder,
                    "target_filename": final_filename,
                    "target_path": final_path,
                    "index_num": curr_num
                })

                global_index += 1
                group_index += 1

        # Collision resolution check
        used_paths: Dict[str, int] = {}
        for item in planned_items:
            path_key = item["target_path"].lower()
            if path_key in used_paths:
                used_paths[path_key] += 1
                stem, ext = os.path.splitext(item["target_filename"])
                dedup_filename = f"{stem}_{used_paths[path_key]}{ext}"
                item["target_filename"] = dedup_filename
                item["target_path"] = os.path.join(item["target_folder"], dedup_filename)
            else:
                used_paths[path_key] = 1

        return planned_items

    @staticmethod
    def atomic_replace_save(tmp_path: str, final_path: str) -> None:
        """Atomically moves temporary output file to final path."""
        target_dir = os.path.dirname(final_path)
        os.makedirs(target_dir, exist_ok=True)
        if os.path.exists(final_path):
            os.remove(final_path)
        shutil.move(tmp_path, final_path)
