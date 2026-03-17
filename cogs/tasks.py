"""태스크 관리 슬래시 명령어 Cog."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.notion import NotionTaskService
from utils.cog_base import AliasCog

# 상태 이모지 매핑
STATUS_EMOJI = {"todo": "📋", "doing": "🔨", "done": "✅"}
PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


class TasksCog(AliasCog):
    """칸반보드 스타일 태스크 관리."""

    ALIASES = {
        "작업추가": "task_add",
        "작업목록": "task_list",
        "작업완료": "task_done",
        "작업상태": "task_status",
        "작업수정": "task_edit",
        "작업삭제": "task_delete",
        "도움말": "help",
    }

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notion = NotionTaskService()

    # ── /task add ───────────────────────────────────────────
    @app_commands.command(name="task_add", description="새 태스크 추가")
    @app_commands.describe(
        name="태스크 이름",
        priority="우선순위 (high/medium/low)",
    )
    @app_commands.choices(
        priority=[
            app_commands.Choice(name="🔴 높음", value="high"),
            app_commands.Choice(name="🟡 보통", value="medium"),
            app_commands.Choice(name="🟢 낮음", value="low"),
        ]
    )
    async def task_add(
        self,
        interaction: discord.Interaction,
        name: str,
        priority: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        prio = priority.value if priority else "medium"

        try:
            result = self.notion.create_task(name=name, priority=prio)
            embed = discord.Embed(
                title="✨ 태스크 생성 완료",
                color=0x2ECC71,
            )
            embed.add_field(name="이름", value=result["name"], inline=False)
            embed.add_field(name="ID", value=f"`{result['task_id']}`", inline=True)
            embed.add_field(
                name="우선순위",
                value=f"{PRIORITY_EMOJI.get(prio, '')} {prio}",
                inline=True,
            )
            embed.add_field(name="상태", value="📋 todo", inline=True)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 태스크 생성 실패: {e}")

    # ── /task list ──────────────────────────────────────────
    @app_commands.command(name="task_list", description="태스크 목록 조회")
    @app_commands.describe(status="필터할 상태 (선택)")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="📋 todo", value="todo"),
            app_commands.Choice(name="🔨 doing", value="doing"),
            app_commands.Choice(name="✅ done", value="done"),
        ]
    )
    async def task_list(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        status_val = status.value if status else None

        try:
            tasks = self.notion.list_tasks(status_filter=status_val)
            if not tasks:
                await interaction.followup.send("📭 등록된 태스크가 없습니다.")
                return

            # 상태별로 그룹핑
            grouped: dict[str, list] = {"todo": [], "doing": [], "done": []}
            for t in tasks:
                s = t["status"]
                if s in grouped:
                    grouped[s].append(t)

            embed = discord.Embed(
                title="📊 태스크 보드",
                color=0x3498DB,
            )

            for s in ("doing", "todo", "done"):
                if status_val and s != status_val:
                    continue
                items = grouped.get(s, [])
                if not items:
                    continue

                lines = []
                for t in items[:10]:  # 최대 10개
                    prio = PRIORITY_EMOJI.get(t["priority"], "⚪")
                    lines.append(f"{prio} `{t['task_id']}` {t['name']}")

                emoji = STATUS_EMOJI.get(s, "")
                embed.add_field(
                    name=f"{emoji} {s.upper()} ({len(items)})",
                    value="\n".join(lines) or "없음",
                    inline=False,
                )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 목록 조회 실패: {e}")

    # ── /task done ──────────────────────────────────────────
    @app_commands.command(name="task_done", description="태스크 완료 처리")
    @app_commands.describe(task_id="완료할 태스크 ID")
    async def task_done(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer(thinking=True)

        try:
            result = self.notion.complete_task(task_id.strip())
            if not result:
                await interaction.followup.send(
                    f"❌ `{task_id}` 태스크를 찾을 수 없습니다."
                )
                return

            embed = discord.Embed(
                title="✅ 태스크 완료!",
                description=f"**{result['name']}** (`{task_id}`)",
                color=0x2ECC71,
            )
            embed.set_footer(text="수고했어! 다음 태스크도 화이팅 💪")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 완료 처리 실패: {e}")

    # ── /task status ────────────────────────────────────────
    @app_commands.command(name="task_status", description="태스크 상태 변경")
    @app_commands.describe(task_id="태스크 ID", status="변경할 상태")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="📋 todo", value="todo"),
            app_commands.Choice(name="🔨 doing", value="doing"),
            app_commands.Choice(name="✅ done", value="done"),
        ]
    )
    async def task_status(
        self,
        interaction: discord.Interaction,
        task_id: str,
        status: app_commands.Choice[str],
    ):
        await interaction.response.defer(thinking=True)

        try:
            result = self.notion.update_status(task_id.strip(), status.value)
            if not result:
                await interaction.followup.send(
                    f"❌ `{task_id}` 태스크를 찾을 수 없습니다."
                )
                return

            emoji = STATUS_EMOJI.get(status.value, "")
            embed = discord.Embed(
                title=f"{emoji} 상태 변경 완료",
                description=(
                    f"**{result['name']}** → `{status.value}`"
                ),
                color=0xF39C12,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 상태 변경 실패: {e}")

    # ── /task edit ──────────────────────────────────────────
    @app_commands.command(name="task_edit", description="태스크 수정")
    @app_commands.describe(
        task_id="수정할 태스크 ID",
        name="새 이름 (선택)",
        priority="새 우선순위 (선택)",
    )
    @app_commands.choices(
        priority=[
            app_commands.Choice(name="🔴 높음", value="high"),
            app_commands.Choice(name="🟡 보통", value="medium"),
            app_commands.Choice(name="🟢 낮음", value="low"),
        ]
    )
    async def task_edit(
        self,
        interaction: discord.Interaction,
        task_id: str,
        name: str = None,
        priority: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        prio = priority.value if priority else None

        try:
            result = self.notion.edit_task(
                task_id.strip(), name=name, priority=prio
            )
            if not result:
                await interaction.followup.send(
                    f"❌ `{task_id}` 태스크를 찾을 수 없거나 변경사항이 없습니다."
                )
                return

            embed = discord.Embed(
                title="✏️ 태스크 수정 완료",
                color=0x9B59B6,
            )
            embed.add_field(name="ID", value=f"`{result['task_id']}`", inline=True)
            embed.add_field(name="이름", value=result["name"], inline=True)
            embed.add_field(
                name="우선순위",
                value=f"{PRIORITY_EMOJI.get(result['priority'], '')} {result['priority']}",
                inline=True,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 수정 실패: {e}")

    # ── /task delete ────────────────────────────────────────
    @app_commands.command(name="task_delete", description="태스크 삭제")
    @app_commands.describe(task_id="삭제할 태스크 ID")
    async def task_delete(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer(thinking=True)

        try:
            success = self.notion.delete_task(task_id.strip())
            if not success:
                await interaction.followup.send(
                    f"❌ `{task_id}` 태스크를 찾을 수 없습니다."
                )
                return

            embed = discord.Embed(
                title="🗑️ 태스크 삭제 완료",
                description=f"태스크 `{task_id}` 가 아카이브 처리되었습니다.",
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 삭제 실패: {e}")

    # ── /help ─────────────────────────────────────────────
    @app_commands.command(name="help", description="사용 가능한 명령어 안내")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 TaskMaster 명령어 안내",
            description="사용 가능한 모든 명령어 목록입니다.",
            color=0x3498DB,
        )

        embed.add_field(
            name="📋 태스크 관리",
            value=(
                "`/task_add` — 새 태스크 추가\n"
                "`/task_list` — 태스크 목록 조회 (상태별 필터 가능)\n"
                "`/task_done` — 태스크 완료 처리\n"
                "`/task_status` — 태스크 상태 변경 (todo/doing/done)\n"
                "`/task_edit` — 태스크 이름/우선순위 수정\n"
                "`/task_delete` — 태스크 삭제 (아카이브)"
            ),
            inline=False,
        )

        embed.add_field(
            name="🚨 이슈 관리",
            value=(
                "`/issue_add` — 태스크에 이슈(블로커) 추가\n"
                "`/issue_list` — 이슈 목록 조회 (태스크별 필터 가능)\n"
                "`/issue_done` — 이슈 해결 처리\n"
                "`/issue_delete` — 이슈 삭제 (아카이브)"
            ),
            inline=False,
        )

        embed.add_field(
            name="⏰ 체크인 (사수 모드)",
            value=(
                "`/checkin_start` — 랜덤 간격 체크인 시작\n"
                "`/checkin_stop` — 체크인 중지"
            ),
            inline=False,
        )

        embed.add_field(
            name="📊 리포트",
            value="`/report` — 오늘의 작업 리포트",
            inline=False,
        )

        embed.add_field(
            name="ℹ️ 기타",
            value="`/help` — 이 도움말 표시",
            inline=False,
        )

        embed.set_footer(text="TaskMaster Bot — 사수가 지켜보고 있다 👀")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TasksCog(bot))
