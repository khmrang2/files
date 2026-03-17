# TaskMaster Bot — 프로젝트 계획 및 개발 기록

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | TaskMaster Bot |
| 유형 | Discord 기반 일정 관리 & 업무 감독 봇 |
| 핵심 컨셉 | "디스코드 사수 봇" — 랜덤 간격으로 진행 상황을 물어보며 업무 집중도를 높이는 자동화 도구 |
| 기술 스택 | Python 3.10+, discord.py 2.3+, Notion API (notion-client 3.0), python-dotenv |
| 외부 서비스 | Discord Bot API, Notion Database API |
| 아키텍처 | Cog 기반 모듈화 + Service Layer 패턴 |

### 기획 의도

개인 또는 소규모 팀 환경에서 태스크를 관리할 때, 별도의 프로젝트 관리 도구를 열어 확인하는 번거로움이 있다. Discord라는 이미 사용 중인 커뮤니케이션 플랫폼 안에서 **Notion 칸반보드와 연동된 태스크 관리**, **랜덤 간격 체크인을 통한 업무 감독**, **자연어 기반 태스크 완료 처리**를 결합하여 업무 흐름을 끊지 않는 생산성 도구를 구현했다.

---

## 2. 시스템 아키텍처

```
┌──────────────────────────────────────────────────────┐
│                    Discord Server                     │
│  사용자 ──▶ 슬래시 명령어 / 자연어 메시지 / 버튼 클릭  │
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                  TaskMaster Bot (bot.py)              │
│                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐   │
│  │  TasksCog    │ │ CheckinCog  │ │  ReportCog   │   │
│  │  태스크 CRUD │ │ 체크인 루프  │ │  일일 리포트  │   │
│  │  /help      │ │ 자연어 감지  │ │              │   │
│  └──────┬──────┘ │ 버튼 UI     │ └──────┬───────┘   │
│         │        └──────┬──────┘        │           │
│  ┌──────┴──────┐        │        ┌──────┴───────┐   │
│  │ IssuesCog   │        │        │              │   │
│  │ 이슈 CRUD   │        │        │              │   │
│  └──────┬──────┘        │        │              │   │
│         │               │        │              │   │
│  ┌──────▼───────────────▼────────▼──────────┐   │   │
│  │            Service Layer                  │   │   │
│  │  NotionTaskService  │ NotionIssueService  │   │   │
│  └──────────────────────┬────────────────────┘   │   │
│                         │                        │   │
│  ┌──────────────────────▼────────────────────┐   │   │
│  │         Utils (id_gen, cog_base)          │   │   │
│  └───────────────────────────────────────────┘   │   │
└──────────────────────────┬───────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│                   Notion API                         │
│  ┌─────────────────┐   ┌──────────────────┐         │
│  │  Task Database   │◄──│  Issue Database   │         │
│  │  (칸반보드)      │ relation  (하위 이슈)  │         │
│  └─────────────────┘   └──────────────────┘         │
└──────────────────────────────────────────────────────┘
```

### 프로젝트 디렉토리 구조

```
taskmaster-bot/
├── bot.py                    # 엔트리포인트, Cog 로딩, 핫 리로드
├── cogs/
│   ├── tasks.py              # 태스크 CRUD 슬래시 명령어 + /help
│   ├── issues.py             # 이슈 CRUD 슬래시 명령어
│   ├── checkin.py            # 랜덤 체크인 루프 + 자연어 완료 감지
│   └── report.py             # 일일 작업 리포트
├── services/
│   ├── notion.py             # Notion Task DB API 래퍼
│   └── notion_issue.py       # Notion Issue DB API 래퍼
├── utils/
│   ├── id_gen.py             # 랜덤 5자 ID 생성
│   └── cog_base.py           # 한/영 명령어 별칭 자동 등록 베이스 클래스
├── .env                      # 환경 변수 (토큰, DB ID)
├── requirements.txt
├── README.md
└── PROJECT.MD                # 본 문서
```

---

## 3. 핵심 기능 상세

### 3-1. 태스크 관리 (Notion 칸반보드 연동)

Discord 슬래시 명령어로 Notion 데이터베이스의 태스크를 CRUD 조작한다.

