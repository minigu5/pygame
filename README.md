# 메챠 카멜레온 2D

2D 횡스크롤 위장 숨바꼭질 게임. 카멜레온은 몸을 배경색으로 칠해 숨고, 헌터는 방을 뒤져 찾는다.

문서는 `docs/superpowers/specs/`에 있다.

- [기술 설계서](docs/superpowers/specs/2026-09-21-chameleon-design.md) — 서버 구조, 프로토콜, 물리, 배포
- [게임 기획 스펙](docs/superpowers/specs/2026-09-21-meccha-chameleon-2d-game-spec.md) — 맵, 시야, 칠하기, 라운드

## 구조

| 경로 | 내용 |
| --- | --- |
| `client/` | pygame-ce 클라이언트 (Python) |
| `server/` | Cloudflare Workers + Durable Objects 서버 (TypeScript) |
| `shared/` | 맵과 튜닝 값처럼 양쪽이 함께 읽는 데이터 |
| `tools/` | 맵 변환과 점검용 스크립트 |

## 준비

Python 3.13 이상과 Node.js 20 이상이 필요하다.

```sh
python3 -m venv .venv
.venv/bin/pip install -r client/requirements.txt
npm install --prefix server
```

## 실행

서버를 먼저 띄운다.

```sh
npm run dev --prefix server        # http://127.0.0.1:8787
```

클라이언트는 창 하나가 플레이어 한 명이다. 두 명이 필요하므로 터미널 두 개에서 각각 실행한다.

```sh
.venv/bin/python client/main.py --room test
```

먼저 접속한 쪽이 헌터, 다음이 카멜레온이다. `--server`로 다른 주소를 쓸 수 있다.

## 점검

서버가 떠 있는 상태에서 접속과 ping 왕복을 확인한다.

```sh
.venv/bin/python tools/smoke_ws.py
```

## 작업 규칙

기능마다 `feat/<단계>-<내용>` 브랜치를 만들고 PR로 `main`에 합친다. 자세한 내용은 기획 스펙 10절에 있다.
