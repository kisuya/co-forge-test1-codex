# Architecture: oh-my-stock

## 1) System Type
- **Modular Monolith + Worker** (초기 MVP)
- 구성:
  - `apps/web` (Next.js, 사용자 UI)
  - `apps/api` (FastAPI, 도메인 API)
  - `apps/worker` (비동기 수집/탐지/원인 점수화)
  - `PostgreSQL` (영속 데이터)
  - `Redis` (큐, 캐시, 레이트리밋)

이 선택은 MVP 속도와 운영 단순성을 우선하면서도, 추후 워커 분리 확장이 가능하도록 한다.

## 2) Tech Stack Rationale
- Next.js + TypeScript: 사용자 화면/SSR/SEO/생산성 균형
- FastAPI + Python: 데이터 수집/점수화 로직 개발 속도 우수
- PostgreSQL: 이벤트/관계형 데이터 무결성 보장
- Redis: 저지연 큐/캐시 처리로 알림 지연 최소화

## 3) High-Level Flow
1. 스케줄러가 KR/US 시세와 이벤트 소스(공시/뉴스)를 주기 수집
2. 변동 임계값을 초과하면 이벤트 후보 생성
3. 원인 매칭기가 시간창/키워드/소스 신뢰도로 원인 후보 1~3개 점수화
4. 원인 카드 저장 후 알림 서비스가 인앱/이메일 발송
5. 사용자는 웹에서 이벤트 히스토리와 근거 링크 조회

## 4) Directory Structure (proposed)
```text
.
├─ apps/
│  ├─ web/                # Next.js (App Router)
│  ├─ api/                # FastAPI (REST)
│  └─ worker/             # Celery/RQ worker
├─ packages/
│  └─ schemas/            # OpenAPI/JSON schema, 공통 타입
├─ infra/
│  ├─ docker/             # docker-compose, local infra
│  └─ migrations/         # DB migration scripts
├─ docs/
└─ tests/
```

## 5) Data Model (MVP)
- `users`
  - id, email, password_hash, locale, created_at
- `watchlists`
  - id, user_id, name, created_at
- `watchlist_items`
  - id, watchlist_id, symbol, market(KR/US), created_at
- `price_events`
  - id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label
- `event_reasons`
  - id, event_id, rank(1..3), reason_type, confidence_score, summary, source_url, published_at
- `notifications`
  - id, user_id, event_id, channel(in_app/email), sent_at, status
- `feedback`
  - id, user_id, event_id, reason_id, vote(helpful/not_helpful), created_at

## 6) API Design (MVP)
### Auth
- `POST /v1/auth/signup`
- `POST /v1/auth/login`

### Watchlist
- `GET /v1/watchlists`
- `POST /v1/watchlists/items`
- `DELETE /v1/watchlists/items/{item_id}`

### Events
- `GET /v1/events?symbol=&market=&from=&to=`
- `GET /v1/events/{event_id}`

### Feedback
- `POST /v1/events/{event_id}/feedback`

### Health
- `GET /health`

## 7) Key Decisions
### 아키텍처 경계
**Chose**: 웹/API/워커 3모듈의 모듈러 모놀리스
**Over**: 초기 마이크로서비스 분할
**Because**: 초기 속도와 디버깅 단순성이 중요
**Trade-offs**: 팀/트래픽 증가 시 배포 단위 분리 필요
**Revisit when**: 월간 활성 사용자 10만+, 워커 지연이 SLA 초과

### 이벤트 소스 전략
**Chose**: 공시+신뢰 뉴스 우선(SEC/OPEN DART/상용 시세)
**Over**: 소셜/커뮤니티 데이터 우선
**Because**: 근거 신뢰도와 설명 가능성 확보
**Trade-offs**: 속보성 일부 손해 가능
**Revisit when**: 사용자 요구가 속보성 중심으로 이동

### 원인 추론 방식
**Chose**: 규칙 기반 + 점수화(시간 근접도, 출처 신뢰도, 주제 일치)
**Over**: 초기부터 대형 ML 모델 단일 의존
**Because**: MVP에서 예측 가능성과 디버깅 용이성 중요
**Trade-offs**: 복잡 이벤트에서 정밀도 한계
**Revisit when**: 피드백 데이터 50k+ 축적

## 8) Non-Functional Requirements
- API 응답 p95 < 300ms(조회 API), 알림 지연 p95 < 60s
- 서비스 가용성 99.5%+
- 모든 외부 소스 호출에 타임아웃/재시도/서킷브레이커 적용
- 감사 가능성: 원인 카드마다 근거 URL/시각/점수 저장
