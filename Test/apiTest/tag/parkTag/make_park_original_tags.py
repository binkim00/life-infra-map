import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[4]

INPUT_PATH = BASE_DIR / "ExData" / "CSVData" / "citypark" / "전국도시공원정보표준데이터.csv"
OUTPUT_PATH = Path(__file__).resolve().parent / "park_original_tag_results.json"
SKIPPED_PATH = Path(__file__).resolve().parent / "park_original_tag_skipped_results.json"


def safe_strip(value):
    if value is None:
        return ""
    return str(value).strip()


def to_float(value):
    value = safe_strip(value)

    if not value:
        return None

    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def extract_default_tags():
    return ["공원", "산책", "휴식"]


def extract_park_type_tags(park_type):
    tags = []

    park_type = safe_strip(park_type)

    if not park_type:
        return tags

    tags.append(park_type)

    if "어린이" in park_type:
        tags.extend(["아이동반", "가족방문", "놀이"])
    elif "근린" in park_type:
        tags.extend(["산책", "휴식", "동네공원"])
    elif "소공원" in park_type:
        tags.extend(["잠깐쉬기", "동네공원"])
    elif "문화" in park_type:
        tags.extend(["문화시설", "사진명소"])
    elif "수변" in park_type:
        tags.extend(["산책", "힐링", "물가산책"])
    elif "체육" in park_type:
        tags.extend(["운동", "체육활동"])
    elif "역사" in park_type:
        tags.extend(["역사", "문화시설", "산책"])
    elif "묘지" in park_type:
        tags.extend(["조용한", "추모"])
    elif "도시농업" in park_type:
        tags.extend(["체험", "자연"])
    elif "가로" in park_type:
        tags.extend(["산책", "잠깐쉬기"])

    return tags


def extract_area_tags(area):
    tags = []

    if area is None:
        return tags

    if area < 1500:
        tags.append("작은공원")
    elif area < 10000:
        tags.append("중형공원")
    elif area < 100000:
        tags.append("대형공원")
    else:
        tags.append("초대형공원")

    return tags


def extract_facility_tags(row):
    tags = []

    exercise = safe_strip(row.get("공원보유시설(운동시설)"))
    play = safe_strip(row.get("공원보유시설(유희시설)"))
    convenience = safe_strip(row.get("공원보유시설(편익시설)"))
    culture = safe_strip(row.get("공원보유시설(교양시설)"))
    etc = safe_strip(row.get("공원보유시설(기타시설)"))

    all_facilities_text = " ".join([
        exercise,
        play,
        convenience,
        culture,
        etc,
    ])

    if exercise:
        tags.extend(["운동시설", "운동", "체육활동"])

    if play:
        tags.extend(["놀이시설", "아이동반", "가족방문"])

    if convenience:
        tags.append("편의시설")

    if culture:
        tags.extend(["문화시설", "체험"])

    if "화장실" in all_facilities_text:
        tags.append("화장실")

    if "주차" in all_facilities_text or "주차장" in all_facilities_text:
        tags.append("주차가능")

    if "벤치" in all_facilities_text or "의자" in all_facilities_text:
        tags.append("잠깐쉬기")

    if "정자" in all_facilities_text or "파고라" in all_facilities_text:
        tags.append("쉼터")

    if "매점" in all_facilities_text or "카페" in all_facilities_text:
        tags.append("매점")

    if "음수" in all_facilities_text or "음수대" in all_facilities_text:
        tags.append("음수대")

    if "공연" in all_facilities_text or "무대" in all_facilities_text:
        tags.extend(["공연장", "문화시설"])

    if "분수" in all_facilities_text:
        tags.extend(["분수", "사진명소"])

    if "산책" in all_facilities_text or "산책로" in all_facilities_text:
        tags.append("산책")

    if "자전거" in all_facilities_text:
        tags.append("자전거")

    if "운동장" in all_facilities_text:
        tags.extend(["운동장", "체육활동"])

    if "농구" in all_facilities_text:
        tags.append("농구장")

    if "축구" in all_facilities_text:
        tags.append("축구장")

    if "테니스" in all_facilities_text:
        tags.append("테니스장")

    if "배드민턴" in all_facilities_text:
        tags.append("배드민턴장")

    return tags


