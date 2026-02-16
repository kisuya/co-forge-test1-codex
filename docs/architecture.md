# Architecture: oh-my-stock

## 1) Current Architecture Decision (Project 001)
- 초기 P0는 `Modular Monolith + Worker responsibilities`를 유지하되, 외부 인프라 없이 동작 가능한 백엔드 이벤트 루프를 먼저 구현했다.
- API 계층, 도메인 상태 저장소, 워커 로직(감지/원인/알림)을 분리해 규칙 검증과 테스트를 빠르게 반복할 수 있도록 했다.
- 데이터 저장은 UTC 기준으로 정규화하고, 원인 후보는 `source_url`이 없는 경우 노출하지 않는 정책을 시스템 규칙으로 강제했다.

## 2) Key Decisions and Rationale

### Decision: Rule-based detection/reason pipeline first
- Chose: 급등락 감지, 디바운스, 원인 점수화를 규칙 기반으로 먼저 구현
- Because: P0에서 설명 가능성과 테스트 안정성이 중요했고, 빠르게 회귀 테스트를 구축해야 했다
- Trade-off: 복합 이벤트에서 정밀도 확장은 이후 단계가 필요

### Decision: Standard retryable error schema
- Chose: API 실패 응답을 `code/message/details/request_id`로 통일하고, 일시 장애는 retryable 형태로 명시
- Because: 클라이언트가 재시도 가능 여부를 일관되게 판단할 수 있어야 했다
- Trade-off: 세부 오류 분류는 향후 운영 데이터 기반으로 고도화가 필요

### Decision: In-memory persistence for this phase
- Chose: 이벤트/원인/알림/관심종목 저장소를 인메모리로 두고 테스트 주도 구현
- Because: 외부 DB/큐 도입 전에 도메인 규칙 검증을 빠르게 마치기 위한 선택
- Trade-off: 재시작 내구성/동시성/운영 확장성은 보장하지 않음
- Revisit when: 프론트엔드 연동과 실제 사용 흐름 검증 단계에서 PostgreSQL/Redis 기반으로 전환

### Decision: Backend-first scope caused product gap
- Observation: 기능을 백엔드 중심으로 잘게 나누면서 사용자가 직접 검증할 프론트엔드 흐름이 빠졌다
- Action: 다음 프로젝트부터 기능 단위를 사용자 시나리오 기준 vertical slice로 정의하고, 프론트엔드+백엔드 통합 검증을 완료 기준으로 채택한다

## 3) Next-Phase Architecture Guardrails
- 기능 정의는 API/워커 작업 단위가 아니라 사용자 가치 흐름 단위로 작성한다.
- 각 핵심 기능은 화면 진입점, 서버 처리, 결과 확인까지 하나의 테스트 가능한 시나리오를 가진다.
- 인프라 전환(실DB/큐, 실제 FastAPI 런타임)은 프론트엔드 E2E 흐름과 함께 단계적으로 도입한다.
