# ================================================
# civicomfy_core/api/civitai.py
# Civitai API wrapper
# ================================================
import requests
import json
from typing import List, Optional, Dict, Any, Union


class CivitaiAPI:
    """Simple wrapper for interacting with the Civitai API v1."""
    BASE_URL = "https://civitai.com/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_headers = {'Content-Type': 'application/json'}
        if api_key:
            self.base_headers["Authorization"] = f"Bearer {api_key}"

    def _get_request_headers(self, method: str, has_json_data: bool) -> Dict[str, str]:
        headers = self.base_headers.copy()
        if method.upper() in ["GET", "HEAD"] and not has_json_data:
            headers.pop('Content-Type', None)
        return headers

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 json_data: Optional[Dict] = None, stream: bool = False,
                 allow_redirects: bool = True, timeout: int = 30) -> Union[Dict[str, Any], requests.Response, None]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        request_headers = self._get_request_headers(method, json_data is not None)
        try:
            response = requests.request(
                method, url, headers=request_headers, params=params,
                json=json_data, stream=stream, allow_redirects=allow_redirects, timeout=timeout
            )
            response.raise_for_status()
            if stream:
                return response
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            error_detail = None
            status_code = http_err.response.status_code
            try:
                error_detail = http_err.response.json()
            except json.JSONDecodeError:
                error_detail = http_err.response.text[:200]
            return {"error": f"HTTP Error: {status_code}", "details": error_detail, "status_code": status_code}
        except requests.exceptions.RequestException as req_err:
            return {"error": str(req_err), "details": None, "status_code": None}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "details": None, "status_code": None}

    def get_model_info(self, model_id: int) -> Optional[Dict[str, Any]]:
        result = self._request("GET", f"/models/{model_id}")
        if isinstance(result, dict) and "error" in result:
            return result
        return result

    def get_model_version_info(self, version_id: int) -> Optional[Dict[str, Any]]:
        result = self._request("GET", f"/model-versions/{version_id}")
        if isinstance(result, dict) and "error" in result:
            return result
        return result

    def search_models(self, query: str, types: Optional[List[str]] = None,
                      sort: str = 'Highest Rated', period: str = 'AllTime',
                      limit: int = 20, page: int = 1,
                      nsfw: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        endpoint = "/models"
        params = {
            "limit": max(1, min(100, limit)),
            "page": max(1, page),
            "query": query,
            "sort": sort,
            "period": period
        }
        if types:
            params["types"] = types
        if nsfw is not None:
            params["nsfw"] = str(nsfw).lower()
        result = self._request("GET", endpoint, params=params)
        if isinstance(result, dict) and "error" in result:
            return result
        if isinstance(result, dict) and "items" in result and "metadata" in result:
            return result
        return {"items": [], "metadata": {"totalItems": 0, "currentPage": page, "pageSize": limit, "totalPages": 0}}

    def search_models_meili(self, query: str, types: Optional[List[str]] = None,
                            base_models: Optional[List[str]] = None,
                            sort: str = 'metrics.downloadCount:desc',
                            limit: int = 20, page: int = 1,
                            nsfw: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        meili_url = "https://search.civitai.com/multi-search"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer 8c46eb2508e21db1e9828a97968d91ab1ca1caa5f70a00e88a2ba1e286603b61'
        }
        offset = max(0, (page - 1) * limit)
        sort_mapping = {
            "Relevancy": "id:desc",
            "Most Downloaded": "metrics.downloadCount:desc",
            "Highest Rated": "metrics.thumbsUpCount:desc",
            "Most Liked": "metrics.favoriteCount:desc",
            "Most Discussed": "metrics.commentCount:desc",
            "Most Collected": "metrics.collectedCount:desc",
            "Most Buzz": "metrics.tippedAmountCount:desc",
            "Newest": "createdAt:desc",
        }
        meili_sort = [sort_mapping.get(sort, "metrics.downloadCount:desc")]
        filter_groups = []
        if types and len(types) > 0:
            type_filters = [f'"type"="{t}"' for t in types]
            filter_groups.append(type_filters)
        if base_models and len(base_models) > 0:
            base_model_filters = [f'"version.baseModel"="{bm}"' for bm in base_models]
            filter_groups.append(base_model_filters)
        if nsfw is None or nsfw is False:
            filter_groups.append("nsfwLevel IN [1, 2, 4]")
        filter_groups.append("availability = Public")
        payload = {
            "queries": [{
                "q": query if query else "",
                "indexUid": "models_v9",
                "facets": ["category.name", "checkpointType", "fileFormats", "lastVersionAtUnix",
                           "tags.name", "type", "user.username", "version.baseModel", "nsfwLevel"],
                "attributesToHighlight": [],
                "highlightPreTag": "__ais-highlight__",
                "highlightPostTag": "__/ais-highlight__",
                "limit": max(1, min(100, limit)),
                "offset": offset,
                "filter": filter_groups
            }]
        }
        if sort != "Relevancy":
            payload["queries"][0]["sort"] = meili_sort
        try:
            response = requests.post(meili_url, headers=headers, json=payload, timeout=25)
            response.raise_for_status()
            results_data = response.json()
            if not results_data or not isinstance(results_data.get('results'), list) or not results_data['results']:
                return {"hits": [], "limit": limit, "offset": offset, "estimatedTotalHits": 0}
            first_result = results_data['results'][0]
            if isinstance(first_result, dict) and "hits" in first_result:
                return first_result
            return {"hits": [], "limit": limit, "offset": offset, "estimatedTotalHits": 0}
        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            try:
                error_detail = http_err.response.json()
            except Exception:
                error_detail = http_err.response.text[:200]
            return {"error": f"Meili HTTP Error: {status_code}", "details": error_detail, "status_code": status_code}
        except Exception as req_err:
            return {"error": str(req_err), "details": None, "status_code": None}
