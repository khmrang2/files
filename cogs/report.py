"""일일 작업 리포트 Cog."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.notion import NotionTaskService
from utils.cog_base import AliasCog

STATUS_EMOJI = {"시작 전": "📋", "진행 중": "🔨", "완료": "✅"}


class ReportCog(AliasCog):
    """오늘의 작업 현황 리포트."""

    ALIASES = {
        "리포트": "report",
    }

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.notion = NotionTaskService()

    @app_commands.command(name="report", description="오늘의 작업 리포트")
    async def report(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        try:
            all_tasks = self.notion.list_tasks()
            completed_today = self.notion.get_today_completed()

            # 상태별 카운트
            counts = {"시작 전": 0, "진행 중": 0, "완료": 0}
            for t in all_tasks:
                s = t["status"]
                if s in counts:
                    counts[s] += 1

            total = sum(counts.values())
            done_pct = (counts["done"] / total * 100) if total > 0 else 0

            embed = discord.Embed(
                title="📊 오늘의 작업 리포트",
                color=0x3498DB,
            )

            # 전체 현황 바
            bar_len = 20
            filled = int(done_pct / 100 * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            embed.add_field(
                name="전체 진행률",
                value=f"`{bar}` {done_pct:.0f}%",
                inline=False,
            )

            # 상태별 카운트
            status_text = (
                f"📋 **Todo**: {counts['시작 전']}  |  "
                f"🔨 **Doing**: {counts['진행 중']}  |  "
                f"✅ **Done**: {counts['완료']}"
            )
            embed.add_field(name="상태별 현황", value=status_text, inline=False)

            # 오늘 완료한 태스크
            if completed_today:
                lines = [
                    f"✅ `{t['task_id']}` {t['name']}"
                    for t in completed_today[:10]
                ]
                embed.add_field(
                    name=f"🎉 오늘 완료 ({len(completed_today)}건)",
                    value="\n".join(lines),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="오늘 완료",
                    value="아직 완료한 태스크가 없어. 화이팅! 💪",
                    inline=False,
                )

            # 진행 중 태스크
            doing = [t for t in all_tasks if t["status"] == "doing"]
            if doing:
                lines = [
                    f"🔨 `{t['task_id']}` {t['name']}" for t in doing[:5]
                ]
                embed.add_field(
                    name="🔨 현재 진행 중",
                    value="\n".join(lines),
                    inline=False,
                )

            # 동기부여 메시지
            if done_pct >= 80:
                footer = "거의 다 했다! 마지막까지 끝내자 🔥"
            elif done_pct >= 50:
                footer = "반 이상 했네! 이 페이스 유지해 💪"
            elif done_pct > 0:
                footer = "시작이 반이야. 계속 가자!"
            else:
                footer = "아직 시작 전이야. 첫 태스크부터 해보자!"
            embed.set_footer(text=footer)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ 리포트 생성 실패: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportCog(bot))
