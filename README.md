# oh-my-stock

KR/US 주식 급등락 이벤트를 감지하고, 원인 후보와 근거 URL을 함께 전달하는 모니터링 서비스다.

## Current Status (Project 001 complete)
- P0 백엔드 이벤트 루프 구현 완료
- 관심 종목 관리, 급등락 감지, 원인 점수화, 알림 쿨다운, 최근 30일 이벤트 조회 API 제공
- 표준 오류 응답(`code`, `message`, `details`, `request_id`) 및 retryable 오류 처리 적용
- 테스트 스위트(24개) 통과
- 프론트엔드 사용자 플로우는 다음 프로젝트에서 구현 예정

## Quick Start

```bash
# 기본 검증 (스모크 + Python 테스트)
./.forge/scripts/test_fast.sh

# 테스트 직접 실행
python3 -m unittest discover -s tests -p "test_*.py"
```

## Local Compose Stack

```bash
# api/web/worker/postgres/redis 스택 시작
docker compose up -d

# 컨테이너만 종료하고 데이터 볼륨은 유지
docker compose down

# 컨테이너와 데이터 볼륨을 함께 초기화
docker compose down -v
```

## Bootstrap Scripts

```bash
# 1) 환경변수 로드
set -a
source .env
set +a

# 2) 의존성 설치(기본은 dry-run 로그, BOOTSTRAP_RUN_INSTALL=1이면 실제 실행)
./scripts/bootstrap_install.sh

# 3) 마이그레이션 적용
./scripts/bootstrap_migrate.sh

# 4) 헬스체크
./scripts/bootstrap_health.sh
```

## Manual QA Stack (Seeded + CORS-safe)

수동 QA 재현성을 위해 고정 시드 데이터와 CORS 기본 허용 오리진을 함께 제공한다.

```bash
# API만 실행 (시드 포함)
scripts/manual_qa_stack.sh start

# API + 웹 동시 실행
OMS_DEV_START_WEB=1 scripts/manual_qa_stack.sh start

# 상태 확인 / 중지
scripts/manual_qa_stack.sh status
scripts/manual_qa_stack.sh stop
```

기본 테스트 계정:
- email: `kisu@test.com`
- password: `thekain007`

기본 CORS 오리진:
- `http://127.0.0.1:13002`
- `http://localhost:13002`
- `http://127.0.0.1:13000`
- `http://localhost:13000`

## Project Docs
- 제품 요구사항: `docs/prd.md`
- 아키텍처 결정: `docs/architecture.md`
- 코딩 규칙: `docs/conventions.md`
- 기술 스택: `docs/tech_stack.md`
- 백로그: `docs/backlog.md`

## Forge Workflow
```bash
source .forge/scripts/init.sh
./.forge/scripts/orchestrate.sh codex
```

프로젝트 종료 후:
- `/forge-retro` (Claude) 또는 `$forge-retro` (Codex)
- 다음 단계 준비: `/forge-project` 또는 `$forge-project`
