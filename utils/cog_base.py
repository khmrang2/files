"""한/영 명령어 별칭을 자동 등록하는 Cog 베이스 클래스."""

from __future__ import annotations

import copy

from discord.ext import commands


class AliasCog(commands.Cog):
    """ALIASES 딕셔너리에 선언된 별칭을 자동으로 커맨드 트리에 등록한다.

    사용법::

        class TasksCog(AliasCog):
            ALIASES = {
                "작업추가": "task_add",   # /작업추가 → /task_add 과 동일
                "작업목록": "task_list",
            }
    """

    ALIASES: dict[str, str] = {}  # {별칭: 원본 커맨드 이름}

    async def cog_load(self) -> None:
        for alias_name, original_name in self.ALIASES.items():
            original = self.bot.tree.get_command(original_name)
            if not original:
                continue
            alias = copy.deepcopy(original)
            alias.name = alias_name
            alias.binding = self
            self.bot.tree.add_command(alias)

    def cog_unload(self) -> None:
        for alias_name in self.ALIASES:
            self.bot.tree.remove_command(alias_name)
