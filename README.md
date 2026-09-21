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

서버는 `wss://chameleon.omm.run`에 배포되어 있다. 클라이언트는 창 하나가 플레이어 한 명이므로, 두 명이 같은 방 이름으로 접속한다.

```sh
.venv/bin/python client/main.py --room test
```

두 명이 모이면 라운드가 시작된다. 한 명이 헌터, 나머지가 카멜레온이고, 판이 끝나면 역할을 바꿔 다음 판으로 넘어간다. 방 정원은 4명이다.

| 단계 | 기본 길이 | 카멜레온 | 헌터 |
| --- | --- | --- | --- |
| 숨는 시간 | 60초 | 이동, 고정, 칠하기 | 화면이 가려지고 조작할 수 없음 |
| 찾는 시간 | 120초 | 이동, 고정 | 이동, 지목 |
| 결과 | 5초 | 결과 표시 | 결과 표시 |

시간이 다 갈 때까지 한 명이라도 숨어 있으면 카멜레온이 이기고, 전원이 잡히면 헌터가 이긴다.

방을 처음 여는 사람이 단계 길이를 정할 수 있다. 숨는 시간 5~180초, 찾는 시간 10~600초, 결과 2~30초 범위다.

```sh
.venv/bin/python client/main.py --room "test&hide=20&seek=45"
```

로컬 서버로 개발할 때는 이렇게 한다.

```sh
npm run dev --prefix server                                   # http://127.0.0.1:8787
.venv/bin/python client/main.py --server ws://127.0.0.1:8787
```

## 배포

```sh
npx wrangler deploy --config server/wrangler.jsonc
```

Durable Object에는 위치 힌트를 주지 않는다. 배치는 객체가 처음 만들어질 때 정해지므로, 방을 여는 사람 근처에 잡히게 두는 편이 지역을 찍는 것보다 낫다.

## 조작

| 키 | 카멜레온 | 헌터 |
| --- | --- | --- |
| ←/→, A/D | 이동 | 이동 |
| Space, ↑, W | 점프 | 점프 |
| Tab | 고정 모드 켜기/끄기 | - |
| E | 스포이드 모드 (고정 중에만) | - |
| 마우스 왼쪽 | HSB 슬라이더, 스포이드로 색 찍기 | 지목 (빗나가면 3초 쿨다운) |
| M | 미니맵 확대 | 미니맵 확대 |
| Esc | 종료 | 종료 |

카멜레온은 고정 모드에서만 칠할 수 있다. 화면은 지금 있는 방을 중심에 두고, 방 바깥은 회색으로 죽여 그린다.

## 점검

서버가 떠 있는 상태에서 접속과 ping 왕복을 확인한다.

```sh
.venv/bin/python tools/smoke_ws.py            # 접속, 물리, 방 필터, 도색, 지목
.venv/bin/python tools/check_physics_parity.py  # 클라 예측이 서버와 일치하는지
```

## 작업 규칙

기능마다 `feat/<단계>-<내용>` 브랜치를 만들고 PR로 `main`에 합친다. 자세한 내용은 기획 스펙 10절에 있다.
