# 운영 DB S3 백업

운영 PostgreSQL을 매일 custom-format dump로 압축해 S3 Standard에 업로드합니다.
서버에는 dump를 보관하지 않으며 업로드 크기와 SHA-256 메타데이터를 확인한 뒤
임시 파일을 바로 삭제합니다. S3 Lifecycle이 `postgresql/` 객체를 3일 후
자동 만료시킵니다.

## AWS 구성

- 리전: `ap-northeast-2`
- 버킷: `life-infra-map-db-backup-kyb-20260820`
- 퍼블릭 액세스: 전체 차단
- 기본 암호화: SSE-S3
- Lifecycle: prefix `postgresql/`, 생성 3일 후 만료

EC2 역할 `life-infra-map-ssm-role`에는 다음 최소 권한만 부여합니다. 삭제는
Lifecycle만 수행하고 EC2에는 `s3:DeleteObject`를 허용하지 않습니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDatabaseBackups",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::life-infra-map-db-backup-kyb-20260820",
      "Condition": {
        "StringLike": {
          "s3:prefix": "postgresql/*"
        }
      }
    },
    {
      "Sid": "WriteAndReadDatabaseBackups",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::life-infra-map-db-backup-kyb-20260820/postgresql/*"
    }
  ]
}
```

## EC2 설치

```bash
sudo install -m 0755 deploy/backup/life-infra-map-db-backup.sh \
  /usr/local/bin/life-infra-map-db-backup.sh
sudo install -m 0644 deploy/backup/life-infra-map-db-backup.service \
  /etc/systemd/system/life-infra-map-db-backup.service
sudo install -m 0644 deploy/backup/life-infra-map-db-backup.timer \
  /etc/systemd/system/life-infra-map-db-backup.timer
sudo install -m 0600 deploy/backup/life-infra-map-db-backup.env.example \
  /etc/default/life-infra-map-db-backup
sudo systemctl daemon-reload
sudo systemctl enable --now life-infra-map-db-backup.timer
```

기본 실행 시각은 매일 UTC 02:30, 한국 시각 11:30이며 최대 10분의 무작위
지연이 적용됩니다. 서버가 꺼져 있던 동안 실행하지 못한 백업은 다음 부팅 후
한 번 실행됩니다.

## 수동 실행과 확인

```bash
sudo systemctl start life-infra-map-db-backup.service
sudo systemctl status life-infra-map-db-backup.service --no-pager
sudo journalctl -u life-infra-map-db-backup.service --no-pager -n 100
```

업로드 전 `pg_restore --list`로 archive를 읽을 수 있는지 검사합니다. 최초 구성
시에는 S3 객체를 다시 내려받아 별도 임시 DB에 복원하고 주요 테이블 건수와
PostGIS 동작을 확인합니다.
