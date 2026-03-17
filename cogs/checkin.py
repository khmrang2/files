"""랜덤 간격 체크인 루프 Cog — 사수처럼 진행 상황을 물어보고, 자연어 완료 감지."""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.notion import NotionTaskService
from utils.cog_base import AliasCog

logger = logging.getLogger(__name__)

# 사수 멘트 로테이션
CHECKIN_MESSAGES = [
    "⏰ 시간 됐다. 지금 뭐 하고 있어?",
    "👀 어디까지 했어? 진행 상황 보고해.",
    "🔥 집중하고 있지? 현재 상태 알려줘.",
    "📋 체크인 시간이야. 뭐 하는 중이야?",
    "💪 체크인! 막히는 거 있어?",
    "🎯 진행 상황 공유해봐. 도움 필요한 거 있어?",
    "⚡ 잘 하고 있지? 현재 상태 브리핑해.",
    "🕐 시간이 좀 됐다. 뭐 끝냈어?",
]

# 완료 축하 멘트 로테이션
COMPLETE_RESPONSES = [
    "수고했어! 다음 태스크도 화이팅 💪",
    "잘했어! 이 기세 이어가자 🔥",
    "좋아, 하나 끝냈네! 계속 달려 🚀",
    "오 빠르다! 다음 태스크 가자 ⚡",
    "깔끔하게 처리했네! 💯",
]

# 자연어 완료 감지 키워드
COMPLETION_KEYWORDS = [
    "완료", "했습니다", "했어요", "했어", "했다", "했음",
    "끝났", "끝냈", "끝남", "끝",
    "다했", "다 했", "done", "완",
]


# ── 버튼 UI ──────────────────────────────────────────────


class TaskCompleteButton(discord.ui.Button["TaskCompleteView"]):
    """개별 태스크 완료 버튼."""

    def __init__(self, task: dict, notion: NotionTaskService) -> None:
        super().__init__(
            label=f"✅ {task['name'][:18]}",
            style=discord.ButtonStyle.success,
            custom_id=f"complete_{task['task_id']}",
        )
        self.task = task
        self.notion = notion

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            result = self.notion.complete_task(self.task["task_id"])
        except Exception as e:
            logger.error("버튼 완료 처리 실패: %s", e)
            await interaction.response.send_message(
                f"❌ 완료 처리 중 오류 발생: {e}", ephemeral=True
            )
            return

        if result:
            resp = random.choice(COMPLETE_RESPONSES)
            await interaction.response.send_message(
                f"✅ **{result['name']}** (`{self.task['task_id']}`) 완료!\n{resp}"
            )
            # 버튼 비활성화
            self.disabled = True
            self.label = f"✔ {self.task['name'][:18]}"
            self.style = discord.ButtonStyle.secondary
            await interaction.message.edit(view=self.view)
        else:
            await interaction.response.send_message(
                f"❌ `{self.task['task_id']}` 태스크를 찾을 수 없어.", ephemeral=True
            )


class TaskCompleteView(discord.ui.View):
    """체크인 메시지에 첨부되는 태스크 완료 버튼 묶음."""

    def __init__(self, doing_tasks: list[dict], notion: NotionTaskService) -> None:
        super().__init__(timeout=3600)  # 1시간 후 버튼 만료
        for t in doing_tasks[:5]:
            self.add_item(TaskCompleteButton(t, notion))


class TaskSelectView(discord.ui.View):
    """여러 doing 태스크 중 완료할 태스크를 선택하는 버튼."""

    def __init__(self, doing_tasks: list[dict], notion: NotionTaskService) -> None:
        super().__init__(timeout=120)
        for t in doing_tasks[:5]:
            self.add_item(TaskCompleteButton(t, notion))


# ── Cog ──────────────────────────────────────────────────