| 명령어 | 기능 | Notion API 호출 |
|--------|------|-----------------|
| `/task_add <이름> [우선순위]` | 태스크 생성 | `pages.create()` |
| `/task_list [상태]` | 상태별 그룹핑 목록 | `data_sources.query()` |
| `/task_done <id>` | 완료 처리 | `pages.update()` — Status, CompletedAt |
| `/task_status <id> <상태>` | 상태 변경 | `pages.update()` — Status, StatusChangedAt |
| `/task_edit <id> [이름] [우선순위]` | 수정 | `pages.update()` |
| `/task_delete <id>` | 아카이브 | `pages.update(archived=True)` |

**Notion Task DB 스키마:**

| 속성 | 타입 | 용도 |
|------|------|------|
| Name | title | 태스크 이름 |
| Status | status | 시작 전 / 진행 중 / 완료 |
| Priority | rich_text | high / medium / low |
| TaskID | rich_text | 자동 생성 5자 고유 ID |
| CreatedAt | date | 생성 시각 |
| CompletedAt | date | 완료 시각 |
| StatusChangedAt | date | 마지막 상태 변경 시각 |

**설계 포인트:**
- Notion의 `status` 타입과 `rich_text` 타입을 구분하여 API 호출 포맷을 정확히 매칭
- `notion-client` v3.0에서 `databases.query()` 제거에 대응하여 `data_sources.query()` 사용
- 모든 API 호출에 `APIResponseError` + 범용 예외 이중 처리로 안정성 확보

### 3-2. 이슈 관리 (태스크 하위 블로커 트래킹)

태스크 진행 중 발생하는 블로커/문제를 별도 Notion DB로 관리한다.

| 명령어 | 기능 |
|--------|------|
| `/issue_add <task_id> <이름> [심각도]` | 상위 태스크에 이슈 등록 |
| `/issue_list [task_id]` | 이슈 목록 (태스크별 필터 가능) |
| `/issue_done <issue_id>` | 이슈 해결 처리 |
| `/issue_delete <issue_id>` | 이슈 아카이브 |

**Notion Issue DB 스키마:**

| 속성 | 타입 | 용도 |
|------|------|------|
| Name | title | 이슈 설명 |
| IssueID | rich_text | 자동 생성 5자 고유 ID |
| ParentTask | **relation** | Task DB와 연결 (Notion에서 클릭 시 상위 태스크로 이동) |
| ParentTaskID | rich_text | 상위 태스크 ID 텍스트 (Discord 표시 & API 필터용) |
| Status | status | 보고됨 / 처리 중 / 해결됨 |
| Severity | rich_text | high / medium / low |
| CreatedAt | date | 생성 시각 |
| ResolvedAt | date | 해결 시각 |

**설계 포인트:**
- **Relation + rich_text 이중 저장**: Notion UI에서는 `ParentTask` relation으로 상위 태스크 하이퍼링크 이동, Discord 봇에서는 `ParentTaskID` 텍스트로 빠른 필터/표시
- 이슈 생성 시 상위 태스크 존재 여부를 Task DB에 쿼리하여 **선검증 후 생성** — 잘못된 task_id로 고아 이슈가 생기는 것을 방지
- `NotionIssueService`를 `NotionTaskService`와 별도 클래스로 분리하여 단일 책임 원칙 준수

### 3-3. 랜덤 간격 체크인 시스템 (사수 모드)

30~60분 사이 랜덤 간격으로 체크인 메시지를 보내 업무 집중도를 높인다.

**동작 흐름:**
```
/checkin_start
    │
    ▼
[30~60분 랜덤 대기]
    │
    ▼
📢 체크인 메시지 전송
├── 현재 진행 중인 태스크 목록 표시
├── 태스크별 완료 버튼 (discord.ui.Button) 첨부
├── 방치된 긴급 태스크 경고 (24시간+ HIGH 우선순위)
│
├── [사용자 버튼 클릭] → 즉시 태스크 완료 처리
├── [사용자 자연어 응답] → 완료 키워드 감지 → 자동 완료
│   ├── 태스크 1개 → 자동 완료
│   ├── 태스크 여러 개 + ID 포함 → 해당 태스크 완료
│   └── 태스크 여러 개 + ID 미포함 → 선택 버튼 표시
│
└── 다음 간격 랜덤 설정 → 반복
```

**자연어 완료 감지 키워드:** `완료`, `했습니다`, `했어요`, `했어`, `했다`, `했음`, `끝났`, `끝냈`, `done` 등 14개

