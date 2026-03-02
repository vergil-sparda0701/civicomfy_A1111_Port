# ================================================
# civicomfy_core/utils/helpers.py
# Utility functions adapted for A1111
# ================================================
import os
import re
import urllib.parse
from typing import Optional, List, Dict, Any


def get_model_dir(model_type: str) -> str:
    """Resolve the absolute directory path for a model type using A1111's paths."""
    from civicomfy_core.config import get_a1111_model_dirs
    model_dirs = get_a1111_model_dirs()
    normalized = (model_type or "").strip().lower()
    full_path = model_dirs.get(normalized)
    if not full_path:
        try:
            from modules import paths as a1111_paths
            base = a1111_paths.models_path
        except Exception:
            base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
        full_path = os.path.join(base, normalized)
    try:
        os.makedirs(full_path, exist_ok=True)
    except Exception as e:
        print(f"[Civicomfy] Warning: Could not create directory '{full_path}': {e}")
    return full_path


def get_subdirs(model_type: str) -> List[str]:
    """Get list of subdirectories within a model type directory."""
    base_dir = get_model_dir(model_type)
    subdirs = [""]  # Empty string = root
    try:
        for item in sorted(os.listdir(base_dir)):
            full_item = os.path.join(base_dir, item)
            if os.path.isdir(full_item) and not item.startswith("."):
                subdirs.append(item)
    except Exception:
        pass
    return subdirs


def parse_civitai_input(url_or_id: str):
    """Parse Civitai URL or ID. Returns (model_id, version_id)."""
    if not url_or_id:
        return None, None
    url_or_id = str(url_or_id).strip()
    model_id = None
    version_id = None

    if url_or_id.isdigit():
        try:
            return int(url_or_id), None
        except (ValueError, TypeError):
            return None, None

    try:
        parsed_url = urllib.parse.urlparse(url_or_id)
        if not parsed_url.scheme or not parsed_url.netloc:
            if url_or_id.startswith(("/models/", "/model-versions/")):
                parsed_url = urllib.parse.urlparse("https://civitai.com" + url_or_id)
            else:
                return None, None

        if parsed_url.netloc and "civitai.com" not in parsed_url.netloc.lower():
            return None, None

        path_parts = [p for p in parsed_url.path.split('/') if p]
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if 'modelVersionId' in query_params:
            try:
                version_id = int(query_params['modelVersionId'][0])
            except (ValueError, IndexError, TypeError):
                version_id = None

        if "models" in path_parts:
            try:
                models_index = path_parts.index("models")
                if models_index + 1 < len(path_parts):
                    potential = path_parts[models_index + 1]
                    if potential.isdigit():
                        model_id = int(potential)
            except (ValueError, IndexError, TypeError):
                pass

        if version_id is None and "model-versions" in path_parts:
            try:
                vi = path_parts.index("model-versions")
                if vi + 1 < len(path_parts):
                    potential = path_parts[vi + 1]
                    if potential.isdigit():
                        version_id = int(potential)
            except (ValueError, IndexError, TypeError):
                pass

    except Exception:
        return None, None

    return model_id, version_id


def sanitize_filename(filename: str, default_filename: str = "downloaded_model") -> str:
    """Sanitize filename for cross-OS compatibility."""
    if not filename:
        return default_filename
    if isinstance(filename, bytes):
        try:
            filename = filename.decode('utf-8')
        except UnicodeDecodeError:
            return default_filename + "_decode_error"

    sanitized = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', filename)
    sanitized = re.sub(r'[_ ]{2,}', '_', sanitized)
    sanitized = sanitized.strip('. _')

    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    base_name, ext = os.path.splitext(sanitized)
    if base_name.upper() in reserved_names:
        sanitized = f"_{base_name}_{ext}"

    if sanitized in ('.', '..'):
        sanitized = default_filename + "_invalid_name"
    if not sanitized:
        sanitized = default_filename

    max_len = 200
    if len(sanitized) > max_len:
        name_part, ext_part = os.path.splitext(sanitized)
        allowed_name_len = max_len - len(ext_part)
        if allowed_name_len <= 0:
            sanitized = sanitized[:max_len]
        else:
            sanitized = name_part[:allowed_name_len] + ext_part

    return sanitized


def select_primary_file(files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the best file from a list using heuristics."""
    if not files or not isinstance(files, list):
        return None

    primary_marked = next(
        (f for f in files if isinstance(f, dict) and f.get("primary") and f.get('downloadUrl')),
        None
    )
    if primary_marked:
        return primary_marked

    def sort_key(file_obj):
        if not isinstance(file_obj, dict):
            return 99
        if not file_obj.get('downloadUrl'):
            return 98
        name_lower = file_obj.get("name", "").lower()
        meta = file_obj.get("metadata", {}) or {}
        format_type = meta.get("format", "").lower()
        size_type = meta.get("size", "").lower()
        is_safetensor = ".safetensors" in name_lower or format_type == "safetensor"
        is_pickle = ".ckpt" in name_lower or ".pt" in name_lower or format_type == "pickletensor"
        is_pruned = size_type == "pruned"
        if is_safetensor and is_pruned:
            return 0
        if is_safetensor:
            return 1
        if is_pickle and is_pruned:
            return 2
        if is_pickle:
            return 3
        if file_obj.get("type") == "Model":
            return 4
        if file_obj.get("type") == "Pruned Model":
            return 5
        return 10

    valid_files = [f for f in files if isinstance(f, dict) and f.get("downloadUrl")]
    if not valid_files:
        return None
    return sorted(valid_files, key=sort_key)[0]
