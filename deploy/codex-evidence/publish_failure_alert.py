#!/usr/bin/env python3
import os
import socket
import time
from pathlib import Path

import boto3


TOPIC_ARN = os.environ["COLLECTION_ALERT_SNS_TOPIC_ARN"]
RUNTIME_DIR = Path(
    os.environ.get(
        "CODEX_EVIDENCE_RUNTIME_DIR",
        "/home/ubuntu/life-infra-map/runtime/codex-evidence",
    )
)
MARKER = RUNTIME_DIR / ".last-failure-alert"
SUPPRESSION_SECONDS = int(os.environ.get("COLLECTION_ALERT_SUPPRESSION_SECONDS", "21600"))


def main() -> None:
    now = int(time.time())
    if MARKER.exists() and now - int(MARKER.stat().st_mtime) < SUPPRESSION_SECONDS:
        print("A collection failure alert was already sent recently")
        return

    subject = "[여기일지도] 태그 수집 실패"
    message = (
        "Codex 웹 태그 수집 작업이 재시도 대기 상태입니다.\n"
        f"서버: {socket.gethostname()}\n"
        "서비스: life-infra-map-codex-evidence.service\n"
        "자동으로 15분 간격 재시도하며, 성공 결과가 오래되면 복구 후 보충 실행합니다.\n"
        "EC2 상태 검사 알림도 함께 확인하세요."
    )
    boto3.client("sns", region_name="ap-northeast-2").publish(
        TopicArn=TOPIC_ARN,
        Subject=subject,
        Message=message,
    )
    MARKER.touch()
    print("Published collection failure alert")


if __name__ == "__main__":
    main()
