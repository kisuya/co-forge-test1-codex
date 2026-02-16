# AGENTS.md

## Project Overview
oh-my-stock은 KR/US 주식 급등락의 원인을 근거와 함께 1분 내 전달하는 이벤트 모니터링 서비스다.

## Docs
- 제품 요구사항: `docs/prd.md`
- 아키텍처 결정: `docs/architecture.md`
- 코딩 규칙: `docs/conventions.md`
- 기술 스택/실행: `docs/tech_stack.md`
- 신규 아이디어 백로그: `docs/backlog.md`

## Absolute Rules
- 기존 테스트 파일은 절대 수정하지 않는다.
- 커밋 전 반드시 `.forge/scripts/test_fast.sh`를 실행한다.
- 기능 완료 시 `docs/projects/current/features.json`의 해당 항목 상태만 업데이트한다.
- 새 기능을 발견하면 `docs/backlog.md`에만 추가하고, `features.json` 범위는 임의 확장하지 않는다.
- 기능 단위는 사용자 시나리오 기준으로 정의하고, 1~2일 내 검증 가능한 vertical slice로 구현한다.
- 완료 기준은 백엔드 단위가 아니라 프론트엔드+백엔드를 실제로 테스트 가능한 흐름까지 포함한다.
- 모든 파일은 300라인 이하로 유지한다.
- 원인 카드에는 근거 URL 없는 내용을 노출하지 않는다.
- 시간 데이터는 저장 시 UTC를 사용한다.

## Session Start Protocol
1. `source .forge/scripts/init.sh`
2. `cat docs/projects/current/spec.md`
3. `cat docs/projects/current/features.json`
4. `cat docs/projects/current/progress.txt`
5. 가장 높은 우선순위의 pending feature 1개만 선택해 작업한다.

## Project Context
- 활성 프로젝트 상태: `docs/projects/current/`
- 기능 정의: `docs/projects/current/features.json`
- 진행 로그: `docs/projects/current/progress.txt`
- 프로젝트 완료 후 회고: `/forge-retro`
