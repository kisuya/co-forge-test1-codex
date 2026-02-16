# Market Research: KR/US Stock Event Monitor

## Target User Profile
- 1차 타깃: 한국 거주 개인투자자 중 한국·미국 주식을 함께 보유/관심 등록하는 사용자.
- 행동 특성:
  - 장중 또는 장후 급등락을 자주 확인
  - 뉴스/공시/커뮤니티를 수동으로 교차 확인
  - "가격이 왜 움직였는지"를 빠르게 알고 싶지만 분석 시간은 부족
- JTBD(Job-to-be-done):
  - "내 보유 종목이 3~5% 움직였을 때, 1분 내에 이유 후보와 근거를 받고 싶다."

## Market Size Estimation
가정 기반 Bottom-up 추정(보수적)

1. **한국 모수**
- 한국 리테일 투자자 규모는 약 1,400만명대(기사 내 KSD 인용치 14.24M, 2022년말).

2. **미국 모수**
- 2025년 미국 성인 주식 보유 비중 62%(Gallup).
- 미국 인구 341.8M, 18세 미만 21.5%(Census) 기준 성인 약 268.3M.
- 성인 주식 보유자 추정: 약 166.3M.

3. **능동 투자층 가정(서비스 적합군)**
- 미국: 주식 보유자 중 10~20%가 이벤트 중심 모니터링 니즈 보유 → 16.6M~33.3M.
- 한국: 리테일 투자자 중 15~25%가 이벤트 모니터링 니즈 보유 → 2.1M~3.6M.

4. **SOM(3년 내 현실적 획득 가능 시장) 시나리오**
- 합산 적합군: 18.7M~36.9M.
- 3년 내 1% 획득: 187K~369K 사용자.
- ARPU 월 $6~$10 가정 시 연매출 잠재치: 약 $13.5M~$44.3M.

해석:
- 절대 시장은 충분히 크지만, 실제 승부는 "정확한 원인 설명"과 "알림 품질"에서 결정됨.

## Competitive Analysis (comparison table)
| 서비스 | URL | 가격(확인 시점) | 강점 | 약점 | 우리 차별화 기회 |
|---|---|---|---|---|---|
| The Fly | https://www.thefly.com/rates.php | Basic $44.99/mo, Full $74.99/mo | "왜 움직였는지" 중심의 속보 큐레이션 | 글로벌/기관 친화, 개인화 맥락 제한 | 한국어 요약 + 개인 포트폴리오 영향 설명 |
| Benzinga Pro | https://www.benzinga.com/pro/pricing-offers | $37~$197/mo | 실시간 뉴스/스캐너/오디오 | 가격대 높고 초보자 진입장벽 | KR 리테일 친화 UX + 핵심만 요약 |
| TradingView | https://www.tradingview.com/pricing/ | $12.95~$199.95/mo | 차트/알림/커뮤니티 강력 | 이벤트 원인 설명은 제한적 | "원인 추론"을 1순위 기능으로 |
| Koyfin | https://www.koyfin.com/pricing/ | Free, $39, $79/mo | 포트폴리오/리서치 깊이 | 초보자에 복잡, 원인 알림 특화 아님 | 원인 중심 워크플로우 + 한국어 |
| FINVIZ Elite | https://finviz.com/elite | $39.50/mo, $299.50/yr | 스크리너/알림/백테스트 | KR 종목/한국어 문맥 한계 | KR+US 통합과 현지화된 이벤트 설명 |
| Investing.com Alerts | https://www.investing.com/alerts/ | 무료(계정 기반) | 접근성 높고 알림 쉬움 | 원인 분석 깊이 제한 | 알림 후 즉시 "이유 카드" 제공 |

## Market Trends
- **리테일 참여 확대/지속**
  - 한국 시장은 개인 비중이 높고(기사 기준 64%), 투자자 모수가 큼.
  - 미국은 2025년 성인 주식 보유율 62%로 높은 참여율 유지.
- **거래/플랫폼 활동 증가**
  - Schwab: 2025년 4분기 일평균 거래량 8.3M(+31% YoY), 액티브 브로커리지 38.5M.
  - Robinhood(2025년 4월 운영지표): Funded customers 25.9M, Equity notional volume +123% YoY.
- **시사점**
  - "알림" 자체는 보편화. 앞으로는 "해석 품질"이 차별화 포인트.

## Opportunities
- KR+US 동시 모니터링을 기본값으로 제공하는 한국어 특화 제품 기회.
- "가격 급변 → 이유 후보 → 근거 링크 → 내 포트폴리오 영향"의 단일 플로우로 정보 탐색 시간을 대폭 단축.
- B2C 구독 외에 B2B(증권사/핀테크 위젯 API) 확장 여지.

## Sources (all URLs used)
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://data.sec.gov/
- https://opendart.fss.or.kr/
- https://polygon.io/docs/rest/quickstart
- https://polygon.io/pricing
- https://www.thefly.com/services.php
- https://www.thefly.com/rates.php
- https://www.benzinga.com/pro/pricing-offers
- https://www.tradingview.com/pricing/
- https://www.koyfin.com/pricing/
- https://finviz.com/elite
- https://www.investing.com/alerts/
- https://www.koreatimes.co.kr/economy/20231114/retail-investors-take-up-64-of-korean-stock-market
- https://news.gallup.com/poll/266807/percentage-americans-own-stock.aspx
- https://www.census.gov/quickfacts/fact/table/US/AGE135224
- https://pressroom.aboutschwab.com/press-releases/press-release/2026/Schwab-Reports-Record-4Q-and-Full-Year-2025-Results/default.aspx
- https://www.globenewswire.com/news-release/2025/05/13/3080631/0/en/Robinhood-Markets-Inc-Reports-April-2025-Operating-Data.html
