"""이슈 관리 슬래시 명령어 Cog."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.notion_issue import NotionIssueService, NotionIssueServiceError
from utils.cog_base import AliasCog

# 이슈 상태 이모지 매핑
ISSUE_STATUS_EMOJI = {"보고됨": "🚨", "처리 중": "🔧", "해결됨": "✅"}
SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


class IssuesCog(AliasCog):
    """태스크 하위 이슈 관리."""

    ALIASES = {
        "이슈추가": "issue_add",
        "이슈목록": "issue_list",
        "이슈완료": "issue_done",
        "이슈삭제": "issue_delete",
    }

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notion_issue = NotionIssueService()

    # ── /issue_add ────────────────────────────────────────
    @app_commands.command(name="issue_add", description="태스크에 이슈 추가")
    @app_commands.describe(
        task_id="상위 태스크 ID",
        name="이슈 설명",
        severity="심각도 (high/medium/low)",
    )
    @app_commands.choices(
        severity=[
            app_commands.Choice(name="🔴 높음", value="high"),
            app_commands.Choice(name="🟡 보통", value="medium"),
            app_commands.Choice(name="🟢 낮음", value="low"),
        ]
    )
    async def issue_add(
        self,
        interaction: discord.Interaction,
        task_id: str,
        name: str,
        severity: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        sev = severity.value if severity else "medium"

        try:
            result = self.notion_issue.create_issue(
                parent_task_id=task_id.strip(), name=name, severity=sev
            )
            embed = discord.Embed(
                title="🚨 이슈 등록 완료",
                color=0xE74C3C,
            )
            embed.add_field(name="이름", value=result["name"], inline=False)
            embed.add_field(
                name="이슈 ID", value=f"`{result['issue_id']}`", inline=True
            )
            embed.add_field(
                name="상위 태스크", value=f"`{result['parent_task_id']}`", inline=True
            )
            embed.add_field(
                name="심각도",
                value=f"{SEVERITY_EMOJI.get(sev, '')} {sev}",
                inline=True,
            )
            embed.add_field(name="상태", value="🚨 보고됨", inline=True)
            await interaction.followup.send(embed=embed)
        except NotionIssueServiceError as e:
            err_msg = str(e)
            if "상위 태스크를 찾을 수 없습니다" in err_msg:
                await interaction.followup.send(
                    f"❌ 태스크 `{task_id}`를 찾을 수 없습니다."
                )
            else:
                await interaction.followup.send(f"❌ 이슈 등록 실패: {e}")
        except Exception as e:
            await interaction.followup.send(f"❌ 이슈 등록 실패: {e}")

    # ── /issue_list ───────────────────────────────────────
    @app_commands.command(name="issue_list", description="이슈 목록 조회")
    @app_commands.describe(task_id="상위 태스크 ID (선택, 미입력 시 전체)")
    async def issue_list(
        self,
        interaction: discord.Interaction,
        task_id: str = None,
    ):
        await interaction.response.defer(thinking=True)
        tid = task_id.strip() if task_id else None

        try:
            issues = self.notion_issue.list_issues(parent_task_id=tid)
            if not issues:
                await interaction.followup.send("📭 등록된 이슈가 없습니다.")
                return

            title = f"🚨 태스크 `{tid}` 이슈 목록" if tid else "🚨 이슈 목록"
            embed = discord.Embed(title=title, color=0xE74C3C)

            # 상태별 그룹핑
            grouped: dict[str, list] = {"보고됨": [], "처리 중": [], "해결됨": []}
            for issue in issues:
                s = issue["status"]
                if s in grouped:
                    grouped[s].append(issue)

            for status in ("보고됨", "처리 중", "해결됨"):
                items = grouped.get(status, [])
                if not items:
                    continue

                lines = []
                for item in items[:10]:
                    sev = SEVERITY_EMOJI.get(item["severity"], "⚪")
                    lines.append(
                        f"{sev} `{item['issue_id']}` {item['name']}"
                        f" (← `{item['parent_task_id']}`)"
                    )

                emoji = ISSUE_STATUS_EMOJI.get(status, "")
                embed.add_field(
                    name=f"{emoji} {status} ({len(items)})",
                    value="\n".join(lines) or "없음",
                    inline=False,
                )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 이슈 목록 조회 실패: {e}")

    # ── /issue_done ───────────────────────────────────────
    @app_commands.command(name="issue_done", description="이슈 해결 처리")
    @app_commands.describe(issue_id="해결할 이슈 ID")
    async def issue_done(self, interaction: discord.Interaction, issue_id: str):
        await interaction.response.defer(thinking=True)

        try:
            result = self.notion_issue.resolve_issue(issue_id.strip())
            if not result:
                await interaction.followup.send(
                    f"❌ `{issue_id}` 이슈를 찾을 수 없습니다."
                )
                return

            embed = discord.Embed(
                title="✅ 이슈 해결!",
                description=f"**{result['name']}** (`{issue_id}`)",
                color=0x2ECC71,
            )
            embed.set_footer(text="이슈 해결 완료! 태스크 진행을 계속하자 💪")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 이슈 해결 처리 실패: {e}")

    # ── /issue_delete ─────────────────────────────────────
    @app_commands.command(name="issue_delete", description="이슈 삭제")
    @app_commands.describe(issue_id="삭제할 이슈 ID")
    async def issue_delete(self, interaction: discord.Interaction, issue_id: str):
        await interaction.response.defer(thinking=True)

        try:
            success = self.notion_issue.delete_issue(issue_id.strip())
            if not success:
                await interaction.followup.send(
                    f"❌ `{issue_id}` 이슈를 찾을 수 없습니다."
                )
                return

            embed = discord.Embed(
                title="🗑️ 이슈 삭제 완료",
                description=f"이슈 `{issue_id}` 가 아카이브 처리되었습니다.",
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 이슈 삭제 실패: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IssuesCog(bot))
