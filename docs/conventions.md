# Coding Conventions: oh-my-stock

## 1) Languages & Style
- Frontend: TypeScript `strict` 모드 필수
- Backend/Worker: Python 3.12+, type hint 필수
- 포맷터/린터:
  - TS: ESLint + Prettier
  - Python: Ruff + Black + mypy

## 2) Naming Rules
- 파일명: `kebab-case` (예: `event-reason-card.tsx`)
- React 컴포넌트: `PascalCase`
- Python 모듈: `snake_case`
- API 경로: 복수형 리소스 + 소문자 (`/v1/watchlists/items`)
- DB 테이블: 복수형 `snake_case`

## 3) File Organization
- 파일 최대 길이 300라인
- 하나의 파일은 하나의 주요 책임만 가진다
- 순환 의존 금지 (`web -> api client -> schemas` 단방향)
- 기능 스코프는 작업 단위가 아니라 사용자 시나리오 단위(1~2일 완결)로 정의한다

## 4) Error Handling
- 예외를 삼키지 않는다. 반드시 구조화 로그를 남긴다
- API 오류 응답 포맷 통일:
  - `code`, `message`, `details`, `request_id`
- 외부 API 호출은 `timeout`, `retry(지수 백오프)`, `fallback` 필수

## 5) Testing
- 테스트 프레임워크:
  - Python: `pytest`
  - Frontend: `vitest` + `@testing-library/react`
- 네이밍:
  - Python: `tests/test_*.py`
  - TS: `*.test.ts`, `*.test.tsx`
- 최소 기준:
  - 핵심 도메인 로직(감지/점수화)은 라인 커버리지 80%+
  - P0 기능은 정상/실패 케이스 각각 1개 이상 필수
  - 각 프로젝트의 핵심 사용자 시나리오는 프론트엔드+백엔드 통합 테스트 가능 상태로 완료한다
- 금지:
  - 기존 테스트 수정으로 기능을 맞추는 행위

## 6) Git & Commit
- 브랜치: `feat/*`, `fix/*`, `chore/*`
- 커밋 메시지: Conventional Commits
  - 예: `feat(events): add reason ranking pipeline`
- 커밋 전 필수:
  - `.forge/scripts/test_fast.sh` 실행 및 통과

## 7) Domain-Specific Rules
- 모든 시간 저장은 UTC, 표시만 로컬 타임존 변환
- 원인 카드에는 근거 URL 없는 항목 노출 금지
- 투자 권유/추천 표현 금지(사실 전달 중심)
