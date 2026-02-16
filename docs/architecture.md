# Architecture: oh-my-stock

## Architecture Decisions

### System Pattern
**Chose**: Modular monolith with separated API and worker responsibilities in one codebase  
**Over**: Early microservices split  
**Because**: P0에서는 빠른 구현/검증과 단순한 디버깅이 더 중요했고, 에이전트가 전체 맥락을 한 번에 이해하기 쉽다  
**Trade-offs**: 배포 단위 분리와 서비스별 독립 확장은 제한된다  
**Revisit when**: 트래픽/팀 규모 증가로 API와 워커의 독립 배포 필요성이 커질 때

### API Runtime and Framework
**Chose**: Python + FastAPI  
**Over**: Node.js 기반 API 프레임워크 단일화  
**Because**: 도메인 규칙(감지/점수화)과 API를 같은 언어로 유지해 구현 속도와 테스트 생산성을 높이기 위해  
**Trade-offs**: 프론트엔드(TypeScript)와의 언어 통일성은 낮아진다  
**Revisit when**: 프론트엔드와 API 간 타입 동기화 비용이 유지보수 병목이 될 때

### Persistence Strategy (Phase 1)
**Chose**: 인메모리 저장소로 도메인 규칙 우선 검증  
**Over**: 초기부터 PostgreSQL/Redis를 필수 의존으로 도입  
**Because**: 프로젝트 초기에는 기능 규칙과 오류 계약을 빠르게 고정하는 것이 우선이었다  
**Trade-offs**: 재시작 내구성, 운영 확장성, 동시성 안전성은 보장하지 않는다  
**Revisit when**: 프론트엔드 포함 사용자 플로우를 실제 환경 수준으로 검증해야 할 때

### Target Production Data Layer
**Chose**: PostgreSQL(영속 데이터) + Redis(큐/캐시)  
**Over**: 단일 엔진 또는 파일 기반 DB 중심 운영  
**Because**: 이벤트 이력의 무결성과 알림/비동기 처리 지연 요구를 함께 만족하기 위해  
**Trade-offs**: 로컬/운영 인프라 복잡성과 운영 포인트가 증가한다  
**Revisit when**: 이벤트 처리량과 운영 비용 데이터를 바탕으로 저장 계층 단순화가 더 유리할 때

### Error Contract
**Chose**: 표준 오류 스키마(`code`, `message`, `details`, `request_id`)와 retryable 오류 신호  
**Over**: 엔드포인트별 비일관 오류 포맷  
**Because**: 클라이언트(향후 웹 UI)가 재시도 가능 여부를 안정적으로 판단해야 한다  
**Trade-offs**: 초기에는 세밀한 도메인 오류 분류를 덜 표현한다  
**Revisit when**: 운영 로그에서 오류 유형 분리가 사용자 복구 경험에 직접 영향을 주기 시작할 때

## Next-Phase Guardrails
- 기능 단위는 API/워커 작업 분해가 아니라 사용자 시나리오 단위(vertical slice)로 정의한다.
- 완료 기준은 프론트엔드+백엔드 통합 흐름을 실제로 테스트 가능한 상태로 둔다.
