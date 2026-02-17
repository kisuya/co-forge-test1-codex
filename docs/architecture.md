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

### Manual QA Runtime and CORS Policy
**Chose**: 시드 데이터 내장 API 어댑터(`scripts/dev_seeded_api_adapter.py`)와 실행 래퍼(`scripts/manual_qa_stack.sh`)를 표준 수동 QA 진입점으로 유지  
**Over**: 매 세션 임시 실행 명령과 임시 CORS 설정을 수동으로 조합  
**Because**: 수동 테스트 재현성(고정 계정/데이터/로그)과 `localhost` vs `127.0.0.1` CORS 불일치 회귀를 동시에 줄이기 위해  
**Trade-offs**: 운영 런타임과 수동 QA 런타임이 분리되어 관리 포인트가 하나 늘어난다  
**Revisit when**: API 런타임이 단일 ASGI 서버로 통합되어 동일 바이너리에서 시드/QA 모드를 지원할 수 있을 때

### Frontend UI Foundation (Next Project)
**Chose**: UI 품질 리스크가 높을 때 Tailwind + shadcn/ui를 기본 가속 경로로 채택  
**Over**: 인라인 스타일 중심의 ad-hoc UI 구현 지속  
**Because**: 디자인 완성도와 일관성 확보를 에이전트 자율성에만 의존하면 결과 편차가 크고, 컴포넌트/토큰 기반 접근이 재현성과 속도를 함께 높이기 때문  
**Trade-offs**: 초기 도입/마이그레이션 비용이 추가되고, 커스텀 비주얼은 시스템 제약을 받는다  
**Revisit when**: 디자인 시스템 토큰/컴포넌트 라이브러리가 팀 기준으로 안정화되어 별도 도입 비용 없이 유지 가능한 시점

## Next-Phase Guardrails
- 기능 단위는 API/워커 작업 분해가 아니라 사용자 시나리오 단위(vertical slice)로 정의한다.
- 완료 기준은 프론트엔드+백엔드 통합 흐름을 실제로 테스트 가능한 상태로 둔다.
- 웹 UI는 기능 동작 확인만으로 완료 처리하지 않고, 시각 품질 기준(레이아웃/타이포/상태별 화면/반응형)과 E2E/스크린샷 검증을 함께 만족해야 한다.
- 종목/시장 입력은 시드 카탈로그 또는 권위 데이터 소스 기반으로 검증하고, 미존재 종목 입력은 명시적 오류 계약으로 차단한다.
- 로컬 수동 QA는 `scripts/manual_qa_stack.sh` 표준 경로를 사용하고, CORS 허용 오리진은 `localhost`/`127.0.0.1` 쌍을 함께 유지한다.
- UI 구현 시 디자인 품질 리스크가 높으면 Tailwind + shadcn/ui 조합을 우선 검토하고, 채택/비채택 근거를 기능 설명에 기록한다.
