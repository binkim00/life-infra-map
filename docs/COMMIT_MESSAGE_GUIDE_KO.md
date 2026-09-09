# 한글 커밋 메시지 규칙

마지막 갱신: 2026-09-09

## 적용 원칙

- 앞으로 새로 만드는 커밋 제목은 한글로 작성합니다.
- 기존 Conventional Commit 종류는 유지합니다: `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `chore`, `data`, `ops`.
- 형식은 `<종류>: <한글로 구체적인 변경 결과>`를 사용합니다.
- 한 커밋에는 하나의 의미 있는 변경 단위를 담습니다.
- 자동 테스트 통과, 배포, 실기기 확인은 실제 수행했을 때만 본문에 적습니다.

예시:

```text
feat: 사용자 지정 장소 저장 그룹 추가
fix: 지도 현재 위치 버튼의 핀 이동 오류 수정
perf: 저장 장소 목록 응답 크기 축소
docs: 여기일지도 오류 수정 이력 정리
```

## 과거 커밋 처리

현재 저장소에는 402개의 기존 커밋과 병합 이력이 있습니다. 이미 공유됐을 가능성이 있는 커밋 메시지를 바꾸려면 모든 커밋 해시가 변경되고 강제 푸시가 필요해 팀 브랜치와 배포 추적이 끊길 수 있습니다. 따라서 기존 Git 이력은 재작성하지 않습니다.

대신 최근 영문 커밋은 다음과 같이 한글로 읽을 수 있습니다.

| 커밋 | 기존 제목 | 한글 대응 제목 |
|---|---|---|
| `4f33f73` | `fix: make situation search conversational` | `fix: 상황 검색을 대화형 흐름으로 개선` |
| `71fac4b` | `fix: show resolved situation search area` | `fix: 상황 검색에서 해석된 지역 표시` |
| `80af122` | `fix: preserve explicit areas in situation search` | `fix: 상황 검색에서 명시한 지역 유지` |
| `91301e6` | `fix: search categories around visible map` | `fix: 현재 보이는 지도 주변에서 카테고리 검색` |
| `23aa360` | `fix: honor visible map search center` | `fix: 지도 검색 시 현재 화면 중심 좌표 반영` |
| `692fad0` | `fix: correct category and area search anchors` | `fix: 카테고리·지역 검색 기준점 보정` |
| `dd67aee` | `fix: align app map search behavior` | `fix: 앱 지도 검색 동작 통일` |
| `2349692` | `feat: polish mobile login experience` | `feat: 모바일 로그인 사용성 개선` |
| `99a529e` | `feat: search places within visible map area` | `feat: 현재 지도 영역 내 장소 검색 추가` |
| `08c97fc` | `feat: make mobile place search map first` | `feat: 모바일 장소 검색을 지도 중심으로 개편` |
| `03ca36a` | `fix: sync mobile map and enrich place details` | `fix: 모바일 지도 동기화 및 장소 상세 보강` |
| `634d767` | `feat: show current location before search` | `feat: 검색 전 현재 위치 표시` |

과거 이력을 실제로 재작성해야 한다면 별도 백업 브랜치, 원격 협업자 확인, 배포 커밋 매핑을 준비한 뒤 독립 작업으로 진행해야 합니다.
