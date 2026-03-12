# ARTRADAR

미술 리뷰·전시·기관·시장 관련 소식을 수집·분석하는 레이더. RSS 기반 미술 저널과 미술관 공개 API를 함께 수집하고, 장르·시대·시장·기관·주제 기준으로 엔티티 태깅한다.

## STRUCTURE

```
ArtRadar/
├── artradar/
│   ├── collector.py              # collect_sources() — RSS + museum API mixed collection
│   ├── analyzer.py               # apply_entity_rules() — art keyword matching
│   ├── reporter.py               # generate_report() — Jinja2 HTML
│   ├── storage.py                # RadarStorage — DuckDB upsert/query/retention
│   ├── models.py                 # Source, Article, EntityDefinition, CategoryConfig
│   ├── config_loader.py          # YAML loading
│   ├── logger.py                 # structlog logging
│   ├── notifier.py               # Email/Webhook notifications
│   ├── raw_logger.py             # JSONL raw logging
│   ├── search_index.py           # SQLite FTS5 search
│   ├── nl_query.py               # Natural language query parser
│   ├── resilience.py             # Circuit breaker (pybreaker)
│   ├── exceptions.py             # Custom exception hierarchy
│   ├── common/                   # validators, quality_checks
│   └── mcp_server/               # MCP server (server.py + tools.py)
├── config/
│   ├── config.yaml               # database_path, report_dir, raw_data_dir, search_db_path
│   ├── notifications.yaml        # optional notifications config
│   └── categories/               # art.yaml + artwork.yaml
├── data/                         # DuckDB, search_index.db, raw/ JSONL
├── reports/                      # generated HTML reports
├── tests/
│   ├── unit/
│   └── integration/
├── main.py                       # CLI entrypoint
└── .github/workflows/radar-crawler.yml  # daily 10:00 UTC
```

## ENTITIES

| Entity | Name | Keyword Examples |
|--------|------|------------------|
| `Genre` | 장르 | painting, sculpture, drawing, photography, installation, digital art |
| `Period` | 시대 | renaissance, baroque, impressionism, modernism, contemporary |
| `Market` | 시장 | auction, gallery, collector, provenance, appraisal, art fair |
| `Institution` | 기관 | museum, gallery, biennale, exhibition, curator, restoration |
| `Topic` | 주제 | technique, iconography, art history, exhibition review, art criticism |

## SOURCE MIX

## CATEGORY SPLIT

- `art`: 미술 뉴스/시장/전시/기관 변화 추적 (RSS + museum API 혼합)
- `artwork`: 개별 작품/소장품/컬렉션 변화 추적 (museum API 중심)

## SOURCE MIX

`art` 8개 소스:
- RSS: 월간미술, Artnet News, ARTnews, Artforum, ArtSelector
- API: Metropolitan Museum, Art Institute of Chicago, Smithsonian

`artwork` 3개 소스:
- API: Metropolitan Museum, Art Institute of Chicago, Smithsonian

## DEVIATIONS FROM TEMPLATE

- `collector.py`: RSS와 museum API를 함께 처리하는 mixed-source dispatcher
- `resilience.py`: circuit breaker로 source 장애 격리
- `exceptions.py`: `NetworkError`, `ParseError`, `SourceError` 계층 사용
- Smithsonian API는 `SMITHSONIAN_API_KEY` 필요
- `reporter.py`: 타임라인 + 날짜 필터 기반으로 날짜별 기사 확인 지원
- GitHub Actions는 `art`와 `artwork` 두 카테고리를 매일 순차 수집

## COMMANDS

```bash
python main.py --category art --recent-days 7 --keep-days 90 --generate-report
python main.py --category artwork --recent-days 30 --keep-days 180 --generate-report
pytest tests/unit -m unit
pytest tests/integration -m integration
```