def extract_name_tags(name):
    tags = []

    name = safe_strip(name)

    if not name:
        return tags

    if "호수" in name:
        tags.extend(["호수공원", "물가산책", "사진명소"])

    if "수변" in name:
        tags.extend(["수변공원", "물가산책", "힐링"])

    if "중앙" in name:
        tags.append("중심지공원")

    if "시민" in name:
        tags.append("시민공원")

    if "대공원" in name:
        tags.extend(["대표공원", "가족방문"])

    if "문화" in name:
        tags.append("문화시설")

    if "체육" in name:
        tags.extend(["운동", "체육활동"])

    if "역사" in name:
        tags.append("역사")

    if "어린이" in name:
        tags.extend(["아이동반", "가족방문"])

    if "근린" in name:
        tags.append("동네공원")

    # "산" 한 글자는 울산/부산/산동 등에도 걸려서 사용하지 않음
    if "숲" in name or "산림" in name or "생태" in name:
        tags.extend(["자연", "숲", "힐링", "산책"])

    return tags


def should_blog_candidate(row, area):
    name = safe_strip(row.get("공원명"))
    park_type = safe_strip(row.get("공원구분"))

    famous_name_keywords = [
        "대공원",
        "시민공원",
        "호수공원",
        "중앙공원",
        "수변공원",
        "문화공원",
        "체육공원",
        "역사공원",
        "생태공원",
        "올림픽공원",
    ]

    blog_target_types = [
        "문화공원",
        "수변공원",
        "체육공원",
        "역사공원",
    ]

    if area is not None and area >= 100000:
        return True
    
    if "근린공원" in park_type and area is not None and area >= 50000:
        return True

    for keyword in famous_name_keywords:
        if keyword in name:
            return True

    for target_type in blog_target_types:
        if target_type in park_type:
            return True

    return False


def make_result(row):
    name = safe_strip(row.get("공원명"))
    park_type = safe_strip(row.get("공원구분"))
    lat = safe_strip(row.get("위도"))
    lon = safe_strip(row.get("경도"))
    area = to_float(row.get("공원면적"))

    default_tags = extract_default_tags()
    park_type_tags = extract_park_type_tags(park_type)
    area_tags = extract_area_tags(area)
    facility_tags = extract_facility_tags(row)
    name_tags = extract_name_tags(name)

    original_tags = sorted(set(
        park_type_tags
        + area_tags
        + facility_tags
        + name_tags
    ))

    all_tags = sorted(set(default_tags + original_tags))

    return {
        "management_no": safe_strip(row.get("관리번호")),
        "name": name,
        "park_type": park_type,
        "road_address": safe_strip(row.get("소재지도로명주소")),
        "lot_address": safe_strip(row.get("소재지지번주소")),
        "lat": lat,
        "lon": lon,
        "area": area,
        "exercise_facility": safe_strip(row.get("공원보유시설(운동시설)")),
        "play_facility": safe_strip(row.get("공원보유시설(유희시설)")),
        "convenience_facility": safe_strip(row.get("공원보유시설(편익시설)")),
        "culture_facility": safe_strip(row.get("공원보유시설(교양시설)")),
        "etc_facility": safe_strip(row.get("공원보유시설(기타시설)")),
        "notice_date": safe_strip(row.get("지정고시일")),
        "management_agency": safe_strip(row.get("관리기관명")),
        "phone": safe_strip(row.get("전화번호")),
        "data_reference_date": safe_strip(row.get("데이터기준일자")),
        "provider_code": safe_strip(row.get("제공기관코드")),
        "provider_name": safe_strip(row.get("제공기관명")),
        "tags": all_tags,
        "default_tags": default_tags,
        "original_tags": original_tags,
        "blog_candidate": should_blog_candidate(row, area),
    }


def main():
    if not INPUT_PATH.exists():
        print(f"입력 파일이 없습니다: {INPUT_PATH}")
        return

    results = []
    skipped = []

    print(f"입력 파일: {INPUT_PATH}")
    print(f"결과 파일: {OUTPUT_PATH}")
    print(f"스킵 파일: {SKIPPED_PATH}")

    with open(INPUT_PATH, "r", encoding="cp949", newline="") as f:
        reader = csv.DictReader(f)

        for index, row in enumerate(reader, start=1):
            name = safe_strip(row.get("공원명"))
            lat = safe_strip(row.get("위도"))
            lon = safe_strip(row.get("경도"))

            if not name or not lat or not lon:
                skipped.append({
                    "row_number": index,
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "reason": "공원명 또는 좌표 누락",
                    "raw": row,
                })
                continue

            result = make_result(row)
            results.append(result)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(SKIPPED_PATH, "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)

    blog_candidate_count = sum(1 for item in results if item["blog_candidate"])

    print("작업 완료")
    print(f"전체 저장 수: {len(results)}개")
    print(f"스킵 수: {len(skipped)}개")
    print(f"블로그 태그 후보 수: {blog_candidate_count}개")
    print(f"결과 저장: {OUTPUT_PATH}")
    print(f"스킵 저장: {SKIPPED_PATH}")


if __name__ == "__main__":
    main()