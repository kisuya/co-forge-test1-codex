# Retrospective: project-001-p0-core-loop

## Summary
2026-02-16 → 2026-02-17 | 6 sessions | 7 features completed

## Goal
2주 내 KR/US 관심 종목 등록부터 급등락 감지, 원인 카드 생성, 알림 전달, 이벤트 히스토리 조회까지 P0 전체 흐름을 동작 가능한 MVP로 완성한다.

## What Was Built
- `infra-001`: FastAPI 앱 골격과 표준 오류 응답 스키마
- `watch-001`: 관심 종목 등록/삭제 API (KR/US, 중복 방지)
- `detect-001`: 급등락 감지 규칙, 디바운스, UTC 이벤트 저장
- `reason-001`: 원인 후보 1~3개 점수화 및 `source_url` 필수 노출
- `notify-001`: 인앱/이메일 알림 발송 및 30분 재알림 쿨다운
- `event-001`: 최근 30일 이벤트 히스토리 목록/상세 조회 API
- `event-002`: 히스토리 API 재시도 가능한 표준 오류 메시지 처리

## What Wasn't Built (and Why)
- 프론트엔드 사용자 플로우 구현은 이번 프로젝트에 포함되지 않았다.
- 원인: 기능을 API/워커 중심으로 잘게 쪼개면서 사용자 가치 단위(화면 포함 end-to-end)로 스코프가 유지되지 못했다.
- `features.json` 기준 deferred 기능은 없고, 7개 계획 기능은 모두 완료했다.

## What Went Well
- 우선순위 기능 7개를 모두 완료했고, 회귀 없이 `test_fast` + 전체 테스트(24개)가 통과했다.
- UTC 저장, 근거 URL 필수, 재시도 가능한 표준 오류 응답 같은 도메인 규칙이 코드와 테스트에 일관되게 반영됐다.

## What Could Be Improved
- 사용자 피드백: "기능을 너무 작게 생각하는거 같아."
- 사용자 피드백: "front-end는 왜 안만든거지? 실제로 테스트 가능한 수준으로 구현해야하는데 backend중심으로 생각하면 안되지."

## Harness Improvements
- `AGENTS.md`에 기능 스코프를 사용자 시나리오 단위(1~2일 완결)로 정의하는 규칙을 추가했다.
- `AGENTS.md`와 `docs/conventions.md`에 프론트엔드+백엔드 통합 테스트 가능한 완료 기준을 명시했다.
- `README.md`를 현재 제품 상태 기준으로 갱신해 백엔드 중심 구현 현황과 다음 단계(프론트엔드 E2E)를 명확히 했다.

## Lessons for Next Project
- 기능 분해는 작업 단위가 아니라 사용자 시나리오 단위로 잡아야 한다.
- 완료 기준은 "API 테스트 통과"가 아니라 "사용자가 실제로 검증 가능한 화면 포함 흐름 완성"이어야 한다.
- 다음 페이즈는 프론트엔드와 백엔드를 함께 묶은 vertical slice를 기본 단위로 진행한다.
