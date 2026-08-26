#!/usr/bin/env python3
import argparse
from pathlib import Path

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic-arn", required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--message-file", required=True)
    parser.add_argument("--region", default="ap-northeast-2")
    args = parser.parse_args()
    message = Path(args.message_file).read_text(encoding="utf-8")
    boto3.client("sns", region_name=args.region).publish(
        TopicArn=args.topic_arn,
        Subject=("[\uc5ec\uae30\uc77c\uc9c0\ub3c4] {} \uc218\uc9d1 \ubcf4\uace0\uc11c".format(args.report_date))[:100],
        Message=message,
    )


if __name__ == "__main__":
    main()
