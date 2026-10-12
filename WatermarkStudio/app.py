import os
import sys
import io
import base64
import webbrowser
import threading
from typing import Dict, Any
from flask import Flask, render_template, request, jsonify, send_file, Response
from PIL import Image

# Import domain services
from services import (
    SettingsManager,
    FileManager,
    WatermarkEngine,
    ImageProcessor,
    JobManager
)

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)

settings_mgr = SettingsManager(config_dir=BASE_DIR)
image_processor = ImageProcessor()
job_manager = JobManager()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.json or {}
        success = settings_mgr.save_settings(data)
        return jsonify({"success": success})
    
    settings = settings_mgr.load_settings()
    presets = settings_mgr.get_presets()
    return jsonify({
        "settings": settings,
        "presets": presets
    })

@app.route("/api/browse", methods=["POST"])
def api_browse():
    """Opens native Windows folder/file picker dialog."""
    data = request.json or {}
    browse_type = data.get("type", "directory")
    title = data.get("title", "Select Folder")
    initial_dir = data.get("initial_dir", PARENT_DIR)

    selected_path = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        if browse_type == "directory":
            selected_path = filedialog.askdirectory(title=title, initialdir=initial_dir)
        else:
            selected_path = filedialog.askopenfilename(
                title=title,
                initialdir=initial_dir,
                filetypes=[
                    ("Image files", "*.png;*.jpg;*.jpeg;*.webp"),
                    ("PNG files", "*.png"),
                    ("All files", "*.*")
                ]
            )
        root.destroy()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "path": selected_path})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scans input folder, inspects photos, and classifies orientation."""
    data = request.json or {}
    input_dir = data.get("input_dir", "")
    output_dir = data.get("output_dir", "")
    square_policy = data.get("square_policy", "portrait")

    if not input_dir or not os.path.isdir(input_dir):
        return jsonify({"success": False, "error": "Source directory does not exist"}), 400

    found_files = FileManager.scan_directory(input_dir, output_dir=output_dir)
    images = []

    for f in found_files:
        info = image_processor.inspect_image(f["abs_path"], square_policy=square_policy)
        if info.get("valid"):
            images.append({
                **f,
                **info
            })

    portraits = sum(1 for img in images if img["orientation"] == "portrait")
    landscapes = sum(1 for img in images if img["orientation"] == "landscape")
    squares = sum(1 for img in images if img["orientation"] == "square")

    return jsonify({
        "success": True,
        "total": len(images),
        "portrait_count": portraits,
        "landscape_count": landscapes,
        "square_count": squares,
        "images": images
    })

@app.route("/api/thumbnail")
def api_thumbnail():
    """Returns a fast, cached thumbnail image for the grid."""
    path = request.args.get("path", "")
    if not path or not os.path.exists(path):
        return "Image not found", 404

    thumb_path = image_processor.get_or_create_thumbnail(path, max_size=260)
    if not thumb_path or not os.path.exists(thumb_path):
        return "Could not generate thumbnail", 500

    return send_file(thumb_path, mimetype="image/jpeg")

@app.route("/api/preview", methods=["POST"])
def api_preview():
    """
    Renders high-speed side-by-side preview with the exact same
    compositing rules as final export.
    """
    data = request.json or {}
    image_path = data.get("image_path", "")
    vert_path = data.get("wm_vert_path", "")
    horiz_path = data.get("wm_horiz_path", "")
    override_orient = data.get("orientation_override", "")
    config = data.get("config", {})

    if not image_path or not os.path.exists(image_path):
        return jsonify({"success": False, "error": "Image not found"}), 404

    try:
        base_img = image_processor.load_normalized_image(image_path)
        if not base_img:
            return jsonify({"success": False, "error": "Failed to decode image"}), 400

        w, h = base_img.size
        # Orientation determination
        if override_orient in ("portrait", "landscape", "square"):
            orientation = override_orient
        else:
            orientation = "portrait" if h > w else ("landscape" if w > h else "square")

        # Load watermark
        wm_img, wm_chosen_path = WatermarkEngine.get_watermark_for_photo(
            orientation=orientation,
            vert_path=vert_path,
            horiz_path=horiz_path,
            square_policy=config.get("square_policy", "portrait")
        )

        # Composite watermark onto full base image for perfect geometric match
        composited = WatermarkEngine.apply_watermark(base_img, wm_img, config)

        # Generate preview thumbnails (up to 1200px max)
        orig_thumb = base_img.copy()
        orig_thumb.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        buf_orig = io.BytesIO()
        image_processor.flatten_to_rgb(orig_thumb).save(buf_orig, format="JPEG", quality=85)
        orig_b64 = base64.b64encode(buf_orig.getvalue()).decode("utf-8")

        wm_thumb = composited.copy()
        wm_thumb.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        buf_wm = io.BytesIO()
        image_processor.flatten_to_rgb(wm_thumb).save(buf_wm, format="JPEG", quality=85)
        wm_b64 = base64.b64encode(buf_wm.getvalue()).decode("utf-8")

        return jsonify({
            "success": True,
            "width": w,
            "height": h,
            "orientation": orientation,
            "watermark_applied": os.path.basename(wm_chosen_path) if wm_chosen_path else "None",
            "original_b64": f"data:image/jpeg;base64,{orig_b64}",
            "watermarked_b64": f"data:image/jpeg;base64,{wm_b64}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/plan-names", methods=["POST"])
def api_plan_names():
    """Generates planned target filenames and collision resolutions."""
    data = request.json or {}
    images = data.get("images", [])
    config = data.get("config", {})

    planned = FileManager.generate_planned_filenames(images, config)
    return jsonify({
        "success": True,
        "planned": planned
    })

@app.route("/api/process", methods=["POST"])
def api_process():
    """Initiates background batch watermarking."""
    data = request.json or {}
    images = data.get("images", [])
    config = data.get("config", {})

    if not images:
        return jsonify({"success": False, "error": "No images provided for processing"}), 400

    planned = FileManager.generate_planned_filenames(images, config)
    success = job_manager.start_job(planned, config, image_processor)

    if not success:
        return jsonify({"success": False, "error": "A job is already in progress"}), 400

    return jsonify({"success": True, "message": "Batch started", "total": len(planned)})

@app.route("/api/status")
def api_status():
    """Returns live batch progress and log stream."""
    return jsonify(job_manager.get_status())

@app.route("/api/job/pause", methods=["POST"])
def api_job_pause():
    success = job_manager.pause_job()
    return jsonify({"success": success})

@app.route("/api/job/resume", methods=["POST"])
def api_job_resume():
    success = job_manager.resume_job()
    return jsonify({"success": success})

@app.route("/api/job/cancel", methods=["POST"])
def api_job_cancel():
    success = job_manager.cancel_job()
    return jsonify({"success": success})

@app.route("/api/open-folder", methods=["POST"])
def api_open_folder():
    """Safely opens folder in Windows Explorer."""
    data = request.json or {}
    folder_path = data.get("folder_path", "")

    if not folder_path or not os.path.exists(folder_path):
        return jsonify({"success": False, "error": "Folder does not exist"}), 400

    try:
        if sys.platform == "win32":
            os.startfile(folder_path)
        else:
            import subprocess
            subprocess.run(["xdg-open", folder_path])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = 5000
    print(f"==================================================")
    print(f"      Watermark Studio Pro V2 Online")
    print(f"      URL: http://127.0.0.1:{port}")
    print(f"==================================================")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
