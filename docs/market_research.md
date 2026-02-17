# Market Research: oh-my-stock

## Target User Profile
- Primary wedge (Korea):
  - 한국 거주 개인투자자 중 KR/US 종목을 함께 모니터링하고 장중 변동에 민감한 사용자.
  - 뉴스/공시/커뮤니티를 수동으로 교차 확인하는 시간이 길고, 알림 피로가 높은 사용자.
- Secondary wedge (global expansion):
  - 원인 기반 이벤트 요약을 원하는 self-directed 투자자/트레이더.
- JTBD:
  - "내 종목이 급등락했을 때 1분 안에 근거 있는 이유 후보를 확인하고, 바로 다음 행동(홀드/리밸런싱/추가 확인)을 결정하고 싶다."

## Market Size Estimation
Bottom-up (as of 2026-02-17).

1. Korea base
- 한국 개인 주식투자자: 14.23M (2025-03, Yonhap/KSD 인용).
- 해외주식 보유 개인투자자: 9.57M (2024년 말 기준, Yonhap/KSD 인용).
- Initial serviceable group assumption:
  - 해외주식 보유자 중 이벤트 민감 능동층 15~25% -> 1.44M~2.39M.

2. Korea SOM (3-year)
- Paid penetration 1~3% -> 14K~72K users.
- ARPU $8~$12/month -> ARR $1.34M~$10.37M.

3. US expansion scenario
- US population estimate (2025): 340,110,988.
- Under-18 ratio: 21.5% -> adults 266,987,126.
- Adult stock ownership (2025): 62% -> 165,532,018 stock owners.
- Long-term capture assumption (0.05~0.2% via direct/B2B distribution):
  - 83K~331K users potential.

Interpretation
- 시장 "크기"는 충분하다.
- 초기 승부처는 TAM이 아니라 신뢰도: 잘못된 원인 제시는 즉시 churn으로 이어질 가능성이 높다.

## Competitive Analysis (comparison table)
Pricing snapshot is from each service's official pricing page or announced plan page (checked on 2026-02-17).

| Product | URL | Pricing snapshot | Strengths | Weaknesses | Gap for oh-my-stock |
|---|---|---|---|---|---|
| Benzinga Pro | https://www.benzinga.com/pro/pricing-offers | Essentials $37/mo, Options Mentorship $197/mo | Fast news + scanners + squawk workflow | 고가 플랜 의존, KR 로컬 맥락 약함 | KR+US 통합 원인 카드와 한국어 설명 |
| Koyfin | https://www.koyfin.com/pricing/ | Free, Plus $39/mo, Pro $79/mo | 리서치/포트폴리오 분석 깊이 | 급등락 "원인 카드" 워크플로우는 약함 | 이벤트 중심 UX + 근거 링크 강제 |
| FINVIZ Elite | https://finviz.com/elite | $39.50/mo or $299.50/yr | Screener/alerts/backtest 강점 | KR 데이터/문맥 제한 | KR 데이터 현지화 + 사유 설명 |
| MarketBeat All Access | https://www.marketbeat.com/pricing/ | $24.95/mo | 뉴스/리포트/알림 패키지 | 개별 사용자 포지션 맥락 부족 | "내 보유 영향"을 기본 출력 |
| Seeking Alpha Premium | https://subscriptions.seekingalpha.com/ | Premium $299/yr (월 결제 옵션 제공) | 리서치 콘텐츠 품질 | 이벤트 순간 대응보다 리서치 소비 중심 | 저지연 이벤트 대응 카드 |
| OpenBB (OSS + SaaS) | https://github.com/OpenBB-finance/OpenBB / https://openbb.co/pricing | OSS SDK free, workspace paid tiers | 개발자 확장성과 데이터 통합 | 일반 리테일용 즉시사용 UX 아님 | 리테일용 curated workflow |
| FinGPT (OSS) | https://github.com/AI4Finance-Foundation/FinGPT | Open source | 금융 LLM 실험/연구 생태계 | 제품화/운영 품질은 별도 구축 필요 | 운영형 신뢰도 규칙 + UX 패키지 |

## Market Trends
- Retail participation remains high:
  - 미국 성인 주식 보유율은 2025년에도 62%.
  - 한국은 해외주식 보유 투자자 기반이 확대되어 KR/US 동시 모니터링 수요가 유지.
- Trading activity is still robust on major platforms:
  - Schwab 2025 Q4 일평균 거래 8.3M(+31% YoY), active brokerage 38.5M.
  - Robinhood 2025-04 운영지표: funded customers 25.9M, equity notional volume +123% YoY.
- Investor behavior signal:
  - EY 리포트에서 self-directed 성향(직접 투자 의사결정)이 강하게 나타나 도구 기반 의사결정 수요가 크다.

## Opportunities
- Feature opportunities to add
  - 1. Evidence Quality Gate:
    - URL 무결성, 출처 신뢰도, 중복 기사 제거, 근거 수 부족 배지.
  - 2. Confidence Transparency:
    - 점수만이 아니라 "가중치 근거"를 노출해 설명 책임 강화.
  - 3. Input Trust by Design:
    - 시드 카탈로그 강제 검색/선택, 임의 입력 차단, 시장 불일치 명시 오류.
  - 4. Alert-to-Action Loop:
    - "What changed since last alert" 델타 카드 + 재알림 이유 표기.
  - 5. Portfolio-first Output:
    - 이벤트마다 보유 수량 기준 영향(추정 손익/리스크 레벨) 기본 제공.
- Distribution opportunities
  - B2C 구독 외에 증권사/핀테크 임베드 카드 API(B2B2C)로 CAC 절감 가능.

## Sources (all URLs used)
- https://www.benzinga.com/pro/pricing-offers
- https://www.koyfin.com/pricing/
- https://finviz.com/elite
- https://www.marketbeat.com/pricing/
- https://subscriptions.seekingalpha.com/
- https://github.com/OpenBB-finance/OpenBB
- https://openbb.co/pricing
- https://github.com/AI4Finance-Foundation/FinGPT
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://data.sec.gov/
- https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020001
- https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS005
- https://www.massive.com/pricing
- https://en.yna.co.kr/view/AEN20250318004700320
- https://en.yna.co.kr/view/AEN20251103002300320
- https://www.census.gov/quickfacts/fact/table/US/PST045225
- https://www.census.gov/quickfacts/fact/table/US/AGE135224
- https://news.gallup.com/poll/266807/percentage-americans-own-stock.aspx
- https://pressroom.aboutschwab.com/press-releases/press-release/2026/Schwab-Reports-Record-4Q-and-Full-Year-2025-Results/default.aspx
- https://www.globenewswire.com/news-release/2025/05/13/3080631/0/en/Robinhood-Markets-Inc-Reports-April-2025-Operating-Data.html
- https://www.ey.com/en_us/insights/wealth-asset-management/investor-pulse
