# Retrospective: project-003-12week-intensive-product-hardening

## Summary
2026-02-17 → 2026-02-17 | 24 sessions | 28 features completed

## Goal
12주 동안 입력 신뢰, 원인 신뢰, 브리프 경험, 비교 해석 경험을 고도화해 실사용 베타 수준으로 완성한다.

## What Was Built
- 관심종목 입력 신뢰 체계(시드 카탈로그 동기화/검증, 검색·선택 UX, 접근성/오류 복구)와 관련 E2E를 완료했다.
- 원인 카드 신뢰 체계(URL 품질 게이트, canonical dedupe, confidence breakdown, 상세 API/UI, 신고·정정 이력)를 end-to-end로 연결했다.
- 델타 재알림, 개장 전/장마감 브리프 생성·전달·인박스 UI, 상충 근거 비교 카드(API/UI/E2E)를 구현했다.
- KPI 스모크, 릴리즈 게이트, features/progress 불일치 점검까지 포함한 품질/운영 가드를 구축했다.

## What Wasn't Built (and Why)
- `features.json` 기준 미완료 기능은 없다(28/28 done).
- 프로젝트 범위 밖 항목(신규 시장/자산군 확장, 투자자문성 기능)은 PRD의 Out-of-Scope 정책에 따라 의도적으로 제외했다.

## What Went Well
- 기본적인 제품 컨셉이 실제 사용자 흐름에서 동작하는 수준까지 검증됐다.

## What Could Be Improved
- 서버 재기동 안정성이 낮아 수동 QA 중 API 프로세스 유지가 불안정한 구간이 있었다.
- `localhost`/`127.0.0.1` 오리진 불일치로 CORS 문제가 반복되었다.
- 시드 데이터와 테스트 환경 정합성을 세션마다 수동으로 맞추는 비용이 컸다.
- UI 디자인 완성도는 기능 구현 대비 편차가 컸고, 자율 구현만으로는 품질 일관성이 부족했다.

## Harness Improvements
- 수동 QA 표준 경로를 `scripts/manual_qa_stack.sh`로 고정하고, 시드 API 어댑터(`scripts/dev_seeded_api_adapter.py`)를 추가했다.
- CORS 기본 허용 오리진을 `localhost`/`127.0.0.1` 쌍으로 표준화하고 AGENTS/Architecture 규칙에 반영했다.
- UI 품질 리스크 시 Tailwind + shadcn/ui 도입을 기본 대안으로 검토하도록 규칙을 추가했다.

## Lessons for Next Project
- “동작하는 UI”가 아니라 “일관된 디자인 품질의 UI”를 우선 목표로 두고, 필요 시 Tailwind + shadcn/ui를 초기에 채택한다.
- 수동 QA 환경(시드 계정/데이터/CORS/로그)은 프로젝트 초반에 표준화해 디버깅 비용을 줄인다.
- 유지할 기존 방식은 이번 회고에서 별도 확정하지 않고, 다음 프로젝트 첫 1~2주 실행 결과를 보고 재평가한다.
