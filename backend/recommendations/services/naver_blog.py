import requests
from django.conf import settings


NAVER_BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"


def search_naver_blogs(query, display=20, sort="sim"):
    """
    네이버 블로그 검색 API에서 제목/요약문을 가져옵니다.
    본문 전체를 저장하지 않고 태그 판별에 필요한 검색 결과만 사용합니다.
    """
    client_id = getattr(settings, "NAVER_CLIENT_ID", None)
    client_secret = getattr(settings, "NAVER_CLIENT_SECRET", None)

    if not client_id or not client_secret:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 설정되지 않았습니다.")

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    params = {
        "query": query,
        "display": display,
        "start": 1,
        "sort": sort,
    }

    response = requests.get(
        NAVER_BLOG_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=5,
    )
    response.raise_for_status()

    return response.json().get("items", [])
