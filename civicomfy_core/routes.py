# ================================================
# civicomfy_core/routes.py
# FastAPI routes replacing aiohttp routes (A1111 uses FastAPI/Starlette)
# ================================================
import os
import re
import json
import traceback
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


def register_routes(app):
    """Register all Civicomfy API routes with the FastAPI app."""

    from civicomfy_core.api import CivitaiAPI
    from civicomfy_core.downloader.manager import manager as download_manager
    from civicomfy_core.utils.helpers import (
        get_model_dir, get_subdirs, parse_civitai_input,
        sanitize_filename, select_primary_file
    )
    from civicomfy_core.config import (
        METADATA_SUFFIX, PREVIEW_SUFFIX, MODEL_TYPE_DISPLAY,
        CIVITAI_API_TYPE_MAP, AVAILABLE_BASE_MODELS, get_a1111_model_dirs
    )

    def resolve_api_key(payload: dict) -> Optional[str]:
        key = (payload.get("api_key") or "").strip()
        if key:
            return key
        return (os.getenv("CIVITAI_API_KEY") or "").strip() or None

    # -------------------------------------------------- #
    # GET /civicomfy/model_types
    # -------------------------------------------------- #
    @app.get("/civicomfy/model_types")
    async def get_model_types():
        return JSONResponse(MODEL_TYPE_DISPLAY)

    # -------------------------------------------------- #
    # GET /civicomfy/base_models
    # -------------------------------------------------- #
    @app.get("/civicomfy/base_models")
    async def get_base_models():
        return JSONResponse(AVAILABLE_BASE_MODELS)

    # -------------------------------------------------- #
    # GET /civicomfy/model_dirs
    # -------------------------------------------------- #
    @app.get("/civicomfy/model_dirs")
    async def get_model_dirs(model_type: str = "checkpoint"):
        try:
            base_dir = get_model_dir(model_type)
            subdirs = get_subdirs(model_type)
            return JSONResponse({
                "success": True,
                "base_dir": base_dir,
                "subdirs": subdirs,
            })
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # GET /civicomfy/model_versions
    # -------------------------------------------------- #
    @app.get("/civicomfy/model_versions")
    async def get_model_versions(request: Request):
        """Return all versions of a model (id, name, baseModel) for the search card dropdown."""
        try:
            model_id = request.query_params.get("model_id", "").strip()
            api_key_param = request.query_params.get("api_key", "").strip()
            if not model_id:
                return JSONResponse({"success": False, "error": "Missing model_id"}, status_code=400)

            resolved_key = api_key_param or (os.getenv("CIVITAI_API_KEY") or "").strip() or None
            api = CivitaiAPI(resolved_key)
            model_info = api.get_model_info(int(model_id))
            if not model_info or "error" in model_info:
                return JSONResponse({"success": False, "error": f"Model {model_id} not found."}, status_code=404)

            versions = model_info.get("modelVersions", [])
            simplified = [
                {
                    "id": v.get("id"),
                    "name": v.get("name", ""),
                    "baseModel": v.get("baseModel", ""),
                    "status": v.get("status", ""),
                }
                for v in versions
                if isinstance(v, dict)
            ]
            return JSONResponse({"success": True, "model_id": model_id, "versions": simplified})
        except Exception as e:
            traceback.print_exc()
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/model_details
    # -------------------------------------------------- #
    @app.post("/civicomfy/model_details")
    async def get_model_details(request: Request):
        try:
            data = await request.json()
            model_url_or_id = data.get("model_url_or_id", "").strip()
            req_version_id = data.get("model_version_id")
            api_key = resolve_api_key(data)

            if not model_url_or_id:
                return JSONResponse({"success": False, "error": "Missing model_url_or_id"}, status_code=400)

            api = CivitaiAPI(api_key)
            parsed_model_id, parsed_version_id = parse_civitai_input(model_url_or_id)

            target_version_id = None
            if req_version_id:
                try:
                    target_version_id = int(req_version_id)
                except (ValueError, TypeError):
                    pass
            if target_version_id is None and parsed_version_id:
                target_version_id = parsed_version_id

            target_model_id = parsed_model_id
            model_info = {}
            version_info = {}

            if target_version_id:
                ver = api.get_model_version_info(target_version_id)
                if not ver or "error" in ver:
                    return JSONResponse({"success": False, "error": f"Version {target_version_id} not found."}, status_code=404)
                version_info = ver
                if not target_model_id:
                    target_model_id = ver.get("modelId")
                if target_model_id:
                    mi = api.get_model_info(target_model_id)
                    if mi and "error" not in mi:
                        model_info = mi
            elif target_model_id:
                mi = api.get_model_info(target_model_id)
                if not mi or "error" in mi:
                    return JSONResponse({"success": False, "error": f"Model {target_model_id} not found."}, status_code=404)
                model_info = mi
                versions = model_info.get("modelVersions", [])
                if not versions:
                    return JSONResponse({"success": False, "error": "No versions found."}, status_code=404)
                best = next((v for v in versions if v.get('status') == 'Published'), versions[0])
                target_version_id = best.get('id')
                full_ver = api.get_model_version_info(target_version_id)
                version_info = full_ver if full_ver and "error" not in full_ver else best
            else:
                return JSONResponse({"success": False, "error": "Could not determine model/version ID."}, status_code=400)

            files = version_info.get("files", [])
            primary_file = select_primary_file(files)

            thumbnail_url = None
            images = version_info.get("images", [])
            if images:
                valid = [img for img in images if isinstance(img, dict) and img.get("url")]
                sorted_imgs = sorted(valid, key=lambda x: x.get('index', 0))
                img_data = next((i for i in sorted_imgs if i.get("type") == "image" and "/width=" in i["url"]), None)
                if not img_data:
                    img_data = next((i for i in sorted_imgs if i.get("type") == "image"), None)
                if not img_data and sorted_imgs:
                    img_data = sorted_imgs[0]
                if img_data and img_data.get("url"):
                    base_url = img_data["url"]
                    if "/width=" in base_url:
                        thumbnail_url = re.sub(r"/width=\d+", "/width=450", base_url)
                    else:
                        thumbnail_url = base_url + ("&" if "?" in base_url else "?") + "width=450"

            return JSONResponse({
                "success": True,
                "model_id": target_model_id,
                "version_id": target_version_id,
                "model_name": model_info.get("name", (version_info.get("model") or {}).get("name", "Unknown")),
                "version_name": version_info.get("name", ""),
                "description": model_info.get("description", ""),
                "model_type": model_info.get("type", ""),
                "base_model": version_info.get("baseModel", ""),
                "thumbnail": thumbnail_url,
                "trained_words": version_info.get("trainedWords", []),
                "tags": model_info.get("tags", []),
                "files": [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "primary": f.get("primary", False),
                        "sizeKB": f.get("sizeKB"),
                        "type": f.get("type"),
                        "metadata": f.get("metadata", {}),
                    }
                    for f in files if isinstance(f, dict) and f.get("downloadUrl")
                ],
            })
        except Exception as e:
            traceback.print_exc()
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/download
    # -------------------------------------------------- #
    @app.post("/civicomfy/download")
    async def route_download_model(request: Request):
        try:
            data = await request.json()
            model_url_or_id = data.get("model_url_or_id", "").strip()
            model_type_value = data.get("model_type", "checkpoint")
            req_version_id = data.get("model_version_id")
            custom_filename_input = (data.get("custom_filename") or "").strip()
            selected_subdir = (data.get("subdir") or "").strip()
            req_file_id = data.get("file_id")
            req_file_name_contains = (data.get("file_name_contains") or "").strip()
            num_connections = int(data.get("num_connections", 4))
            force_redownload = bool(data.get("force_redownload", False))
            api_key = resolve_api_key(data)

            if not model_url_or_id:
                return JSONResponse({"error": "Missing model_url_or_id"}, status_code=400)

            api = CivitaiAPI(api_key)
            parsed_model_id, parsed_version_id = parse_civitai_input(model_url_or_id)

            target_version_id = None
            if req_version_id:
                try:
                    target_version_id = int(req_version_id)
                except (ValueError, TypeError):
                    pass
            if target_version_id is None and parsed_version_id:
                target_version_id = parsed_version_id

            target_model_id = parsed_model_id
            model_info = {}
            version_info = {}

            if target_version_id:
                ver = api.get_model_version_info(target_version_id)
                if not ver or "error" in ver:
                    return JSONResponse({"error": f"Version {target_version_id} not found."}, status_code=404)
                version_info = ver
                if not target_model_id:
                    target_model_id = ver.get("modelId")
                if target_model_id:
                    mi = api.get_model_info(target_model_id)
                    model_info = mi if mi and "error" not in mi else {}
            elif target_model_id:
                mi = api.get_model_info(target_model_id)
                if not mi or "error" in mi:
                    return JSONResponse({"error": f"Model {target_model_id} not found."}, status_code=404)
                model_info = mi
                versions = model_info.get("modelVersions", [])
                if not versions:
                    return JSONResponse({"error": "No versions found."}, status_code=404)
                best = next((v for v in versions if v.get('status') == 'Published'), versions[0])
                target_version_id = best.get('id')
                full_ver = api.get_model_version_info(target_version_id)
                version_info = full_ver if full_ver and "error" not in full_ver else best
            else:
                return JSONResponse({"error": "Could not determine model/version ID."}, status_code=400)

            files = version_info.get("files", [])
            if not files and version_info.get("downloadUrl"):
                files = [{
                    "id": None, "name": version_info.get("name", f"version_{target_version_id}_file"),
                    "primary": True, "type": "Model",
                    "sizeKB": version_info.get("fileSizeKB"),
                    "downloadUrl": version_info["downloadUrl"],
                    "hashes": {}, "metadata": {}
                }]
            if not files:
                return JSONResponse({"error": "No files found for this version."}, status_code=404)

            # File selection
            primary_file = None
            if req_file_id is not None:
                try:
                    fid = int(str(req_file_id).strip())
                    primary_file = next(
                        (f for f in files if isinstance(f, dict) and f.get("id") == fid and f.get("downloadUrl")),
                        None
                    )
                    if not primary_file:
                        return JSONResponse({"error": f"File id {fid} not found."}, status_code=404)
                except ValueError:
                    return JSONResponse({"error": "Invalid file_id"}, status_code=400)

            if primary_file is None and req_file_name_contains:
                needle = req_file_name_contains.lower()
                candidates = [
                    f for f in files if f.get("downloadUrl") and (
                        needle in (f.get("name") or "").lower() or
                        needle in (((f.get("metadata") or {}).get("format")) or "").lower()
                    )
                ]
                primary_file = candidates[0] if candidates else None

            if primary_file is None:
                primary_file = select_primary_file(files)

            if not primary_file or not primary_file.get("downloadUrl"):
                return JSONResponse({"error": "No downloadable file found."}, status_code=404)

            download_url = primary_file["downloadUrl"]
            api_filename = primary_file.get("name", f"model_{target_model_id}_ver_{target_version_id}")
            final_filename = sanitize_filename(api_filename)

            # Subdirectory
            sub_path = ""
            if selected_subdir:
                norm_sub = os.path.normpath(selected_subdir.replace('\\', '/'))
                parts = [p for p in norm_sub.split('/') if p and p not in ('.', '..')]
                if parts:
                    sub_path = os.path.join(*[sanitize_filename(p) for p in parts])

            # Custom filename
            if custom_filename_input:
                safe_name = sanitize_filename(custom_filename_input)
                base, ext = os.path.splitext(safe_name)
                if not ext:
                    _, api_ext = os.path.splitext(api_filename)
                    ext = api_ext or ".safetensors"
                final_filename = base + ext

            # Output directory
            base_output_dir = get_model_dir(model_type_value)
            output_dir = os.path.join(base_output_dir, sub_path) if sub_path else base_output_dir
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, final_filename)

            # Check if exists
            api_size_kb = primary_file.get("sizeKB")
            api_size_bytes = int(api_size_kb * 1024) if api_size_kb else 0
            if os.path.exists(output_path) and not force_redownload:
                local_size = os.path.getsize(output_path)
                if api_size_bytes > 0 and abs(api_size_bytes - local_size) <= 1024:
                    return JSONResponse({
                        "status": "exists",
                        "message": "File already exists with matching size.",
                        "filename": final_filename,
                        "path": output_path
                    })
                else:
                    return JSONResponse({
                        "status": "exists_size_mismatch",
                        "message": "File exists but size differs. Use Force Re-download to overwrite.",
                        "filename": final_filename,
                        "path": output_path,
                        "local_size": local_size,
                        "api_size_kb": api_size_kb
                    }, status_code=409)

            # Thumbnail
            thumbnail_url = None
            thumbnail_nsfw_level = None
            images = version_info.get("images")
            if images and isinstance(images, list):
                valid = [img for img in images if isinstance(img, dict) and img.get("url")]
                sorted_imgs = sorted(valid, key=lambda x: x.get('index', 0))
                img_data = next((i for i in sorted_imgs if i.get("type") == "image" and "/width=" in i["url"]), None)
                if not img_data:
                    img_data = next((i for i in sorted_imgs if i.get("type") == "image"), None)
                if not img_data and sorted_imgs:
                    img_data = sorted_imgs[0]
                if img_data and img_data.get("url"):
                    base_url = img_data["url"]
                    thumbnail_nsfw_level = img_data.get("nsfwLevel")
                    if "/width=" in base_url:
                        thumbnail_url = re.sub(r"/width=\d+", "/width=256", base_url)
                    else:
                        thumbnail_url = base_url + ("&" if "?" in base_url else "?") + "width=256"

            model_name = model_info.get('name', (version_info.get('model') or {}).get('name', 'Unknown'))
            version_name = version_info.get('name', 'Unknown Version')
            known_size_bytes = api_size_bytes if api_size_bytes > 0 else None

            primary_meta = (primary_file.get('metadata') or {})
            download_info_dict = {
                "url": download_url,
                "output_path": output_path,
                "num_connections": num_connections,
                "known_size": known_size_bytes,
                "api_key": api_key,
                "model_url_or_id": model_url_or_id,
                "model_version_id": req_version_id,
                "custom_filename": custom_filename_input,
                "force_redownload": force_redownload,
                "filename": final_filename,
                "model_name": model_name,
                "version_name": version_name,
                "thumbnail": thumbnail_url,
                "thumbnail_nsfw_level": thumbnail_nsfw_level,
                "model_type": model_type_value,
                "file_precision": primary_meta.get("fp"),
                "file_model_size": primary_meta.get("size"),
                "file_format": primary_meta.get("format"),
                "civitai_model_id": target_model_id,
                "civitai_version_id": target_version_id,
                "civitai_file_id": primary_file.get("id"),
                "civitai_model_info": model_info,
                "civitai_version_info": version_info,
                "civitai_primary_file": primary_file,
                "trained_words": version_info.get("trainedWords", []),
            }

            download_id = download_manager.add_to_queue(download_info_dict)
            return JSONResponse({
                "status": "queued",
                "message": f"Download queued: '{final_filename}'",
                "download_id": download_id,
                "details": {
                    "filename": final_filename,
                    "model_name": model_name,
                    "version_name": version_name,
                    "thumbnail": thumbnail_url,
                    "thumbnail_nsfw_level": thumbnail_nsfw_level,
                    "path": output_path,
                    "size_kb": api_size_kb
                }
            })

        except Exception as e:
            traceback.print_exc()
            return JSONResponse({"error": "Internal Server Error", "details": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/search
    # -------------------------------------------------- #
    @app.post("/civicomfy/search")
    async def route_search_models(request: Request):
        import math
        try:
            data = await request.json()
            query = (data.get("query") or "").strip()
            model_type_keys = data.get("model_types", [])
            base_model_filters = data.get("base_models", [])
            sort = data.get("sort", "Most Downloaded")
            limit = int(data.get("limit", 20))
            page = int(data.get("page", 1))
            api_key = resolve_api_key(data)
            nsfw = data.get("nsfw", None)

            if not query and not model_type_keys and not base_model_filters:
                return JSONResponse({"error": "Search requires a query or filter."}, status_code=400)

            api = CivitaiAPI(api_key)
            api_types_filter = []
            if isinstance(model_type_keys, list) and model_type_keys and "any" not in model_type_keys:
                for key in model_type_keys:
                    api_type = CIVITAI_API_TYPE_MAP.get(key.lower())
                    if api_type and api_type not in api_types_filter:
                        api_types_filter.append(api_type)

            valid_base_models = [bm for bm in base_model_filters if isinstance(bm, str) and bm] \
                if isinstance(base_model_filters, list) else []

            meili_results = api.search_models_meili(
                query=query or None,
                types=api_types_filter or None,
                base_models=valid_base_models or None,
                sort=sort,
                limit=limit,
                page=page,
                nsfw=nsfw
            )

            if meili_results and isinstance(meili_results, dict) and "error" in meili_results:
                status_code = meili_results.get("status_code", 500) or 500
                return JSONResponse(meili_results, status_code=status_code)

            if meili_results and isinstance(meili_results, dict) and "hits" in meili_results:
                image_base_url = "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7QA"
                processed_items = []
                for hit in meili_results.get("hits", []):
                    if not isinstance(hit, dict):
                        continue
                    thumbnail_url = None
                    images = hit.get("images")
                    if images and isinstance(images, list) and len(images) > 0:
                        first_image = images[0]
                        if isinstance(first_image, dict) and first_image.get("url"):
                            image_id = first_image["url"]
                            thumbnail_url = f"{image_base_url}/{image_id}/width=256"
                    hit['thumbnailUrl'] = thumbnail_url
                    processed_items.append(hit)

                total_hits = meili_results.get("estimatedTotalHits", 0)
                total_pages = math.ceil(total_hits / limit) if limit > 0 else 0
                return JSONResponse({
                    "items": processed_items,
                    "metadata": {
                        "totalItems": total_hits,
                        "currentPage": page,
                        "pageSize": limit,
                        "totalPages": total_pages,
                    }
                })
            return JSONResponse({
                "items": [], "metadata": {
                    "totalItems": 0, "currentPage": page, "pageSize": limit, "totalPages": 0}
            })
        except Exception as e:
            traceback.print_exc()
            return JSONResponse({"error": "Internal Server Error", "details": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # GET /civicomfy/status
    # -------------------------------------------------- #
    @app.get("/civicomfy/status")
    async def route_get_status():
        try:
            return JSONResponse(download_manager.get_status())
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/cancel
    # -------------------------------------------------- #
    @app.post("/civicomfy/cancel")
    async def route_cancel_download(request: Request):
        try:
            data = await request.json()
            download_id = data.get("download_id")
            if not download_id:
                return JSONResponse({"error": "Missing download_id"}, status_code=400)
            success = download_manager.cancel_download(download_id)
            if success:
                return JSONResponse({"status": "cancelled", "download_id": download_id})
            return JSONResponse({"error": f"Download {download_id} not found or already finished."}, status_code=404)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/clear_history
    # -------------------------------------------------- #
    @app.post("/civicomfy/clear_history")
    async def route_clear_history():
        try:
            result = download_manager.clear_history()
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/retry
    # -------------------------------------------------- #
    @app.post("/civicomfy/retry")
    async def route_retry_download(request: Request):
        try:
            data = await request.json()
            download_id = data.get("download_id")
            if not download_id:
                return JSONResponse({"success": False, "error": "Missing download_id"}, status_code=400)
            result = download_manager.retry_download(download_id)
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # -------------------------------------------------- #
    # POST /civicomfy/open_path
    # -------------------------------------------------- #
    @app.post("/civicomfy/open_path")
    async def route_open_path(request: Request):
        try:
            data = await request.json()
            download_id = data.get("download_id")
            if not download_id:
                return JSONResponse({"success": False, "error": "Missing download_id"}, status_code=400)
            result = download_manager.open_containing_folder(download_id)
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    print("[Civicomfy] All routes registered successfully.")
