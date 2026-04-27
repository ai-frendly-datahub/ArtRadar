# Data Quality Plan

- 생성 시각: `2026-04-11T16:05:37.910248+00:00`
- 우선순위: `P2`
- 데이터 품질 점수: `79`
- 가장 약한 축: `운영 깊이`
- Governance: `low`
- Primary Motion: `intelligence`

## 현재 이슈

- 가장 약한 품질 축은 운영 깊이(45)

## 필수 신호

- 경매 낙찰가와 추정가·낙찰일
- 전시 티켓 판매·관람객·아트페어 참가사
- 작가·갤러리·기관의 canonical entity

## 품질 게이트

- 작가명·작품명·제작연도 alias를 분리 관리
- 전시 기사와 거래/판매 신호를 별도 레이어로 유지
- 낙찰가 통화와 수수료 포함 여부를 명시

## 다음 구현 순서

- 경매 낙찰가와 아트페어 참가사 source를 운영 레이어로 추가
- 작가/기관 canonicalization rule을 보강
- 전시 coverage와 거래 신호를 분리한 market score를 추가

## 운영 규칙

- 원문 URL, 수집일, 이벤트 발생일은 별도 필드로 유지한다.
- 공식 source와 커뮤니티/시장 source를 같은 신뢰 등급으로 병합하지 않는다.
- collector가 인증키나 네트워크 제한으로 skip되면 실패를 숨기지 말고 skip 사유를 기록한다.
- 이 문서는 `scripts/build_data_quality_review.py --write-repo-plans`로 재생성한다.
