# ArtRadar - 미술 정보 레이더

**🌐 Live Report**: https://ai-frendly-datahub.github.io/ArtRadar/

미술 뉴스, 전시, 기관, 미술시장 신호와 미술작품/소장품 변화 데이터를 함께 추적하는 레이더입니다. RSS 기반 미술 매체와 공개 museum API를 조합해 수집하고, DuckDB 저장 + HTML 리포트를 GitHub Pages로 배포합니다.

## 프로젝트 목표

- **데이터 수집**: 미술 뉴스 RSS + Metropolitan Museum / Art Institute of Chicago / Smithsonian 공개 API
- **카테고리 분리**: `art`(뉴스/시장/전시)와 `artwork`(개별 작품/소장품 변화) 이원화
- **시각화**: 날짜별 타임라인 + 날짜 필터 기반 리포트 제공
- **자동화**: GitHub Actions 일 1회 수집 + GitHub Pages 자동 배포

## 기술적 우수성

- **혼합 수집기**: RSS와 museum API를 같은 파이프라인에서 처리
- **관찰성**: JSONL raw logging + DuckDB + SQLite FTS5 검색 인덱스
- **복원력**: retry + circuit breaker + source별 오류 격리
- **날짜 기반 검토**: `Date-based review` 섹션에서 날짜별 기사/작품 변화 추적
- **운영 자동화**: GitHub Actions가 `art`와 `artwork` 보고서를 함께 생성

## 빠른 시작

1. 가상환경을 만들고 의존성을 설치합니다.
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

2. 실행:
   ```bash
   python main.py --category art --recent-days 7 --keep-days 90 --generate-report
   python main.py --category artwork --recent-days 30 --keep-days 180 --generate-report
   ```

   생성 결과:
   - `reports/art_report.html`
   - `reports/artwork_report.html`
   - `reports/index.html`

## GitHub Actions & GitHub Pages

- 워크플로: `.github/workflows/radar-crawler.yml`
  - 스케줄: 매일 10:00 UTC (KST 19:00)
  - `art`와 `artwork`를 순차 수집
  - 배포 디렉터리: `reports/` → `gh-pages` 브랜치
  - DuckDB 경로: `data/art_data.duckdb`

- 설정 방법:
  1) 저장소 Settings → Pages에서 `gh-pages` 브랜치를 활성화
  2) Actions가 `contents`, `pages`, `id-token` 권한을 가지는지 확인
  3) Smithsonian 수집이 필요하면 `SMITHSONIAN_API_KEY`를 repository secret/env로 설정

## 동작 방식

- **수집**: `config/categories/art.yaml`, `config/categories/artwork.yaml` 기준으로 소스를 수집합니다.
- **정규화**: 모든 수집 결과를 `Article` 구조로 변환하고 엔티티 키워드를 매칭합니다.
- **저장**: DuckDB upsert + SQLite FTS5 인덱스를 함께 갱신합니다.
- **리포트**: 날짜별 타임라인과 `Date-based review` 필터가 포함된 HTML 보고서를 생성합니다.

## 카테고리 구성

- `art`
  - 목적: 미술 뉴스, 전시, 기관, 시장 변화 추적
  - 소스: RSS 5개 + museum API 3개

- `artwork`
  - 목적: 개별 작품, 소장품, 매체, 컬렉션 변화 추적
  - 소스: museum API 3개

## 기본 경로

- DB: `data/art_data.duckdb`
- 검색 인덱스: `data/search_index.db`
- Raw 로그: `data/raw/`
- 리포트 출력: `reports/`

## 디렉터리 구성

```text
ArtRadar/
  main.py
  config/
    config.yaml
    notifications.yaml
    categories/
      art.yaml
      artwork.yaml
  artradar/
    collector.py
    analyzer.py
    reporter.py
    storage.py
    search_index.py
    config_loader.py
    notifier.py
    raw_logger.py
    mcp_server/
  reports/
  data/
  tests/
  .github/workflows/
```

## 참고

- Smithsonian은 기본적으로 API 키가 있어야 정상 수집됩니다.
- `ArtSelector`는 공식 RSS 피드(`https://www.artselector.com/feed/`) 기반으로 수집합니다.
- 공개 Pages 반영은 `gh-pages` 브랜치 갱신 후 수 분 정도 지연될 수 있습니다.

<!-- DATAHUB-OPS-AUDIT:START -->
## DataHub Operations

- CI/CD workflows: `pr-checks.yml`, `radar-crawler.yml`.
- GitHub Pages visualization: `reports/index.html` (valid HTML); https://ai-frendly-datahub.github.io/ArtRadar/.
- Latest remote Pages check: HTTP 200, HTML.
- Local workspace audit: 46 Python files parsed, 0 syntax errors.
- Re-run audit from the workspace root: `python scripts/audit_ci_pages_readme.py --syntax-check --write`.
- Latest audit report: `_workspace/2026-04-14_github_ci_pages_readme_audit.md`.
- Latest Pages URL report: `_workspace/2026-04-14_github_pages_url_check.md`.
<!-- DATAHUB-OPS-AUDIT:END -->
