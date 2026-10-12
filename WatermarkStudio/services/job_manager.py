import os
import time
import threading
from typing import Dict, Any, List, Optional
from .watermark import WatermarkEngine
from .image_processor import ImageProcessor
from .file_manager import FileManager

class JobManager:
    """
    Manages background batch watermarking jobs with thread synchronization,
    progress tracking, pause/resume, cancellation, and error resilience.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Unpaused by default
        self.cancel_requested = False
        self.worker_thread: Optional[threading.Thread] = None

        self.state = {
            "status": "idle",  # idle, processing, paused, completed, cancelled, failed
            "current": 0,
            "total": 0,
            "percentage": 0,
            "current_file": "",
            "logs": [],
            "failed_files": [],
            "summary": None,
            "output_dir": ""
        }

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            # Return copy of state
            return {
                **self.state,
                "is_running": self.state["status"] in ("processing", "paused"),
                "is_paused": self.state["status"] == "paused"
            }

    def start_job(
        self,
        planned_items: List[Dict[str, Any]],
        config: Dict[str, Any],
        image_processor: ImageProcessor
    ) -> bool:
        with self.lock:
            if self.state["status"] in ("processing", "paused"):
                return False

            self.cancel_requested = False
            self.pause_event.set()
            self.state = {
                "status": "processing",
                "current": 0,
                "total": len(planned_items),
                "percentage": 0,
                "current_file": "",
                "logs": [f"[{time.strftime('%H:%M:%S')}] Initialized batch with {len(planned_items)} files."],
                "failed_files": [],
                "summary": None,
                "output_dir": config.get("output_dir", "")
            }

        self.worker_thread = threading.Thread(
            target=self._execute_batch,
            args=(planned_items, config, image_processor),
            daemon=True
        )
        self.worker_thread.start()
        return True

    def pause_job(self) -> bool:
        with self.lock:
            if self.state["status"] != "processing":
                return False
            self.pause_event.clear()
            self.state["status"] = "paused"
            self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] Batch paused by user.")
            return True

    def resume_job(self) -> bool:
        with self.lock:
            if self.state["status"] != "paused":
                return False
            self.pause_event.set()
            self.state["status"] = "processing"
            self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] Batch resumed.")
            return True

    def cancel_job(self) -> bool:
        with self.lock:
            if self.state["status"] not in ("processing", "paused"):
                return False
            self.cancel_requested = True
            self.pause_event.set()  # Unblock if waiting in pause
            self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] Cancellation requested...")
            return True

    def _execute_batch(
        self,
        planned_items: List[Dict[str, Any]],
        config: Dict[str, Any],
        image_processor: ImageProcessor
    ):
        start_time = time.time()
        total = len(planned_items)
        success_count = 0
        failed_count = 0

        vert_path = config.get("wm_vert_path", "")
        horiz_path = config.get("wm_horiz_path", "")
        square_policy = config.get("square_policy", "portrait")
        overwrite = bool(config.get("overwrite_existing", False))

        for idx, item in enumerate(planned_items):
            # Check pause state
            self.pause_event.wait()

            # Check cancel
            if self.cancel_requested:
                with self.lock:
                    self.state["status"] = "cancelled"
                    self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] Job cancelled by user.")
                return

            dest_path = item["target_path"]
            src_path = item["abs_path"]
            orientation = item.get("orientation", "landscape")

            with self.lock:
                self.state["current"] = idx + 1
                self.state["current_file"] = f"{item['name']} -> {item['target_filename']}"
                self.state["percentage"] = int(((idx + 1) / total) * 100)

            # Skip if destination exists and overwrite not enabled
            if os.path.exists(dest_path) and not overwrite:
                with self.lock:
                    self.state["logs"].append(f"[{time.strftime('%H:%M:%S')}] ⚠ Skipped existing: {item['target_filename']}")
                success_count += 1
                continue

            try:
                base_img = image_processor.load_normalized_image(src_path)
                if not base_img:
                    raise ValueError("Could not read image file")

                # Load watermark for photo
                wm_img, _ = WatermarkEngine.get_watermark_for_photo(
                    orientation=orientation,
                    vert_path=vert_path,
                    horiz_path=horiz_path,
                    square_policy=square_policy
                )

                # Composite watermark
                composited = WatermarkEngine.apply_watermark(base_img, wm_img, config)

                # Export safely
                image_processor.export_image(composited, dest_path, config)
                success_count += 1

                with self.lock:
                    self.state["logs"].append(
                        f"[{time.strftime('%H:%M:%S')}] ✓ Exported {item['target_filename']} ({orientation})"
                    )
            except Exception as e:
                failed_count += 1
                err_text = f"[{time.strftime('%H:%M:%S')}] ✗ Failed {item['name']}: {str(e)}"
                with self.lock:
                    self.state["failed_files"].append({**item, "error": str(e)})
                    self.state["logs"].append(err_text)

        elapsed = round(time.time() - start_time, 2)
        with self.lock:
            self.state["status"] = "completed" if failed_count == 0 else "failed"
            self.state["summary"] = {
                "total": total,
                "processed": success_count,
                "failed": failed_count,
                "elapsed_seconds": elapsed,
                "output_dir": config.get("output_dir", "")
            }
            self.state["logs"].append(
                f"[{time.strftime('%H:%M:%S')}] 🎉 Job completed in {elapsed}s. Processed: {success_count}, Failed: {failed_count}."
            )
