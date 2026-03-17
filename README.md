# 🔥 TaskMaster Bot — Discord 일정 관리 & 사수 봇

랜덤 간격(30~60분)으로 진행 상황을 물어보는 **디스코드 사수 봇**입니다.
Notion 칸반보드와 연동하여 태스크를 관리합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| `/task_add` | 새 태스크 추가 (Notion에 자동 생성) |
| `/task_list` | 현재 태스크 목록 조회 (상태별 필터) |
| `/task_done <id>` | 태스크 완료 처리 |
| `/task_status <id> <상태>` | 상태 변경 (todo/doing/done) |
| `/task_edit <id>` | 태스크 이름/우선순위 수정 |
| `/task_delete <id>` | 태스크 삭제 (아카이브) |
| `/issue_add <task_id> <이름>` | 태스크에 이슈(블로커) 추가 |
| `/issue_list [task_id]` | 이슈 목록 조회 (태스크별 필터 가능) |
| `/issue_done <issue_id>` | 이슈 해결 처리 |
| `/issue_delete <issue_id>` | 이슈 삭제 (아카이브) |
| `/checkin_start` | 랜덤 간격 체크인 시작 (사수 모드) |
| `/checkin_stop` | 체크인 중지 |
| `/report` | 오늘의 작업 리포트 |
| `/help` | 사용 가능한 명령어 안내 |

### 추가 기능

- **랜덤 체크인 간격**: 30~60분 사이 랜덤으로 체크인하여 예측 불가한 사수 느낌
- **우선순위 알림**: HIGH 우선순위 태스크가 24시간+ 방치되면 자동 경고

## 사전 준비

### 1. Discord Bot 생성
1. [Discord Developer Portal](https://discord.com/developers/applications) 접속
2. **New Application** → 이름 입력 → 생성
3. **Bot** 탭 → **Add Bot**
4. **TOKEN** 복사 → `.env`에 저장
5. **Privileged Gateway Intents** 에서 `Message Content Intent` 활성화
6. **OAuth2 → URL Generator** 에서:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`
   - 생성된 URL로 서버에 봇 초대

### 2. Notion Integration 생성
1. [Notion Developers](https://developers.notion.com/) 접속
2. **New Integration** → 이름 입력 → 생성
3. **Internal Integration Token** 복사 → `.env`에 저장
4. Notion에서 **새 데이터베이스** 생성 (아래 속성 필요):
   - `Name` (title) — 태스크 이름
   - `Status` (select) — 옵션: `todo`, `doing`, `done`
   - `Priority` (select) — 옵션: `high`, `medium`, `low`
   - `TaskID` (rich_text) — 자동 생성되는 짧은 ID
   - `CreatedAt` (date) — 생성일
   - `CompletedAt` (date) — 완료일
   - `StatusChangedAt` (date) — 상태 변경 시각 (우선순위 알림용)
5. **Issue 데이터베이스** 별도 생성 (아래 속성 필요):
   - `Name` (title) — 이슈 설명
   - `IssueID` (rich_text) — 자동 생성 ID
   - `ParentTask` (relation) — Task DB와 연결 (클릭 시 상위 태스크로 이동)
   - `ParentTaskID` (rich_text) — 상위 태스크 ID (텍스트)
   - `Status` (status) — 옵션: `보고됨`, `처리 중`, `해결됨`
   - `Severity` (rich_text) — `high`, `medium`, `low`
   - `CreatedAt` (date) — 생성일
   - `ResolvedAt` (date) — 해결일
6. 두 데이터베이스 모두 **⋯ → 연결 추가** → 생성한 Integration 연결
7. 데이터베이스 URL에서 ID 추출:
   - `https://notion.so/YOUR_WORKSPACE/DATABASE_ID?v=...`
   - `DATABASE_ID` 부분 복사 → `.env`에 저장 (Task DB, Issue DB 각각)

### 3. 환경 변수 설정

`.env` 파일을 생성하고 아래 값을 입력:

```env
# Discord
DISCORD_TOKEN=your_bot_token
DISCORD_GUILD_ID=your_guild_id

# Notion
NOTION_TOKEN=your_notion_token
NOTION_DATABASE_ID=your_task_database_id
NOTION_DATASOURCE_ID=your_task_datasource_id

# Notion Issue DB
NOTION_ISSUE_DATABASE_ID=your_issue_database_id
NOTION_ISSUE_DATASOURCE_ID=your_issue_datasource_id

# Checkin Settings (랜덤 간격 범위, 분)
CHECKIN_MIN_MINUTES=30
CHECKIN_MAX_MINUTES=60
CHECKIN_CHANNEL_ID=your_channel_id

# Priority Alert (긴급 태스크 방치 경고 기준, 시간)
PRIORITY_ALERT_HOURS=24
```

### 4. 설치 및 실행

```bash
pip install -r requirements.txt
python bot.py
```

## 프로젝트 구조

```
taskmaster-bot/
├── bot.py              # 메인 봇 엔트리포인트
├── cogs/
│   ├── tasks.py        # /task 명령어 그룹 + /help
│   ├── issues.py       # /issue 명령어 그룹
│   ├── checkin.py      # 랜덤 간격 체크인 + 우선순위 알림
│   └── report.py       # /report 명령어
├── services/
│   ├── notion.py       # Notion Task API 래퍼
│   └── notion_issue.py # Notion Issue API 래퍼
├── utils/
│   └── id_gen.py       # 짧은 태스크 ID 생성
├── .env
├── requirements.txt
└── README.md
```