**기술 구현:**
- `discord.ext.tasks.loop` + `change_interval()`로 매 루프마다 랜덤 간격 재설정
- `discord.ui.View` / `discord.ui.Button`으로 인터랙티브 UI 구현
- `@commands.Cog.listener()` — `on_message` 이벤트로 자연어 메시지 실시간 감지
- 버튼 클릭 후 `self.disabled = True`로 비활성화하여 중복 완료 방지

### 3-4. 일일 작업 리포트

`/report` 명령어로 오늘의 작업 현황을 시각적으로 요약한다.

**리포트 내용:**
- 전체 진행률 바 (`█░░░░░░░░░ 10%`)
- 상태별 태스크 카운트 (Todo / Doing / Done)
- 오늘 완료한 태스크 목록 (최대 10건)
- 현재 진행 중인 태스크 목록 (최대 5건)
- 진행률 기반 동기부여 메시지 (0%/50%/80% 분기)

### 3-5. 한/영 명령어 별칭 시스템

`AliasCog` 베이스 클래스를 통해 모든 영문 명령어에 한글 별칭을 자동 등록한다.

```python
class TasksCog(AliasCog):
    ALIASES = {
        "작업추가": "task_add",
        "작업목록": "task_list",
        ...
    }
```

- `cog_load` 시 원본 커맨드를 `deepcopy`하여 별칭 이름으로 커맨드 트리에 추가
- `cog_unload` 시 별칭 자동 제거 — 핫 리로드에도 안전

### 3-6. 핫 리로드

`/reload` 관리자 명령어로 서버 재시작 없이 코드 변경사항을 즉시 반영한다.

- `importlib.reload()`로 `services/`, `utils/` 모듈 갱신
- `bot.reload_extension()`으로 모든 Cog 리로드
- 슬래시 명령어 재동기화까지 자동 수행

---

## 4. 기술적 챌린지 및 해결 과정

### 4-1. Notion API 스키마 불일치 문제

**문제:** Notion의 `Status` 속성이 `select` 타입이 아닌 빌트인 `status` 타입이었고, `Priority`는 `rich_text` 타입이었다. API 호출 포맷이 완전히 달라 생성/필터/조회 모두 실패.

**해결:**
- Status: `{"select": {"name": "..."}}` → `{"status": {"name": "..."}}`
- Priority: `{"select": {"name": "..."}}` → `{"rich_text": [{"text": {"content": "..."}}]}`
- 필터도 각 타입에 맞게 전환 — `status.equals`, `rich_text.equals`
- `_extract_status()` 헬퍼를 별도 구현하여 status 타입 파싱 처리

### 4-2. notion-client v3.0 Breaking Change

**문제:** `notion-client` v3.0에서 `databases.query()` 메서드가 제거됨. 기존 코드가 모두 동작 불가.

**해결:** 라이브러리 소스코드를 분석하여 v3에서 제공하는 `data_sources.query()` API로 전환. 동일한 filter/sort 파라미터 구조를 유지하면서 호출 경로만 변경.

### 4-3. 자연어 완료 감지의 모호성 처리

**문제:** 사용자가 "완료했습니다"라고 말했을 때, 진행 중인 태스크가 여러 개면 어떤 태스크인지 특정할 수 없음.

**해결:** 3단계 매칭 전략 구현:
1. 메시지에 태스크 ID 포함 여부 확인 → 해당 태스크 완료
2. 메시지에 태스크 이름(3자 이상) 포함 여부 확인 → 해당 태스크 완료
3. 매칭 실패 시: doing 태스크 1개면 자동 완료, 여러 개면 선택 버튼 UI 표시

### 4-4. Issue-Task 관계 설계

**문제:** 이슈와 태스크의 연결을 Notion에서 시각적으로 확인 가능하면서도, Discord 봇에서 효율적으로 필터링할 수 있어야 함.

**해결:** Notion `relation` 속성과 `rich_text` 속성을 이중 저장:
- `ParentTask` (relation): Notion UI에서 클릭하면 상위 태스크 페이지로 바로 이동
- `ParentTaskID` (rich_text): Discord 봇에서 `rich_text.equals` 필터로 빠른 조회

---

## 5. 전체 명령어 목록

