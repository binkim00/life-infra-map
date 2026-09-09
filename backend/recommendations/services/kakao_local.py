import requests
from django.conf import settings


KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def region_at_coordinates(lat, lng):
    """좌표의 시/도 힌트. 조회 실패 시 지역을 추정하지 않는다."""
    from django.core.cache import cache
    if lat is None or lng is None or not settings.KAKAO_REST_API_KEY:
        return ""
    key = f"map-region:{lat:.4f}:{lng:.4f}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json",
            headers={"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"},
            params={"x": lng, "y": lat, "input_coord": "WGS84"}, timeout=3,
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
        region = str(documents[0].get("region_1depth_name", "")) if documents else ""
    except (requests.RequestException, ValueError, TypeError):
        region = ""
    cache.set(key, region, timeout=3600 if region else 30)
    return region


def search_address(query):
    """Resolve administrative/address text, never a similarly named business."""
    if not settings.KAKAO_REST_API_KEY:
        raise ValueError("KAKAO_REST_API_KEY is not configured")
    response = requests.get(
        "https://dapi.kakao.com/v2/local/search/address.json",
        headers={"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"},
        params={"query": query, "analyze_type": "exact", "size": 10},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def search_places_by_keyword(
    keyword,
    lat=None,
    lng=None,
    radius=1000,
    size=5,
    category_group_code=None,
):
    if not settings.KAKAO_REST_API_KEY:
        raise ValueError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")

    headers = {
        "Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}",
    }

    params = {
        "query": keyword,
        "size": size,
    }
    if category_group_code:
        params["category_group_code"] = category_group_code

    if lat is not None and lng is not None:
        params.update({
            "x": lng,
            "y": lat,
            "sort": "distance",
        })

        if radius:
            params["radius"] = radius

    response = requests.get(
        KAKAO_KEYWORD_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=5,
    )

    response.raise_for_status()
    return response.json()
