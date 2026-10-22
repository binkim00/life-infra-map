# P0 전체 실행 — 검증·운영 반영·제한 관찰

사용자가 첨부한 1~5 전체 실행을 요청한 범위에서 진행했다. **1~4와 주간·자정 제한 관찰 기록을 완료했다.** 실제 이전날 예약 이월·checkpoint 재개·heartbeat 갱신은 관찰 사례가 없어 미관찰로 남기며 합성 PostgreSQL 검사와 구분한다. 근거 품질 개선은 확인되지 않았다.

## 완료한 1~4

| 항목 | 결과 |
|---|---|
| 1. 고정 후보 PostgreSQL | 검토 원본8291766f/treec70e0915의 실제 파생 이미지에서 PostgreSQL16.4 관련94개 모두 통과·skip0 |
| 2. 종료/CPU checkpoint 호환성 | 추가3개 통과: pending row lock으로 새claim 차단·진행 중 작업 완료, idle SIGTERM의 job/quota 보존, P0 checkpoint를 CPU 원본으로 무호출 재개·실제3요청 단일정산 |
| 3. 실제 이미지 | Python3.13.16/Django6.0.5, 검토9파일hash/CPU세함수AST확인. 의존성·기존321개 이미지파일 보존 |
| 4. 운영 반영 | 10/13 14:08:13~14:08:15 KST에 기존worker/scheduler만 교체·직접 검증. env/명령/자원 제한/network 유지, DB/API서비스 교체·migration 없음 |

고정 P0 image: `sha256:5cc9513034f32dd614a3c20253008641ef2253731e013e888fe7a9a1196914c8`, revision `8291766f16a8bcc8928fe69f2f587bbbe00a57f1`.

이전 CPU image: `sha256:19753ab879653d630e3ec431ffda96058f8efe0e0c01af26b70223ec1ff16824`, revision76e2de2f. `lifemap-collection-cpu-rollback:76e2de2f`로 보호·가용성 확인했다. 기존image를 삭제하거나 prune하지 않았다.

### 검사 환경과 범위

로컬 Docker 엔진이 꺼져 있어 같은 EC2 Docker 호스트에 **운영 network/DB와 연결하지 않는 internal 임시 network·새 PostgreSQL 컨테이너**를 구성했다. 별도 collection_release/test_collection_release만 사용했으며 운영env를 전달하지 않았다. 테스트 CPU/메모리를 제한했다. 기존DB이미지는 실행 바이너리로만 사용했고 운영DBvolume은 연결하지 않았다.

총97개는36.322초에 통과했다. Python3.13.16/Django6.0.5, PostgreSQL16.4 실제 연결을 확인했다. 20,000개 합성 장소에서 scan2000/candidates300/jobs100·PK index, planner778ms/435query 관측. 임시테스트 DB와 컨테이너/network를 종료·제거했다. 이전 공유통합본PG7 성공이나 Python3.12 CI 대신 **이번 고정 이미지에서 직접 실행한 증거**다.

최초 임시 PG의 unix-socket 임시 startup을 readiness로 오인해 TCP 연결 검사에서 중단됐다. 운영에는 영향 없이 임시환경을 종료하고 final TCP readiness로 보완한 뒤97개를 실행했다. 후보코드는 변경하지 않았다.

### 실제 안전 종료와 배포

배포 직전 기존경보4개 OK. 직전 완결15분 CPU5분 평균7.54/12.33/23.21%, Maximum 최고50.53%였다. 마지막 구간에는 격리 이미지 검사 부하도 포함돼 자연수집 기준선과 분리한다.

기존 Compose2파일·env를 그대로 사용하고 image/revision metadata만 별도override로 지정했다. 환경 값은 출력/저장하지 않고 메모리에서 전후 동일성을 비교했다. image의9파일 외321파일 digest와 Env/Cmd, 실제컨테이너 Env/Cmd·CPU/메모리/pids/restart/init/network가 동일했다.

