# ================================================
# civicomfy_core/downloader/chunk_downloader.py
# Adapted from Civicomfy for A1111 (no ComfyUI deps)
# ================================================

import requests
import threading
import time
import shutil
from pathlib import Path
import os
from typing import Optional, Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import DownloadManager

from civicomfy_core.config import DEFAULT_CHUNK_SIZE, DOWNLOAD_TIMEOUT, HEAD_REQUEST_TIMEOUT


class ChunkDownloader:
    """Handles downloading files in chunks using multiple connections or fallback."""
    STATUS_UPDATE_INTERVAL = 0.5
    HEAD_REQUEST_TIMEOUT = HEAD_REQUEST_TIMEOUT
    DOWNLOAD_TIMEOUT = DOWNLOAD_TIMEOUT
    MIN_SIZE_FOR_MULTI_MB = 100

    def __init__(self, url: str, output_path: str, num_connections: int = 4,
                 chunk_size: int = DEFAULT_CHUNK_SIZE, manager: 'DownloadManager' = None,
                 download_id: str = None, api_key: Optional[str] = None,
                 known_size: Optional[int] = None):
        self.initial_url = url
        self.url = url
        self.output_path = Path(output_path)
        self.temp_dir = self.output_path.parent / f".{self.output_path.name}.parts_{download_id or int(time.time())}"
        self.num_connections = max(1, num_connections)
        self.chunk_size = chunk_size
        self.manager = manager
        self.download_id = download_id
        self.api_key = api_key
        self.known_size = known_size if known_size and known_size > 0 else None
        self.total_size = self.known_size or 0
        self.downloaded = 0
        self.connection_type = "N/A"
        self.error = None
        self.threads = []
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.part_files = []
        self._start_time = 0
        self._last_update_time = 0
        self._last_downloaded_bytes = 0
        self._speed = 0

    def _get_request_headers(self, add_range: Optional[str] = None) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if add_range:
            headers['Range'] = add_range
        return headers

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def cancel(self):
        if not self.is_cancelled:
            self.cancel_event.set()
            self.error = "Download cancelled by user"
            if self.manager and self.download_id:
                self.manager._update_download_status(self.download_id, status="cancelled", error=self.error)

    def _cleanup_temp(self, success: bool):
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
        if not success and self.output_path.exists():
            try:
                self.output_path.unlink()
            except Exception:
                pass

    def _get_range_support_and_url(self) -> Tuple[str, bool]:
        final_url = self.initial_url
        supports_ranges = False
        try:
            response = requests.head(self.initial_url, allow_redirects=True,
                                     timeout=self.HEAD_REQUEST_TIMEOUT,
                                     headers=self._get_request_headers())
            response.raise_for_status()
            final_url = response.url
            self.url = final_url
            supports_ranges = response.headers.get('accept-ranges', 'none').lower() == 'bytes'
            if self.total_size <= 0:
                head_size = int(response.headers.get('Content-Length', 0))
                if head_size > 0:
                    self.total_size = head_size
            return final_url, supports_ranges
        except Exception:
            return self.initial_url, False

    def _update_progress(self, chunk_len: int):
        with self.lock:
            self.downloaded += chunk_len
            current_time = time.monotonic()
            time_diff = current_time - self._last_update_time
            if time_diff >= self.STATUS_UPDATE_INTERVAL or self.downloaded == self.total_size:
                progress = min((self.downloaded / self.total_size) * 100, 100.0) if self.total_size > 0 else 0
                if time_diff > 0:
                    bytes_diff = self.downloaded - self._last_downloaded_bytes
                    self._speed = bytes_diff / time_diff
                self._last_update_time = current_time
                self._last_downloaded_bytes = self.downloaded
                if self.manager and self.download_id:
                    self.manager._update_download_status(
                        self.download_id, progress=progress, speed=self._speed, status="downloading")

    def download_segment(self, segment_index: int, start_byte: int, end_byte: int):
        part_file_path = self.temp_dir / f"part_{segment_index}"
        request_headers = self._get_request_headers(add_range=f'bytes={start_byte}-{end_byte}')
        retries = 3
        for current_try in range(retries):
            if self.is_cancelled:
                return
            response = None
            try:
                response = requests.get(self.url, headers=request_headers, stream=True, timeout=self.DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                bytes_written_this_segment = 0
                with open(part_file_path, 'wb') as f:
                    for chunk in response.iter_content(self.chunk_size):
                        if self.is_cancelled:
                            return
                        if chunk:
                            bytes_written = f.write(chunk)
                            bytes_written_this_segment += bytes_written
                            self._update_progress(bytes_written)
                expected_size = (end_byte - start_byte) + 1
                if bytes_written_this_segment != expected_size:
                    raise ValueError(f"Size mismatch. Expected {expected_size}, got {bytes_written_this_segment}")
                return
            except Exception as e:
                if current_try >= retries - 1:
                    self.error = f"Segment {segment_index} failed after {retries} attempts: {e}"
                    self.cancel()
                    return
                time.sleep(min(2 ** current_try, 10))
            finally:
                if response:
                    response.close()

    def merge_parts(self) -> bool:
        if not self.part_files:
            self.error = self.error or "No part files were created to merge."
            return False
        try:
            sorted_parts = sorted(self.part_files, key=lambda p: int(p.name.split('_')[-1]))
            with open(self.output_path, 'wb') as outfile:
                for part_file in sorted_parts:
                    if not part_file.exists():
                        self.error = self.error or f"Missing part file: {part_file}"
                        return False
                    with open(part_file, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile, length=1024 * 1024 * 2)
            return True
        except Exception as e:
            self.error = f"Failed to merge parts: {e}"
            return False

    def fallback_download(self) -> bool:
        self.connection_type = "Single"
        if self.manager and self.download_id:
            self.manager._update_download_status(self.download_id, connection_type=self.connection_type, status="downloading")
        self._start_time = self._start_time or time.monotonic()
        self._last_update_time = self._start_time
        self._last_downloaded_bytes = 0
        self.downloaded = 0
        response = None
        try:
            response = requests.get(self.url, stream=True, timeout=self.DOWNLOAD_TIMEOUT,
                                    allow_redirects=True, headers=self._get_request_headers())
            response.raise_for_status()
            self.url = response.url
            if self.total_size <= 0:
                get_size = int(response.headers.get('Content-Length', 0))
                if get_size > 0:
                    self.total_size = get_size
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, 'wb') as f:
                for chunk in response.iter_content(self.chunk_size):
                    if self.is_cancelled:
                        return False
                    if chunk:
                        self._update_progress(f.write(chunk))
            return not self.error
        except Exception as e:
            if not self.error:
                self.error = f"Fallback download failed: {e}"
            return False
        finally:
            if response:
                response.close()

    def download(self) -> bool:
        self._start_time = time.monotonic()
        self.downloaded = 0
        self.error = None
        self.threads = []
        self.part_files = []
        success = False
        if self.temp_dir.exists():
            self._cleanup_temp(success=False)
        final_url, supports_ranges = self._get_range_support_and_url()
        use_multi = (supports_ranges and self.num_connections > 1 and
                     self.total_size > self.MIN_SIZE_FOR_MULTI_MB * 1024 * 1024)
        try:
            if use_multi:
                success = self._do_multi_connection_download()
            else:
                success = self.fallback_download()
        except Exception as e:
            if not self.error:
                self.error = f"Unexpected download error: {e}"
            success = False
            if not self.is_cancelled:
                self.cancel()
        finally:
            self._cleanup_temp(success=success and not self.is_cancelled and not self.error)
            if self.manager and self.download_id:
                final_status = "completed" if success else ("cancelled" if self.is_cancelled else "failed")
                final_progress = 100.0 if success else (
                    (self.downloaded / self.total_size * 100) if self.total_size > 0 else 0)
                self.manager._update_download_status(
                    self.download_id, status=final_status,
                    progress=min(100.0, final_progress), speed=0,
                    error=self.error, connection_type=self.connection_type)
        return success and not self.error and not self.is_cancelled

    def _do_multi_connection_download(self) -> bool:
        self.connection_type = f"Multi ({self.num_connections})"
        if self.manager and self.download_id:
            self.manager._update_download_status(self.download_id, connection_type=self.connection_type, status="downloading")
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            self.temp_dir.mkdir(parents=True)
        except Exception as e:
            self.error = f"Failed to create temp directory: {e}"
            return False
        segment_size = self.total_size // self.num_connections
        if segment_size == 0:
            return self.fallback_download()
        segments = []
        current_byte = 0
        for i in range(self.num_connections):
            if current_byte >= self.total_size:
                break
            start_byte = current_byte
            end_byte = min(current_byte + segment_size - 1, self.total_size - 1)
            if i == self.num_connections - 1:
                end_byte = self.total_size - 1
            if start_byte <= end_byte < self.total_size:
                segments.append((i, start_byte, end_byte))
                self.part_files.append(self.temp_dir / f"part_{i}")
            current_byte = end_byte + 1
        if not segments:
            self.error = "No valid segments calculated."
            return False
        for index, start, end in segments:
            if self.is_cancelled:
                break
            t = threading.Thread(target=self.download_segment, args=(index, start, end), daemon=True)
            self.threads.append(t)
            t.start()
        active = list(self.threads)
        while active and not self.is_cancelled:
            joined = []
            for t in active:
                t.join(timeout=0.2)
                if not t.is_alive():
                    joined.append(t)
            active = [t for t in active if t not in joined]
        if self.is_cancelled or self.error:
            return False
        return self.merge_parts()
