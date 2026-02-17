# AGENTS.md

## Project Overview
oh-my-stock은 KR/US 주식 급등락의 원인을 근거와 함께 1분 내 전달하는 이벤트 모니터링 서비스다.

## Docs
- 제품 요구사항: `docs/prd.md`
- 아키텍처 결정: `docs/architecture.md`
- 코딩 규칙/기술 스택: `docs/conventions.md`, `docs/tech_stack.md`
- 신규 아이디어 백로그: `docs/backlog.md`

## Absolute Rules
- 기존 테스트 파일은 절대 수정하지 않는다.
- 기능을 `done`으로 바꾸기 전에 반드시 `.forge/scripts/test_fast.sh`를 통과시키고, 수동 커밋 시에도 동일하게 테스트를 선행한다.
- 오케스트레이터 세션에서는 직접 `git commit` 하지 않는다 (`checkpoint.sh`가 세션 단위 커밋 담당).
- `docs/projects/current/features.json`에서 기능 상태를 업데이트할 때 `description`은 미니 스펙(입출력/성공·실패/경계조건)으로 유지하고, 새 기능은 `docs/backlog.md`에만 추가한다.
- 기능 단위는 사용자 시나리오 기준으로 정의하고, 1~2일 내 검증 가능한 vertical slice로 구현한다.
- 완료 기준은 백엔드 단위가 아니라 프론트엔드+백엔드를 실제로 테스트 가능한 흐름까지 포함한다.
- 하나의 파일에는 하나의 책임만 — 여러 관심사가 섞이면 분리한다.
- 시간 데이터는 UTC로 저장하고, 원인 카드에는 근거 URL 없는 내용을 노출하지 않는다.
- UI 기능의 `description`에는 시각 수용기준(레이아웃/타이포/상태별 화면/반응형)을 포함하고, 검증 시 스크린샷 또는 E2E assertion으로 확인한다.
- 종목/시장 등 도메인 입력은 시드 카탈로그(또는 권위 데이터 소스) 기준 검증을 필수로 하며, 임의 값 저장을 허용하지 않는다.
- `features.json` 상태와 `progress.txt` 기록이 불일치하면 즉시 수정하고 다음 기능 작업을 시작하지 않는다.
- 수동 QA는 `scripts/manual_qa_stack.sh` 기준으로 실행해 시드 데이터/계정/로그 경로를 표준화한다.
- 로컬 웹 수동 테스트 시 CORS 허용 오리진은 `localhost`와 `127.0.0.1` 쌍을 함께 유지한다(한쪽만 허용 금지).
- UI 디자인 완성도 리스크가 높으면 다음 프로젝트에서 Tailwind + shadcn/ui 도입을 기본 대안으로 검토하고, 채택 여부를 `features.json` description에 명시한다.

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