class CheckinCog(AliasCog):
    """랜덤 간격(30~60분) 체크인 + 자연어 완료 감지 시스템."""

    ALIASES = {
        "체크인시작": "checkin_start",
        "체크인중지": "checkin_stop",
    }

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notion = NotionTaskService()
        self.channel_id: int | None = None
        self.msg_index = 0

        # 마지막 체크인에서 보여준 doing 태스크 목록
        self.last_doing_tasks: list[dict] = []

        # 랜덤 간격 범위 (분)
        self.min_minutes = int(os.getenv("CHECKIN_MIN_MINUTES", "30"))
        self.max_minutes = int(os.getenv("CHECKIN_MAX_MINUTES", "60"))

        # 우선순위 알림 기준 (시간)
        self.priority_alert_hours = int(os.getenv("PRIORITY_ALERT_HOURS", "24"))

        # 환경변수에서 기본 채널 설정
        default_ch = os.getenv("CHECKIN_CHANNEL_ID")
        if default_ch:
            self.channel_id = int(default_ch)

    def cog_unload(self) -> None:
        self.checkin_loop.cancel()
        super().cog_unload()

    # ── 체크인 루프 ────────────────────────────────────────
    @tasks.loop(minutes=30)
    async def checkin_loop(self):
        if not self.channel_id:
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        # 현재 진행 중인 태스크 가져오기
        try:
            doing_tasks = self.notion.get_in_progress()
        except Exception as e:
            logger.error("체크인 중 Notion 조회 실패: %s", e)
            doing_tasks = []

        # 마지막 doing 태스크 저장 (자연어 감지용)
        self.last_doing_tasks = doing_tasks

        # 사수 멘트 선택
        msg = CHECKIN_MESSAGES[self.msg_index % len(CHECKIN_MESSAGES)]
        self.msg_index += 1

        embed = discord.Embed(
            title="📢 체크인 타임",
            description=msg,
            color=0xE67E22,
        )

        view = None
        if doing_tasks:
            task_lines = []
            for t in doing_tasks[:5]:
                task_lines.append(f"• `{t['task_id']}` {t['name']}")
            embed.add_field(
                name="🔨 현재 진행 중인 태스크",
                value="\n".join(task_lines),
                inline=False,
            )
            embed.set_footer(
                text="버튼을 누르거나 '완료했습니다'라고 말해도 돼!"
            )
            # 완료 버튼 첨부
            view = TaskCompleteView(doing_tasks, self.notion)
        else:
            embed.add_field(
                name="📭 진행 중인 태스크 없음",
                value="할 일이 있으면 `/task_add`로 추가하고 시작해!",
                inline=False,
            )

        await channel.send(embed=embed, view=view)

        # ── 우선순위 알림: 방치된 긴급 태스크 경고 ──────────
        try:
            stale_tasks = self.notion.get_stale_high_priority(
                max_hours=self.priority_alert_hours
            )
        except Exception as e:
            logger.error("우선순위 알림 조회 실패: %s", e)
            stale_tasks = []

        if stale_tasks:
            alert_embed = discord.Embed(
                title="🚨 방치된 긴급 태스크 경고",
                description=(
                    f"다음 **HIGH** 우선순위 태스크가 "
                    f"{self.priority_alert_hours}시간 이상 방치되고 있어!"
                ),
                color=0xE74C3C,
            )
            for t in stale_tasks[:5]:
                status_emoji = {"시작 전": "📋", "진행 중": "🔨"}.get(t["status"], "")
                if t.get("status_changed_at"):
                    try:
                        changed = datetime.fromisoformat(
                            t["status_changed_at"].replace("Z", "+00:00")
                        )
                        delta = datetime.now(timezone.utc) - changed
                        hours = int(delta.total_seconds() // 3600)
                        stale_text = f"{hours}시간 경과"
                    except ValueError:
                        stale_text = "시간 불명"
                else:
                    stale_text = "시간 불명"

                alert_embed.add_field(
                    name=f"{status_emoji} `{t['task_id']}` {t['name']}",
                    value=f"상태: **{t['status']}** | {stale_text}",
                    inline=False,
                )
            alert_embed.set_footer(
                text="긴급 태스크를 먼저 처리해! 완료하려면 /task_done <id>"
            )
            await channel.send(embed=alert_embed)

        # 다음 체크인 간격을 랜덤으로 변경
        next_interval = random.randint(self.min_minutes, self.max_minutes)
        self.checkin_loop.change_interval(minutes=next_interval)
        logger.info("다음 체크인: %d분 후", next_interval)

    @checkin_loop.before_loop
    async def before_checkin(self):
        await self.bot.wait_until_ready()

    # ── 자연어 완료 감지 ─────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # 봇 자신의 메시지 무시
        if message.author.bot:
            return

        # 체크인 채널에서만 감지
        if message.channel.id != self.channel_id:
            return

        # 체크인이 실행 중일 때만
        if not self.checkin_loop.is_running():
            return

        content = message.content.lower().strip()
        if not content:
            return

        # 완료 키워드 매칭
        has_completion = any(kw in content for kw in COMPLETION_KEYWORDS)
        if not has_completion:
            return

        # 현재 doing 태스크 목록 갱신
        try:
            doing_tasks = self.notion.get_in_progress()
        except Exception as e:
            logger.error("자연어 감지 중 Notion 조회 실패: %s", e)
            return

        if not doing_tasks:
            await message.reply("📭 현재 진행 중인 태스크가 없어!")
            return

        # 메시지에서 태스크 ID 또는 이름 매칭 시도
        matched_task = self._find_task_in_message(content, doing_tasks)

        if matched_task:
            # 특정 태스크 매칭됨 → 바로 완료
            await self._complete_and_respond(message, matched_task)
        elif len(doing_tasks) == 1:
            # doing 태스크가 1개 → 자동 완료
            await self._complete_and_respond(message, doing_tasks[0])
        else:
            # doing 태스크가 여러 개 → 선택 요청
            embed = discord.Embed(
                title="🤔 어떤 태스크를 완료했어?",
                description="여러 태스크가 진행 중이야. 완료한 걸 골라줘!",
                color=0xF39C12,
            )
            view = TaskSelectView(doing_tasks, self.notion)
            await message.reply(embed=embed, view=view)

    def _find_task_in_message(
        self, content: str, doing_tasks: list[dict]
    ) -> dict | None:
        """메시지에서 태스크 ID 또는 이름을 찾아 매칭."""
        # 1. 태스크 ID로 매칭 (예: "a3f2k 완료")
        for t in doing_tasks:
            if t["task_id"].lower() in content:
                return t

        # 2. 태스크 이름으로 매칭 (예: "API 설계 완료했습니다")
        for t in doing_tasks:
            task_name = t["name"].lower()
            # 이름이 3글자 이상이고 메시지에 포함되어 있으면 매칭
            if len(task_name) >= 3 and task_name in content:
                return t

        return None

    async def _complete_and_respond(
        self, message: discord.Message, task: dict
    ) -> None:
        """태스크를 완료하고 사수 스타일 응답."""
        try:
            result = self.notion.complete_task(task["task_id"])
        except Exception as e:
            logger.error("자연어 완료 처리 실패: %s", e)
            await message.reply(f"❌ 완료 처리 중 오류가 발생했어: {e}")
            return

        if result:
            resp = random.choice(COMPLETE_RESPONSES)
            embed = discord.Embed(
                title="✅ 태스크 완료!",
                description=f"**{result['name']}** (`{task['task_id']}`)",
                color=0x2ECC71,
            )
            embed.set_footer(text=resp)
            await message.reply(embed=embed)

            # last_doing_tasks 갱신
            self.last_doing_tasks = [
                t for t in self.last_doing_tasks
                if t["task_id"] != task["task_id"]
            ]
        else:
            await message.reply(f"❌ `{task['task_id']}` 태스크를 찾을 수 없어.")

    # ── /checkin start ──────────────────────────────────────
    @app_commands.command(
        name="checkin_start",
        description="사수 모드 시작 (랜덤 간격 체크인)",
    )
    async def checkin_start(self, interaction: discord.Interaction):
        self.channel_id = interaction.channel_id

        if self.checkin_loop.is_running():
            await interaction.response.send_message("⚠️ 이미 체크인이 실행 중이야!")
            return

        self.checkin_loop.start()

        embed = discord.Embed(
            title="🚀 체크인 모드 시작",
            description=(
                f"{self.min_minutes}~{self.max_minutes}분 랜덤 간격으로 "
                f"이 채널에서 진행 상황을 물어볼게.\n"
                "사수가 지켜보고 있다 생각해. 집중해! 🔥\n\n"
                "💡 **팁**: 체크인 메시지에 '완료했습니다'라고 답하면\n"
                "자동으로 태스크를 완료 처리해줘!"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text="중지하려면 /checkin_stop")
        await interaction.response.send_message(embed=embed)

    # ── /checkin stop ───────────────────────────────────────
    @app_commands.command(name="checkin_stop", description="체크인 중지")
    async def checkin_stop(self, interaction: discord.Interaction):
        if not self.checkin_loop.is_running():
            await interaction.response.send_message("⚠️ 체크인이 실행 중이 아니야.")
            return

        self.checkin_loop.cancel()
        self.last_doing_tasks = []

        embed = discord.Embed(
            title="⏸️ 체크인 중지",
            description="수고했어! 체크인을 중지했어. 쉬어가자 ☕",
            color=0x95A5A6,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CheckinCog(bot))