신규계획/recovery를 멈추기 위해 scheduler를 중지하고, 기존DB의 짧은 transaction에서 최대501개 pending행을 NOWAIT로 잠가 새claim을 막았다. 업무행 update/delete는 하지 않았고 SQL2초/lock200ms·idletransaction90초 제한을 사용했다. processing0 확인 후worker를 SIGTERM으로 종료(exit143, SIGKILL137아님), 검증한image로worker→scheduler 순서 교체했다. 잠금transaction은 ROLLBACK으로 끝냈다.

잠금 시작/끝 pending264·processing0, 오늘예약일 quota요청7402/reserved0이 동일했다. schema/Evidence/quota/checkpoint를 수동변경·되감지 않았다. 이후의 업무쓰기와API호출은 기존 자연수집의 정상동작이다.

14:03/14:05 배포 준비조회에서 PostgreSQL JSON 배열의 다중행 출력을 단일행으로 해석해 실패했다. P0image교체 전 중단·기존CPU이미지running복귀를 직접확인했다. JSONB 단일행 출력으로 보완한 최종실행은14:08 성공했다. 이를 숨기거나 최초시도부터무중단성공으로표현하지 않는다.

운영 실제파일9개hash일치, 양쪽running/restart0/OOMfalse, worker_checkpoint/worker_attempt와scheduler_queue/scheduler 이벤트의 실제발생을 확인했다. 최초직접확인에는worker완료event10개가있었다. batch/watch/기존 worker ID·bounded/pacing·일일예산/기간설정을 변경하지 않았다.

## 5. 제한 관찰 진행 상태

### 주간 — 완료 (100 attempt 한도)

관찰 구간: **10/13 14:08:15.682269~14:38:15.682269 KST**, 최대30분 또는attempt100개. 읽기용 `observe.py`는 숫자event최대2000개/5MiB만 해석하고 전체시간과component를 분리한다.

14:50~14:53 KST 후속 읽기 확인 완료. **14:32:04.269917 KST에 attempt100개 한도에 도달**해 작업 표본을 그 시각에서 잘랐다. 계획한30분전체의 작업을100개라고 표현하지 않는다.

| 최종 표본 항목 | 결과 |
|---|---:|
| 완료 attempt / useful | 100 / 16 (16%) |
| Evidence / 신규 Evidence | 50 / 50 |
| 만료 / 유효 긍정 / 유효 긍정 accepted | 43 / 7 / 0 |
| checkpoint 정산 요청 | 210회 |
| 재개 checkpoint / 날짜 귀속 불일치 | 0 / 0 |
| 처리 시간 중앙값 / p95 / 최대 | 400.015 / 606.433 / 1055.201 ms |
| collector 중앙값 / p95 | 338.057 / 512.063 ms |
| save/finalize 중앙값 / p95 | 7.532 / 177.151 ms |

claim/structured/collector/settle/save/processing 각100개 모두 시간 결측0이었다. pacing 대기99개 요청합계1,380,904.478ms·실제합계1,380,948.362ms로 처리 시간과 분리했다. planner2회 2524.206/2451.67ms, scheduler tick 최댓값2857.569ms였다. 이는 전체wall시간이고 개별SQL2초 제한 위반이라고 해석하지 않는다.

READ ONLY SQL2초/lock200ms·provider/cycle/완료timestamp·LIMIT100으로 같은 최초100작업을 대조했다. 실행계획의 provider/date Index Scan을 확인했고 job100·stats 요청합계210·정산표식100·checkpoint0·예약/정산metadata불일치0·재개0으로 event와 일치했다. 이 대조만으로 모든 외부 호출이나 모든 과거작업의 exactly-once를 증명하지 않는다.

계획된 구간 안에 완전히 들어가는 **14:10~14:35 KST 5분구간5개** CPU 평균6.00~6.88%, 표본Maximum최고8.92%였다. 경계의부분구간은제외했고 마지막5분구간은작업표본한도시각14:32이후도포함하므로자원기간과작업기간을구분한다. 조회시점의 기존경보4개 모두OK·두수집컨테이너image5cc95130.../running/restart0/OOMfalse였다. 관측범위에 CPU 중단임계값·SQL timeout·날짜귀속오류가없었다. 경보이력전체나관측하지않은서비스부하는확정하지않는다.

