# ArtRadar

미술 리뷰, 전시, 미술관 공개 컬렉션, 미술 시장 관련 소식을 수집하는 Standard Tier Radar 프로젝트입니다. RSS 기반 미술 매체와 공개 museum API를 함께 수집하고 GitHub Pages용 HTML 리포트를 생성합니다.

## 수집 대상

- RSS: 월간미술, Artnet News, ARTnews, Artforum, ArtSelector
- Museum API: Metropolitan Museum, Art Institute of Chicago, Smithsonian

## 실행

```bash
pip install -r requirements.txt
python main.py --category art --recent-days 7 --keep-days 90 --generate-report
```

## 테스트

```bash
pytest tests/unit -m unit
pytest tests/integration -m integration
```

## 스케줄

매일 10:00 UTC (한국 19:00) 자동 수집 후 GitHub Pages 배포.

## 날짜 기준 확인

- 리포트의 `Article Timeline` 차트로 날짜별 수집량을 확인할 수 있습니다.
- `Date-based review` 섹션의 날짜 필터로 특정 날짜 기사만 카드 목록에서 바로 확인할 수 있습니다.

## 참고

- Smithsonian 소스는 `SMITHSONIAN_API_KEY` 환경변수가 있어야 활성 수집됩니다.
- `ArtSelector`는 공식 RSS 피드(`https://www.artselector.com/feed/`)로 수집합니다.
