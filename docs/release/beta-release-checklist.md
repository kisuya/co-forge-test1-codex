# Beta Release Checklist

## Purpose
배포 전에 필수 게이트(API/worker/web/e2e/perf/security)와 운영 승인 로그를 확인한다.

## Required Files
- Checklist JSON: `docs/release/beta-release-checklist.json`
- Approval log: `docs/release/approval-log-vX.Y.Z.md`

## Validation Command
```bash
python3 scripts/validate_release_checklist.py docs/release/beta-release-checklist.json
```

필수 항목 하나라도 누락되거나 `false`면 non-zero exit code를 반환하며 배포를 차단한다.

## Version Tagging Procedure
1. 체크리스트 JSON에서 `version_tag`를 `vX.Y.Z` 형식으로 갱신한다.
2. 승인자와 승인 시각(UTC), 승인 로그 경로를 채운다.
3. 검증 스크립트를 실행해 성공을 확인한다.
4. 릴리즈 태그를 생성한다: `git tag -a vX.Y.Z -m "beta release vX.Y.Z"`
5. 태그를 원격에 푸시한다: `git push origin vX.Y.Z`

## Release Approval Log Template
- Version: `vX.Y.Z`
- Approved by:
- Approved at (UTC):
- Evidence links:
  - CI run URL
  - Perf/Security artifact URL
  - Rollback plan URL
