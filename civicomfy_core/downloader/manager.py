# ================================================
# civicomfy_core/downloader/manager.py
# Download Manager adapted for A1111
# ================================================
import threading
import time
import datetime
import os
import json
import requests
import subprocess
import platform
import sys
from typing import List, Dict, Any, Optional

from civicomfy_core.config import (
    MAX_CONCURRENT_DOWNLOADS, DOWNLOAD_HISTORY_LIMIT, DEFAULT_CONNECTIONS,
    METADATA_SUFFIX, PREVIEW_SUFFIX, METADATA_DOWNLOAD_TIMEOUT, PLUGIN_ROOT
)

HISTORY_FILE_PATH = os.path.join(PLUGIN_ROOT, "download_history.json")


class DownloadManager:
    """Manages a queue of downloads, running them concurrently and saving metadata."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DOWNLOADS):
        self.queue: List[Dict[str, Any]] = []
        self.active_downloads: Dict[str, Dict[str, Any]] = {}
        self.history: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.max_concurrent = max(1, max_concurrent)
        self.running = True
        self._load_history_from_file()
        self._process_thread = threading.Thread(target=self._process_queue, daemon=True)
        print(f"[Civicomfy] Download Manager starting (Max Concurrent: {self.max_concurrent}).")
        self._process_thread.start()

    def add_to_queue(self, download_info: Dict[str, Any]) -> str:
        with self.lock:
            timestamp = int(time.time() * 1000)
            file_hint = os.path.basename(download_info.get('output_path', 'file'))[:10]
            unique_num = len([h for h in self.history if file_hint in h.get("id", "")])
            download_id = f"dl_{timestamp}_{unique_num}_{file_hint}"
            download_info["id"] = download_id
            download_info["status"] = "queued"
            download_info["added_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            download_info["progress"] = 0
            download_info["speed"] = 0
            download_info["error"] = None
            download_info["start_time"] = None
            download_info["end_time"] = None
            download_info["connection_type"] = "N/A"
            required_fields = [
                'url', 'output_path', 'num_connections', 'api_key', 'known_size',
                'civitai_model_info', 'civitai_version_info', 'civitai_primary_file',
                'thumbnail', 'filename', 'model_url_or_id', 'model_version_id',
                'model_type', 'custom_filename', 'force_redownload'
            ]
            for key in required_fields:
                if key not in download_info:
                    if key in ['civitai_model_info', 'civitai_version_info', 'civitai_primary_file']:
                        download_info[key] = {}
                    elif key == 'num_connections':
                        download_info[key] = DEFAULT_CONNECTIONS
                    elif key == 'force_redownload':
                        download_info[key] = False
                    else:
                        download_info[key] = None
            self.queue.append(download_info)
            print(f"[Civicomfy] Queued: {download_info.get('filename', 'N/A')} (ID: {download_id})")
            return download_id

    def cancel_download(self, download_id: str) -> bool:
        downloader_to_cancel = None
        with self.lock:
            for i, item in enumerate(self.queue):
                if item["id"] == download_id:
                    cancelled_info = self.queue.pop(i)
                    cancelled_info["status"] = "cancelled"
                    cancelled_info["end_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    cancelled_info["error"] = "Cancelled from queue"
                    self._add_to_history(cancelled_info)
                    return True
            if download_id in self.active_downloads:
                active_info = self.active_downloads[download_id]
                downloader_to_cancel = active_info.get("downloader_instance")
                current_status = active_info.get("status")
                if not downloader_to_cancel and current_status == "starting":
                    active_info["status"] = "cancelled"
                    active_info["end_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    active_info["error"] = "Cancelled before download started"
                    return True
                elif current_status in ["completed", "failed", "cancelled"]:
                    return False
        if downloader_to_cancel:
            try:
                if not downloader_to_cancel.is_cancelled:
                    downloader_to_cancel.cancel()
                    return True
            except Exception as e:
                self._update_download_status(download_id, status="failed", error=f"Error during cancel: {e}")
                return False
        return False

    def get_status(self) -> Dict[str, List[Dict[str, Any]]]:
        with self.lock:
            exclude = [
                'downloader_instance', 'civitai_model_info', 'civitai_version_info',
                'api_key', 'url', 'output_path', 'custom_filename', 'model_url_or_id',
            ]
            return {
                "queue": [{k: v for k, v in item.items() if k not in exclude} for item in self.queue],
                "active": [{k: v for k, v in item.items() if k not in exclude}
                           for item in self.active_downloads.values()],
                "history": [{k: v for k, v in item.items() if k not in exclude}
                            for item in self.history[:DOWNLOAD_HISTORY_LIMIT]],
            }

    def _load_history_from_file(self):
        if not os.path.exists(HISTORY_FILE_PATH):
            self.history = []
            return
        try:
            with open(HISTORY_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            if isinstance(loaded_data, list):
                self.history = [item for item in loaded_data if isinstance(item, dict) and 'id' in item][:DOWNLOAD_HISTORY_LIMIT]
            else:
                self.history = []
        except Exception:
            self.history = []

    def _save_history_to_file(self):
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE_PATH), exist_ok=True)
            temp_path = HISTORY_FILE_PATH + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.history[:DOWNLOAD_HISTORY_LIMIT], f, indent=2, ensure_ascii=False)
            os.replace(temp_path, HISTORY_FILE_PATH)
        except Exception as e:
            print(f"[Civicomfy] Warning: Failed to save history: {e}")

    def _add_to_history(self, download_info: Dict[str, Any]):
        info_copy = {k: v for k, v in download_info.items() if k != 'downloader_instance'}
        if not info_copy.get("end_time"):
            info_copy["end_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if "status" not in info_copy:
            info_copy["status"] = "unknown"
        self.history.insert(0, info_copy)
        if len(self.history) > DOWNLOAD_HISTORY_LIMIT:
            self.history = self.history[:DOWNLOAD_HISTORY_LIMIT]
        self._save_history_to_file()

    def clear_history(self) -> Dict[str, Any]:
        try:
            with self.lock:
                cleared_count = len(self.history)
                self.history = []
                if os.path.exists(HISTORY_FILE_PATH):
                    try:
                        os.remove(HISTORY_FILE_PATH)
                    except OSError as e:
                        return {"success": False, "error": f"Could not delete history file: {e}"}
            return {"success": True, "message": f"Cleared {cleared_count} history items."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def retry_download(self, original_download_id: str) -> Dict[str, Any]:
        with self.lock:
            original_info = next((h for h in self.history if h.get("id") == original_download_id), None)
        if not original_info:
            return {"success": False, "error": "Original download not found in history."}
        if original_info.get("status") not in ["failed", "cancelled"]:
            return {"success": False, "error": "Can only retry failed or cancelled downloads."}
        retry_info = {k: v for k, v in original_info.items()
                      if k not in ['id', 'status', 'progress', 'speed', 'error',
                                   'start_time', 'end_time', 'added_time', 'connection_type']}
        retry_info['force_redownload'] = True
        try:
            new_download_id = self.add_to_queue(retry_info)
            if new_download_id:
                with self.lock:
                    self.history = [h for h in self.history if h.get("id") != original_download_id]
                return {"success": True, "message": "Retry queued.", "new_download_id": new_download_id}
        except Exception as e:
            return {"success": False, "error": f"Failed to queue retry: {e}"}
        return {"success": False, "error": "Failed to queue retry (unknown error)."}

    def open_containing_folder(self, download_id: str) -> Dict[str, Any]:
        with self.lock:
            item_info = next((h for h in self.history if h.get("id") == download_id), None)
            if not item_info:
                item_info = self.active_downloads.get(download_id)
        if not item_info:
            return {"success": False, "error": "Download ID not found."}
        if item_info.get("status") != "completed":
            return {"success": False, "error": "Can only open path for completed downloads."}
        file_path = item_info.get("output_path")
        if not file_path:
            return {"success": False, "error": "Output path not found."}
        folder_path = os.path.dirname(os.path.abspath(file_path))
        if not os.path.isdir(folder_path):
            return {"success": False, "error": f"Directory does not exist: {folder_path}"}
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":
                subprocess.check_call(["open", folder_path])
            elif system == "Linux":
                try:
                    subprocess.check_call(["xdg-open", folder_path])
                except FileNotFoundError:
                    return {"success": False, "error": "'xdg-open' not found."}
            else:
                return {"success": False, "error": f"Unsupported OS: {system}"}
            return {"success": True, "message": f"Opened: {folder_path}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to open directory: {e}"}

    def _process_queue(self):
        print("[Civicomfy] Process queue thread started.")
        while self.running:
            processed = False
            with self.lock:
                finished_ids = [
                    dl_id for dl_id, info in self.active_downloads.items()
                    if info.get("status") in ["completed", "failed", "cancelled"]
                ]
                for dl_id in finished_ids:
                    if dl_id in self.active_downloads:
                        finished_info = self.active_downloads.pop(dl_id)
                        self._add_to_history(finished_info)
                        processed = True

                while len(self.active_downloads) < self.max_concurrent and self.queue:
                    download_info = self.queue.pop(0)
                    download_id = download_info["id"]
                    if download_info["status"] == "cancelled":
                        if not download_info.get("end_time"):
                            download_info["end_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        self._add_to_history(download_info)
                        processed = True
                        continue
                    download_info["status"] = "starting"
                    download_info["start_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    download_info["downloader_instance"] = None
                    self.active_downloads[download_id] = download_info
                    thread = threading.Thread(target=self._download_file_wrapper, args=(download_info,), daemon=True)
                    thread.start()
                    processed = True
            if not processed:
                time.sleep(0.5)
        print("[Civicomfy] Process queue thread stopped.")

    def _update_download_status(self, download_id: str, status: Optional[str] = None,
                                progress: Optional[float] = None, speed: Optional[float] = None,
                                error: Optional[str] = None, connection_type: Optional[str] = None):
        with self.lock:
            if download_id in self.active_downloads:
                item = self.active_downloads[download_id]
                if status is not None:
                    item["status"] = status
                    if status in ["completed", "failed", "cancelled"] and not item.get("end_time"):
                        item["end_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if progress is not None:
                    item["progress"] = max(0.0, min(100.0, progress))
                if speed is not None:
                    item["speed"] = max(0.0, speed)
                if error is not None:
                    item["error"] = str(error)[:500]
                if connection_type is not None and connection_type != "N/A":
                    item["connection_type"] = connection_type

    def _save_civitai_metadata(self, download_info: Dict[str, Any]):
        output_path = download_info.get('output_path')
        model_info = download_info.get('civitai_model_info', {})
        version_info = download_info.get('civitai_version_info', {})
        primary_file = download_info.get('civitai_primary_file', {})
        download_id = download_info.get('id', 'unknown')
        if not output_path:
            return
        try:
            file_meta = primary_file.get('metadata', {}) or {}
            creator_info = model_info.get('creator', {}) or {}
            model_stats = model_info.get('stats', {}) or {}
            version_stats = version_info.get('stats', {}) or {}
            metadata = {
                "ModelId": model_info.get('id', version_info.get('modelId')),
                "ModelName": model_info.get('name', (version_info.get('model') or {}).get('name')),
                "ModelDescription": model_info.get('description'),
                "CreatorUsername": creator_info.get('username'),
                "Nsfw": model_info.get('nsfw'),
                "Tags": model_info.get('tags', []),
                "ModelType": model_info.get('type'),
                "VersionId": version_info.get('id'),
                "VersionName": version_info.get('name'),
                "VersionDescription": version_info.get('description'),
                "BaseModel": version_info.get('baseModel'),
                "VersionPublishedAt": version_info.get('publishedAt'),
                "VersionStatus": version_info.get('status'),
                "PrimaryFileId": primary_file.get('id'),
                "PrimaryFileName": primary_file.get('name'),
                "FileMetadata": {
                    "fp": file_meta.get('fp'),
                    "size": file_meta.get('size'),
                    "format": file_meta.get('format', 'Unknown')
                },
                "ImportedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "Hashes": primary_file.get('hashes', {}),
                "TrainedWords": version_info.get('trainedWords', []),
                "Stats": {
                    "downloadCount": version_stats.get('downloadCount', model_stats.get('downloadCount', 0)),
                    "rating": version_stats.get('rating', model_stats.get('rating', 0)),
                    "thumbsUpCount": version_stats.get('thumbsUpCount', 0),
                },
                "DownloadUrlUsed": download_info.get('url'),
            }
            base, _ = os.path.splitext(output_path)
            meta_path = base + METADATA_SUFFIX
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            print(f"[Civicomfy] Metadata saved: {meta_path}")
        except Exception as e:
            print(f"[Civicomfy] Warning: Could not save metadata for {download_id}: {e}")

    def _download_and_save_preview(self, download_info: Dict[str, Any]):
        output_path = download_info.get('output_path')
        thumbnail_url = download_info.get('thumbnail')
        api_key = download_info.get('api_key')
        download_id = download_info.get('id', 'unknown')
        if not output_path or not thumbnail_url:
            return
        base, _ = os.path.splitext(output_path)
        preview_path = base + PREVIEW_SUFFIX
        response = None
        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = requests.get(thumbnail_url, stream=True, headers=headers,
                                    timeout=METADATA_DOWNLOAD_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            if not content_type.startswith('image/'):
                return
            with open(preview_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[Civicomfy] Preview saved: {preview_path}")
        except Exception as e:
            print(f"[Civicomfy] Warning: Could not save preview for {download_id}: {e}")
        finally:
            if response:
                response.close()

    def _download_file_wrapper(self, download_info: Dict[str, Any]):
        from civicomfy_core.downloader.chunk_downloader import ChunkDownloader
        download_id = download_info["id"]
        filename = download_info.get('filename', download_id)
        downloader = None
        success = False
        final_status = "failed"
        error_msg = None
        try:
            downloader = ChunkDownloader(
                url=download_info["url"],
                output_path=download_info["output_path"],
                num_connections=download_info.get("num_connections", DEFAULT_CONNECTIONS),
                manager=self,
                download_id=download_id,
                api_key=download_info.get("api_key"),
                known_size=download_info.get("known_size")
            )
            with self.lock:
                if download_id not in self.active_downloads or \
                        self.active_downloads[download_id]["status"] == "cancelled":
                    self._update_download_status(download_id, status="cancelled", error="Cancelled before start")
                    return
                self.active_downloads[download_id]["downloader_instance"] = downloader

            self._update_download_status(download_id, status="downloading")
            success = downloader.download()
            error_msg = downloader.error
            if success:
                final_status = "completed"
                try:
                    self._save_civitai_metadata(download_info)
                    self._download_and_save_preview(download_info)
                except Exception as meta_err:
                    print(f"[Civicomfy] Warning: Post-download error for {download_id}: {meta_err}")
            elif downloader.is_cancelled:
                final_status = "cancelled"
                error_msg = downloader.error or "Download cancelled"
            else:
                final_status = "failed"
                error_msg = downloader.error or "Download failed"
        except Exception as e:
            import traceback
            traceback.print_exc()
            final_status = "failed"
            error_msg = f"Unexpected error: {e}"
            if downloader and not downloader.is_cancelled:
                try:
                    downloader.cancel()
                except Exception:
                    pass
        finally:
            final_progress = 0
            conn_type = "N/A"
            if downloader:
                conn_type = downloader.connection_type
                if downloader.total_size and downloader.total_size > 0:
                    final_progress = downloader.downloaded / downloader.total_size * 100
                if final_status == "completed":
                    final_progress = 100.0
                final_progress = min(100.0, max(0.0, final_progress))
            self._update_download_status(
                download_id, status=final_status, progress=final_progress,
                speed=0, error=error_msg, connection_type=conn_type)


# Global instance
manager = DownloadManager(max_concurrent=MAX_CONCURRENT_DOWNLOADS)


def shutdown_manager():
    print("[Civicomfy] Shutdown requested.")
    if manager:
        manager.running = False
        try:
            with manager.lock:
                active_ids = list(manager.active_downloads.keys())
                queue_ids = [item['id'] for item in manager.queue]
            for dl_id in active_ids + queue_ids:
                try:
                    manager.cancel_download(dl_id)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if manager._process_thread and manager._process_thread.is_alive():
                manager._process_thread.join(timeout=2.0)
        except Exception:
            pass
    print("[Civicomfy] Shutdown complete.")


import atexit
atexit.register(shutdown_manager)