14:53 현재quota는오늘7794/reserved0/failed0/rate_limited0, 최근이틀checkpoint/미정산checkpoint0이다. 현재snapshot은100작업의종료시각과다르므로7402→7794 증분392를표본210회와동일하게비교하지않는다. processing표본0이어서heartbeat갱신은직접미관찰이다. 표본처리최대1.06초는기본30초heartbeat주기보다짧고checkpoint재개도없었으며, 합성PostgreSQL의heartbeat/복구검사를운영실측으로대체하지않는다.

**판정:** 계측·정산·관측자원 조건은 이 제한표본에서 확인했다. 유효긍정accepted0·만료43/50으로 근거품질 개선은 확인되지 않았다. 남은것은 실제자정경계 관찰이다. 증거는 `runtime/collection-p0-release-20261013/daytime/evidence.json`.

14:14:40 KST의 **초기 부분 표본**:

- attempt27개 모두completed, useful3개·Evidence11/신규11, checkpoint단일정산요청57회.
- 유효긍정3·유효긍정accepted0·만료8·재사용0. completed를품질성공이라고판단하지않는다.
- reservation/settlement date불일치0, 완료/계획/예약/정산일모두10/13. 자정이월관찰증거는아니다.
- processing 시간중앙값396.841ms/p95 596.196ms/최대928.097ms. collector중앙값345.216ms/p95 506.311ms. 각단계측정결측0.
- planner2회elapsed2524.206/2451.67ms. 큐247 아래에서자연refill이발생해338까지올라간사례가있다. 날짜/요청/quality개선율의인과결론은내리지않는다.
- 양쪽running/restart0/OOMfalse. 실제heartbeat갱신은이표본만으로직접확인되지않았다.

14:16:45 KST 후속 READ ONLY snapshot에서 오늘quota7478/reserved0/rate_limited0, 최근이틀processing0/checkpoint0/P0telemetry36개/예약일metadata불일치0이었다. 초기57회event정산과후속76회quota증분은cutoff시각이다르므로같은표본합계로비교하지않는다.

위27개수치는초기부분표본이다. 이번후속확인에서예정구간의최초100attempt와CPU·기존경보·DB정산·heartbeat결측을대조했으며최종수치는위완료기록에있다.

14:22 KST 직접조회에서 기존경보4개는모두OK, 배포후완결14:15~14:20 CPU구간평균6.88%/Maximum8.92%였다. 이는주간30분전체자원결과가아니다. 후속observer는scheduler tick·실제/요청대기시간·checkpoint재개합계도출력하도록releaseworkspace의읽기script만보완했으며SSM Success를확인했다.

### 자정 경계 — 확인 완료·이전 예약 이월/재개는 미관찰

관찰 구간: **10/13 23:50~10/14 00:10 KST**. 후속 실행이 예정00:45가 아닌10/14 08:51 KST에 도착해08:54~09시대에 읽기 확인했다. 예정 시각에 확인을 완료했다고 표현하지 않는다. 새작업/수동retry로자정이월을만들지않았다.

| 자정 표본 항목 | 결과 |
|---|---:|
| completed attempt / DB 완료 작업 | 35 / 35 |
| event 정산 요청 / DB stats 요청합계 | 74 / 74 |
| 정산표식 / checkpoint / 재개 | 35 / 0 / 0 |
| 예약일·정산일·완료일 | 전부10/14 |
| 신규 Evidence / 만료 / 유효 긍정 accepted | 17 / 16 / 0 |
| 유효 긍정 | 1 |
| processing 중앙값 / p95 / 최대 | 388.175 / 598.842 / 670.831 ms |

로그의 planner14·scheduler40·scheduler_queue20·worker81·worker_checkpoint35·worker_attempt35를 확인했다. 35개가 모두cycle_date/completed_date/reservation_date/settlement_date10/14로 일치했다. **새날짜 계획·예약·완료 귀속은 관찰했지만10/13 예약이10/14에정산된 작업과checkpoint재개는없었다.** 이를 재개 안전성의 실제 운영 통과로 확대하지 않는다. heartbeat 갱신도 해당 짧은 작업과현재processing0 표본에서 직접 미관찰이다.

