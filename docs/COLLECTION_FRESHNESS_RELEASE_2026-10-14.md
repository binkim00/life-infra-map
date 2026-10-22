# 수집 신선도 4파일 선별 배포 — 완료

사용자의 수집 4파일 Git 반영·기존 수집 2서비스 배포 승인에 따라 2026-10-14 10:22:06 KST 교체를 완료했다. 기존 P0 계측·CPU checkpoint/정산 안전성은 보존했다. 추가 품질분석·장기 관찰·자동확인은 만들지 않았다.

PR10 https://github.com/binkim00/life-infra-map/pull/10 / 원본 b0a97ee0ad57bb11bfd5e21a3f20cde6b8058c8f / master c58d885c52ddf65095e1d28efb0fdc4015e6b9ba. 고정 원본의 CI run38494557277 4job 성공을 확인했다. Git 담당이 병합했으며 이 채팅은 공유 HEAD/index를 조작하지 않았다.

대상은 tag_freshness.py, place_tag_collection.py, naver_tag_evidence_provider.py, test_collection_freshness.py 네 파일뿐이다. Git blob으로 작은 COPY context를 만들고 기존 P0 image5cc9513034f32dd614a3c20253008641ef2253731e013e888fe7a9a1196914c8 위에 offline 빌드했다. 새 image는 sha256:8eaa7c0051a56e7b81c308d871093424d04340d8ebac191b47c126c5af66435d이다. 대상 외327개 파일 hash 묶음이 동일하다. CPU/worker/checkpoint/정산/heartbeat·계측·설정·migration·승인/귀속 정책·의존성 파일이 그대로다. 기존 TTL/원본 게시일/날짜불명 동작·유효 반대근거를 유지한다. 모든 후보 태그가 만료된 자료는 AI 추출을 생략하며 추가 API 호출을 넣지 않았다.

실제 새 이미지에서 network none·CPU0.5·memory384MiB·격리 SQLite로 관련64검사를 실행해 11.935초/OK였다. 기존 로컬64검사와 별개로 이미지 내부 실행을 확인했다. 운영 DB를 테스트에 연결하지 않았다. 최초 준비 명령의 JSON/Python boolean 형식 오류는 서비스 교체 전에 중단했고 수정 후 성공했다.

기존 Compose base+CPU override+P0 override 세 파일을 모두 유지하고 image/revision만 새 override로 추가했다. scheduler를 먼저 멈추고 최대501 pending행 NOWAIT 잠금/SQL2초/lock200ms/idle90초로 신규 claim을 잠시 막았다. pending37·processing0 확인 후 worker SIGTERM 종료143, worker→scheduler 교체, 검증 후 ROLLBACK으로 잠금을 풀었다. 수동 업무 UPDATE/DELETE·migration·재수집·승인변경은 없다. 잠금 전후 quota10/13=11822·10/14=5097, 예약0·rate_limited0, processing0·pending37이 동일했다.

10:23 KST 직접 확인: 두 컨테이너 새image/원본revision 일치·running·restart0·OOMfalse, 양쪽 런타임4파일 hash 일치. 환경값·명령·CPU/메모리/PID/restart/init/network 설정이 기존과 같다. 공개 health200·기존 경보4개OK. 배포 전 완결10:15~10:20 CPU평균6.71%/최대7.02%로 정상이며 이를 배포 후 부하 측정이라고 표현하지 않는다.

짧은 자연 표본4작업/9요청·날짜불일치0·새Evidence0·저장시만료0·유효긍정accepted0이었다. 새 근거가 없어 실제 품질 향상과 운영에서 만료 후보 제외 발생은 미측정이다. 합성 회귀의 만료 제외/AI 생략 통과와 구분한다. 표본을 늘리려고 새작업·추가worker·장기 대기를 하지 않았다. 이전 P0 주간/자정 기록과 미관찰인 실제 이전예약 이월/checkpoint재개/heartbeat갱신은 그대로 유지한다.

복구 자료: /home/ubuntu/life-infra-map/collection-freshness-release-20261014-b0a97ee0/override.rollback.json 및 기존 P0 image의 lifemap-collection-p0-rollback:8291766f 태그를 유지했다. 복구 시 같은 자연 정산/잠금 절차 뒤 세 기존 Compose와 rollback override로 worker→scheduler만 교체하며 DB/schema/Evidence/quota를 되감지 않는다. 이번에는 복구 실행이 필요하지 않았다.

숫자 증거: runtime/collection-freshness-release-20261014/image-verification.json, final-evidence.json, manifest.json. SSM build f0afbd9d·deploy51c63b66·post3d4ff46f 모두Success. 서버 workspace에는 build/tests/verification/deploy/deployment/postdeploy 자료가 있다. 원문·장소·주소·URL·비밀값은 보고에 포함하지 않았다.

보존audit: 기존729파일 중 다른 채팅의 GIT_INTEGRATION_PLAN 보고서만 변경됐으며 그대로 보존했다. 공유 HEAD/index는 동일하다. CODEX_STATE에는 이 채팅의 완료 milestone만 추가했다.

승인된 선별 배포와 필수 검증은 종료했다. 부모 채팅에 완료 결과와 품질 향상 미측정을 전달했다. 다음 한 가지 행동: 부모 채팅에서 전체 마무리 보고에 합친다.