| 카테고리 | 명령어 | 한글 별칭 | 설명 |
|----------|--------|-----------|------|
| 태스크 | `/task_add` | `/작업추가` | 새 태스크 추가 |
| 태스크 | `/task_list` | `/작업목록` | 태스크 목록 조회 (상태별 필터) |
| 태스크 | `/task_done` | `/작업완료` | 태스크 완료 처리 |
| 태스크 | `/task_status` | `/작업상태` | 상태 변경 (시작 전/진행 중/완료) |
| 태스크 | `/task_edit` | `/작업수정` | 이름/우선순위 수정 |
| 태스크 | `/task_delete` | `/작업삭제` | 태스크 삭제 (아카이브) |
| 이슈 | `/issue_add` | `/이슈추가` | 태스크에 이슈 등록 |
| 이슈 | `/issue_list` | `/이슈목록` | 이슈 목록 조회 |
| 이슈 | `/issue_done` | `/이슈완료` | 이슈 해결 처리 |
| 이슈 | `/issue_delete` | `/이슈삭제` | 이슈 삭제 |
| 체크인 | `/checkin_start` | `/체크인시작` | 랜덤 간격 체크인 시작 |
| 체크인 | `/checkin_stop` | `/체크인중지` | 체크인 중지 |
| 리포트 | `/report` | `/리포트` | 오늘의 작업 리포트 |
| 기타 | `/help` | `/도움말` | 명령어 안내 |
| 관리 | `/reload` | — | Cog/서비스 핫 리로드 (관리자) |

---

## 6. 개발 진행 기록

### Phase 1: 기본 구조 구축
- Discord 봇 엔트리포인트 (`bot.py`) 및 Cog 로딩 시스템 구현
- Notion API 래퍼 서비스 (`NotionTaskService`) 설계 및 구현
- 태스크 CRUD 슬래시 명령어 전체 구현 (`/task_add`, `/task_list`, `/task_done`, `/task_status`, `/task_edit`, `/task_delete`)
- 랜덤 5자 ID 생성 유틸리티 구현
- `/help` 명령어로 전체 명령어 가이드 제공

### Phase 2: 체크인 시스템 & 자동화
- 랜덤 간격(30~60분) 체크인 루프 구현 — `tasks.loop` + `change_interval()`
- 체크인 메시지에 진행 중 태스크 목록 + 완료 버튼 UI 첨부
- 자연어 완료 감지 시스템 구현 — `on_message` 리스너 + 키워드 매칭
- 방치된 긴급(HIGH) 태스크 자동 경고 알림 구현
- 일일 작업 리포트 (`/report`) 구현 — 진행률 바, 상태별 카운트, 동기부여 메시지

### Phase 3: 버그 수정 & API 호환성
- Notion DB 스키마 불일치 해결 (Status → status 타입, Priority → rich_text 타입)
- `notion-client` v3.0 Breaking Change 대응 (`databases.query()` → `data_sources.query()`)
- 환경 변수 검증 강화 및 에러 핸들링 체계화

### Phase 4: 이슈 관리 & 확장
- 별도 Notion Issue DB 설계 (Relation 속성으로 태스크 하이퍼링크 연결)
- `NotionIssueService` 구현 — 상위 태스크 검증 + 이슈 CRUD
- 이슈 슬래시 명령어 구현 (`/issue_add`, `/issue_list`, `/issue_done`, `/issue_delete`)
- `AliasCog` 베이스 클래스로 한/영 명령어 별칭 자동화
- `/reload` 핫 리로드 명령어 구현

---

## 7. 사용 기술 요약

| 영역 | 기술 | 활용 |
|------|------|------|
| 런타임 | Python 3.10+ | async/await, type hints, `match` 표현식 |
| Discord | discord.py 2.3+ | 슬래시 명령어, Cog, tasks.loop, ui.View/Button, Embed |
| 외부 API | Notion API (notion-client 3.0) | 데이터베이스 CRUD, Relation, Status/RichText 속성 |
| 설정 관리 | python-dotenv | 환경 변수 기반 설정 분리 |
| 아키텍처 | Service Layer + Cog 패턴 | 비즈니스 로직(Service)과 UI 로직(Cog) 분리 |
| 에러 처리 | 커스텀 예외 + 이중 try/except | API 오류와 예상치 못한 오류를 구분하여 사용자에게 명확한 피드백 |
