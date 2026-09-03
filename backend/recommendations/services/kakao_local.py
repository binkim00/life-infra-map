import requests
from django.conf import settings


KAKAO_KEYWORD_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


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