READ ONLY·SQL2초/lock200ms·cycle13~14/완료시각구간/LIMIT100·provider/date Index Scan으로 같은 작업을 대조했다.08:56현재quota는10/13 요청11822/예약0/failed0/rate_limited0,10/14 요청4336/예약0/failed0/rate_limited0이다. 이현재값은자정구간종료시각의quota snapshot이 아니므로표본74회와직접증분비교하지않는다.

자정완결5분4구간 CPU평균5.29~6.27%·Maximum최고6.67%였다. 조회현재경보4개OK·두수집컨테이너원래P0 image/running/restart0/OOMfalse다. 전체경보이력과24시간부하를확정한것은아니다. 관측범위에정산/날짜불일치나CPU중단조건은없었다.

최초observe.py의global tail2000 방식은오래된지정시간구간의event를0개로반환했다. 실제무수집으로판정하지않고 **같은시간필터+스트림반출상한2000줄/5MiB**로보완했다. worker151줄/47,266byte·scheduler94줄/24,813byte로한도미도달이었다. 기존JSON파일로그는보존돼있었다. 긴결과는SSM반환24,000문자제한으로잘려, 이미완료된명령의서버stdout에서숫자요약만읽었고DB/로그를추가재조회하지않았다.

자정증거는 `runtime/collection-p0-release-20261013/midnight/evidence.json`. 원본수집SSM cfd130df·기존출력요약552febee 모두Success/응답0이다. 만료/승인0은 주간의 [원인분석](COLLECTION_P0_QUALITY_CAUSE_2026-10-13.md)과함께보되이번17행의보류사유를새로분석했다고주장하지않는다.

이채팅의후속자동확인 `p0`는주간과이번자정구간기록을끝내고PAUSED로전환했다. 앱update결과와automation.toml의status를재확인했다. 두확인은운영설정·업무쓰기·서비스재시작없이수행했다. 이후관찰을자동으로반복하거나수집강도를확대하지않는다.

## 재현·복구와 증거

운영workspace: `/home/ubuntu/life-infra-map/p0-release-20261013-8291766f/`에 build/tests/verification/deployment/postdeploy/숫자observer가있다. 운영의실제Compose목록은기존base + CPUreleaseoverride + P0imageoverride다. `override.rollback.json`은동일기존설정을보존하고CPU image로복귀하는자료다. 롤백은검증한quiescence후서비스image만복귀하며schema/업무데이터를되감지않는다. [후보·복구계획](COLLECTION_P0_DEPLOYMENT_CANDIDATE_2026-10-13.md)의미완료조건중이번완료항목은이보고서가최신이다.

로컬증거는 `runtime/collection-p0-release-20261013/`의 evidence.json·종료/호환성검사·observe.py·실제배포script·보존audit이다. P0원본9파일이나다른채팅source는이번실행에서편집하지않았다. 새commit/push/PR/병합도하지않았다.

보존audit: 관련기존698파일 중695개동일·HEAD/index유지. 다른채팅에서변경한 SEARCH_PIPELINE_RELEASE_REVIEW·GIT_INTEGRATION_PLAN·SEARCH_PREPARED_EVIDENCE_REVIEW 보고서3개는이채팅에서쓰지않았고최신변경을보존했다. 공통CODEX_STATE에는이번milestone만추가했다.

**요청한 검증·배포·제한관찰 기록은 완료했다.** 이전예약이월/checkpoint재개/실제heartbeat갱신은미관찰,근거품질개선은미확인이다. 새환경·데이터·승인정책을바꾸어이항목을강제로성공처리하지않았다. 제품소스수정은없으며이번마무리변경파일은본보고서와CODEX_STATE,로컬증거/audit뿐이다. 다음한가지행동: 별도품질개선요청이있을때신선자료선택·장소귀속/문맥검토후보를분리해검토한다.

최종보존audit는727개기존파일중본보고서외타채팅의모바일보고서2개만변경됐고HEAD/index동일이다. MOBILE_STORE_READINESS와MOBILE_FULL_QA는이채팅에서쓰지않았으며최신변경을보존했다. 이번담당문서수정은종료했다.
