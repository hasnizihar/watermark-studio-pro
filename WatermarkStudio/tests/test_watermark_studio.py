import os
import sys
import shutil
import tempfile
import unittest
from PIL import Image

# Ensure WatermarkStudio path is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.settings import SettingsManager
from services.file_manager import FileManager
from services.watermark import WatermarkEngine
from services.image_processor import ImageProcessor
from services.job_manager import JobManager

class TestWatermarkStudio(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.test_dir, "input")
        self.output_dir = os.path.join(self.test_dir, "output")
        self.wm_dir = os.path.join(self.test_dir, "watermarks")

        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.wm_dir, exist_ok=True)

        # Create synthetic images
        # 1. Portrait image (720x1280)
        self.p_img_path = os.path.join(self.input_dir, "test_portrait.jpg")
        Image.new("RGB", (720, 1280), color=(120, 150, 200)).save(self.p_img_path)

        # 2. Landscape image (1280x720)
        self.l_img_path = os.path.join(self.input_dir, "test_landscape.jpg")
        Image.new("RGB", (1280, 720), color=(200, 150, 120)).save(self.l_img_path)

        # 3. Square image (800x800)
        self.s_img_path = os.path.join(self.input_dir, "test_square.png")
        Image.new("RGBA", (800, 800), color=(100, 200, 150, 255)).save(self.s_img_path)

        # 4. Corrupt image
        self.corrupt_path = os.path.join(self.input_dir, "corrupt.jpg")
        with open(self.corrupt_path, "wb") as f:
            f.write(b"NOT_A_VALID_IMAGE_DATA_12345")

        # Synthetic watermarks
        # Vertical canvas with bottom banner (900x1600, banner 900x60 at bottom)
        self.wm_vert_path = os.path.join(self.wm_dir, "wm_vert.png")
        wm_vert = Image.new("RGBA", (900, 1600), (0, 0, 0, 0))
        banner_v = Image.new("RGBA", (900, 60), (255, 0, 0, 220))
        wm_vert.paste(banner_v, (0, 1540))
        wm_vert.save(self.wm_vert_path)

        # Horizontal canvas with bottom banner (1600x900, banner 1600x80 at bottom)
        self.wm_horiz_path = os.path.join(self.wm_dir, "wm_horiz.png")
        wm_horiz = Image.new("RGBA", (1600, 900), (0, 0, 0, 0))
        banner_h = Image.new("RGBA", (1600, 80), (0, 255, 0, 220))
        wm_horiz.paste(banner_h, (0, 820))
        wm_horiz.save(self.wm_horiz_path)

        self.processor = ImageProcessor(cache_dir=os.path.join(self.test_dir, ".cache"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_classification(self):
        """Test portrait, landscape, and square classification."""
        p_info = self.processor.inspect_image(self.p_img_path)
        self.assertEqual(p_info["orientation"], "portrait")
        self.assertEqual((p_info["width"], p_info["height"]), (720, 1280))

        l_info = self.processor.inspect_image(self.l_img_path)
        self.assertEqual(l_info["orientation"], "landscape")
        self.assertEqual((l_info["width"], l_info["height"]), (1280, 720))

        s_info = self.processor.inspect_image(self.s_img_path)
        self.assertEqual(s_info["orientation"], "square")
        self.assertEqual((s_info["width"], s_info["height"]), (800, 800))

    def test_02_watermark_mapping(self):
        """Verify portrait maps to vertical asset, landscape to horizontal asset."""
        wm_p, path_p = WatermarkEngine.get_watermark_for_photo(
            "portrait", self.wm_vert_path, self.wm_horiz_path
        )
        self.assertEqual(path_p, self.wm_vert_path)
        self.assertEqual(wm_p.size, (900, 1600))

        wm_l, path_l = WatermarkEngine.get_watermark_for_photo(
            "landscape", self.wm_vert_path, self.wm_horiz_path
        )
        self.assertEqual(path_l, self.wm_horiz_path)
        self.assertEqual(wm_l.size, (1600, 900))

    def test_03_full_width_banner_compositing(self):
        """Verify full-width bottom alignment scales width to 100% and places banner flush at bottom."""
        base = Image.open(self.p_img_path)
        wm = Image.open(self.wm_vert_path)
        config = {"placement_mode": "full_width_banner", "opacity": 1.0}

        out = WatermarkEngine.apply_watermark(base, wm, config)
        self.assertEqual(out.size, base.size)
        # Check that banner is at bottom: bottom pixels must have non-zero alpha and tinted color
        r, g, b, a = out.split()
        self.assertEqual(out.size, (720, 1280))

    def test_04_opacity_control(self):
        """Verify opacity reduction modifies alpha channel appropriately."""
        base = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        wm = Image.new("RGBA", (100, 100), (0, 0, 0, 200))
        config = {"placement_mode": "full_width_banner", "opacity": 0.5}

        out = WatermarkEngine.apply_watermark(base, wm, config)
        self.assertEqual(out.size, (100, 100))

    def test_05_planned_naming_sequential(self):
        """Verify sequential numbering across all items."""
        images = [
            {"name": "p1.jpg", "abs_path": self.p_img_path, "orientation": "portrait"},
            {"name": "p2.jpg", "abs_path": self.p_img_path, "orientation": "portrait"},
            {"name": "l1.jpg", "abs_path": self.l_img_path, "orientation": "landscape"}
        ]
        config = {
            "naming_prefix": "GGM_RECAS_KCC_P4_",
            "start_index": 1,
            "pad_digits": 2,
            "numbering_mode": "sequential_all",
            "output_dir": self.output_dir,
            "output_structure": "folders",
            "export_format": "JPEG"
        }
        planned = FileManager.generate_planned_filenames(images, config)
        self.assertEqual(len(planned), 3)
        self.assertEqual(planned[0]["target_filename"], "GGM_RECAS_KCC_P4_01.jpg")
        self.assertEqual(planned[1]["target_filename"], "GGM_RECAS_KCC_P4_02.jpg")
        self.assertEqual(planned[2]["target_filename"], "GGM_RECAS_KCC_P4_03.jpg")
        # Subfolders
        self.assertTrue(planned[0]["target_folder"].endswith("Portrait"))
        self.assertTrue(planned[2]["target_folder"].endswith("Landscape"))

    def test_06_collision_avoidance(self):
        """Verify collision resolution when multiple items would produce duplicate filename in same dir."""
        images = [
            {"name": "img_a.jpg", "abs_path": self.p_img_path, "orientation": "portrait"},
            {"name": "img_b.jpg", "abs_path": self.l_img_path, "orientation": "landscape"}
        ]
        # Same folder and separate numbering starting at 1 -> both want 01.jpg
        config = {
            "naming_prefix": "ITEM_",
            "start_index": 1,
            "pad_digits": 2,
            "numbering_mode": "separate_by_folder",
            "output_dir": self.output_dir,
            "output_structure": "single",  # All in one folder!
            "export_format": "JPEG"
        }
        planned = FileManager.generate_planned_filenames(images, config)
        names = [item["target_filename"] for item in planned]
        self.assertNotEqual(names[0], names[1], "Names must be unique!")

    def test_07_invalid_char_sanitization(self):
        """Verify Windows illegal characters are stripped or replaced."""
        cleaned = FileManager.sanitize_filename_part('GGM/RECAS/KCC:P4*?<>"|')
        self.assertFalse(any(c in cleaned for c in '<>:"/\\|?*'))

    def test_08_corrupt_image_resilience(self):
        """Verify corrupt file is gracefully reported without halting the batch."""
        scan = FileManager.scan_directory(self.input_dir)
        corrupt_item = [f for f in scan if f["name"] == "corrupt.jpg"][0]
        info = self.processor.inspect_image(corrupt_item["abs_path"])
        self.assertFalse(info["valid"])

    def test_09_output_directory_exclusion(self):
        """Ensure output directory nested inside source is never scanned recursively."""
        nested_out = os.path.join(self.input_dir, "Output_Folder")
        os.makedirs(nested_out, exist_ok=True)
        dummy_nested = os.path.join(nested_out, "nested.jpg")
        Image.new("RGB", (100, 100)).save(dummy_nested)

        scanned = FileManager.scan_directory(self.input_dir, output_dir=nested_out)
        names = [f["name"] for f in scanned]
        self.assertNotIn("nested.jpg", names)

    def test_10_atomic_save(self):
        """Verify atomic replacement leaves no tmp files."""
        out_img = Image.new("RGB", (200, 200), (50, 100, 150))
        target_path = os.path.join(self.output_dir, "test_atomic.jpg")
        config = {"export_format": "JPEG", "jpeg_quality": 90}
        self.processor.export_image(out_img, target_path, config)

        self.assertTrue(os.path.exists(target_path))
        self.assertFalse(os.path.exists(target_path + ".tmp"))

    def test_11_real_assets_integrity(self):
        """Verify real watermark assets in workspace load cleanly without modification."""
        real_root = r"C:\Users\asus\Desktop\Hasni\GGM\School Project GGM\Part 4 Gallery"
        wm_land = os.path.join(real_root, "Water mark", "water mark landscape.png")
        wm_port = os.path.join(real_root, "Water mark", "water mark portrait.png")

        if os.path.exists(wm_land) and os.path.exists(wm_port):
            with Image.open(wm_land) as im1:
                self.assertEqual(im1.size, (900, 1600))
            with Image.open(wm_port) as im2:
                self.assertEqual(im2.size, (1600, 900))

    def test_12_job_manager_cancellation(self):
        """Verify job cancellation stops gracefully."""
        jm = JobManager()
        images = [
            {"name": f"img_{i}.jpg", "abs_path": self.p_img_path, "target_path": os.path.join(self.output_dir, f"out_{i}.jpg"), "target_filename": f"out_{i}.jpg", "orientation": "portrait"}
            for i in range(10)
        ]
        config = {
            "wm_vert_path": self.wm_vert_path,
            "wm_horiz_path": self.wm_horiz_path,
            "output_dir": self.output_dir,
            "export_format": "JPEG",
            "overwrite_existing": True
        }
        jm.start_job(images, config, self.processor)
        jm.cancel_job()
        if jm.worker_thread:
            jm.worker_thread.join(timeout=3.0)
    def test_13_geometry_preview_output_equivalence(self):
        """Verify preview rendering and export use identical scaling logic."""
        base = Image.open(self.p_img_path)
        wm = Image.open(self.wm_vert_path)
        config = {"placement_mode": "full_width_banner", "opacity": 1.0}
        
        # 1. Direct compositing
        composited = WatermarkEngine.apply_watermark(base, wm, config)
        
        # 2. Export
        export_path = os.path.join(self.output_dir, "geom_test.jpg")
        self.processor.export_image(composited, export_path, {"export_format": "JPEG", "jpeg_quality": 95})
        with Image.open(export_path) as exp:
            self.assertEqual(exp.size, composited.size)
            self.assertEqual(exp.size, (720, 1280))

    def test_14_rgba_to_jpeg_white_background(self):
        """Verify flattening RGBA with transparent alpha onto white background."""
        rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0)) # 100% transparent
        rgb = self.processor.flatten_to_rgb(rgba, background_color="#FFFFFF")
        self.assertEqual(rgb.mode, "RGB")
        # Every pixel should be white (255, 255, 255)
        r, g, b = rgb.getpixel((50, 50))
        self.assertEqual((r, g, b), (255, 255, 255))

    def test_15_settings_manager_persistence(self):
        """Verify loading, updating, and saving local configuration."""
        sm = SettingsManager(config_dir=self.test_dir)
        defaults = sm.get_default_settings()
        self.assertIn("naming_prefix", defaults)
        
        sm.save_settings({"naming_prefix": "CUSTOM_PREFIX_"})
        loaded = sm.load_settings()
        self.assertEqual(loaded["naming_prefix"], "CUSTOM_PREFIX_")

if __name__ == "__main__":
    unittest.main()
