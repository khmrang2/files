"""TaskMaster Bot — 디스코드 일정 관리 & 사수 봇.

사용법:
    1. .env 파일에 토큰과 설정값 입력
    2. python bot.py
"""

from __future__ import annotations

import importlib
import os
import sys
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# 필수 환경 변수 목록
REQUIRED_ENV_VARS = ["DISCORD_TOKEN", "NOTION_TOKEN", "NOTION_DATABASE_ID", "NOTION_ISSUE_DATABASE_ID"]

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")


class TaskMasterBot(commands.Bot):
    """메인 봇 클래스."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    COG_LIST = [
        "cogs.tasks",
        "cogs.checkin",
        "cogs.report",
        "cogs.issues",
    ]

    async def setup_hook(self) -> None:
        """Cog 로드 및 슬래시 명령어 동기화."""
        bot = self

        @self.tree.command(name="reload", description="코그 및 서비스 모듈을 핫 리로드합니다.")
        @app_commands.checks.has_permissions(administrator=True)
        async def reload(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)

            # services/ 하위 모듈 리로드
            reloaded_services: list[str] = []
            for mod_name, module in list(sys.modules.items()):
                if mod_name.startswith("services.") or mod_name.startswith("utils."):
                    try:
                        importlib.reload(module)
                        reloaded_services.append(mod_name)
                    except Exception as e:
                        await interaction.followup.send(f"❌ `{mod_name}` 리로드 실패: {e}")
                        return

            # Cog 리로드
            results: list[str] = []
            for cog in bot.COG_LIST:
                try:
                    await bot.reload_extension(cog)
                    results.append(f"✅ {cog}")
                except commands.ExtensionNotLoaded:
                    await bot.load_extension(cog)
                    results.append(f"✅ {cog} (새로 로드)")
                except Exception as e:
                    results.append(f"❌ {cog}: {e}")

            # 슬래시 명령어 재동기화
            if GUILD_ID:
                guild = discord.Object(id=int(GUILD_ID))
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
            else:
                await bot.tree.sync()

            summary = "\n".join(results)
            svc = ", ".join(reloaded_services) if reloaded_services else "없음"
            await interaction.followup.send(
                f"**리로드 완료**\n```\n{summary}\n```\n서비스 리로드: `{svc}`"
            )

        for cog in self.COG_LIST:
            try:
                await self.load_extension(cog)
                print(f"  ✅ {cog} 로드 완료")
            except Exception as e:
                print(f"  ❌ {cog} 로드 실패: {e}")

        # 슬래시 명령어 동기화
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"  🔄 길드 {GUILD_ID}에 명령어 동기화 완료")
        else:
            await self.tree.sync()
            print("  🔄 글로벌 명령어 동기화 완료 (최대 1시간 소요)")

    async def on_ready(self) -> None:
        print(f"\n{'='*40}")
        print(f"🤖 {self.user} 온라인!")
        print(f"   서버 수: {len(self.guilds)}")
        print(f"{'='*40}\n")

        # 봇 상태 메시지
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="너의 진행 상황 👀",
        )
        await self.change_presence(activity=activity)


async def main() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        print("❌ 필수 환경 변수가 설정되지 않았습니다:")
        for var in missing:
            print(f"   - {var}")
        print("💡 .env 파일을 확인해주세요.")
        return

    bot = TaskMasterBot()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
