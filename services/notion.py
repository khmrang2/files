"""Notion API 래퍼 — 태스크 CRUD 및 칸반 관리."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from notion_client import APIResponseError, Client

from utils.id_gen import generate_task_id

logger = logging.getLogger(__name__)


class NotionServiceError(Exception):
    """Notion API 호출 중 발생한 오류를 래핑."""


class NotionTaskService:
    """Notion 데이터베이스를 칸반보드처럼 사용하는 서비스."""

    VALID_STATUSES = ("시작 전", "진행 중", "완료")
    VALID_PRIORITIES = ("high", "medium", "low")

    def __init__(self) -> None:
        self.client = Client(auth=os.getenv("NOTION_TOKEN"))
        self.database_id = os.getenv("NOTION_DATABASE_ID")
        self.datasource_id = os.getenv("NOTION_DATASOURCE_ID")

    # ── 태스크 생성 ─────────────────────────────────────────
    def create_task(self, name: str, priority: str = "medium") -> dict:
        """새 태스크를 Notion DB에 추가하고 결과를 반환."""
        task_id = generate_task_id()
        now = datetime.now(timezone.utc).isoformat()

        try:
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Name": {"title": [{"text": {"content": name}}]},
                    "Status": {"status": {"name": "시작 전"}},
                    "Priority": {"rich_text": [{"text": {"content": priority}}]},
                    "TaskID": {"rich_text": [{"text": {"content": task_id}}]},
                    "CreatedAt": {"date": {"start": now}},
                    "StatusChangedAt": {"date": {"start": now}},
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (create_task): %s", e)
            raise NotionServiceError(f"태스크 생성 중 Notion API 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (create_task): %s", e)
            raise NotionServiceError(f"태스크 생성 중 오류 발생: {e}") from e

        return {
            "page_id": page["id"],
            "task_id": task_id,
            "name": name,
            "status": "시작 전",
            "priority": priority,
        }

    # ── 태스크 목록 조회 ───────────────────────────────────
    def list_tasks(self, status_filter: Optional[str] = None) -> list[dict]:
        """태스크 목록 조회. status_filter가 있으면 해당 상태만."""
        query_kwargs: dict = {
            "sorts": [{"property": "CreatedAt", "direction": "descending"}],
        }
        if status_filter and status_filter in self.VALID_STATUSES:
            query_kwargs["filter"] = {
                "property": "Status",
                "status": {"equals": status_filter},
            }

        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                **query_kwargs,
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (list_tasks): %s", e)
            raise NotionServiceError(f"태스크 목록 조회 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (list_tasks): %s", e)
            raise NotionServiceError(f"태스크 목록 조회 중 오류: {e}") from e

        return [self._parse_page(page) for page in response["results"]]

    # ── 태스크 상태 변경 ───────────────────────────────────
    def update_status(self, task_id: str, new_status: str) -> Optional[dict]:
        """태스크 상태 업데이트. 상태 변경 시 StatusChangedAt 갱신, done 시 CompletedAt 기록."""
        page = self._find_page_by_task_id(task_id)
        if not page:
            return None

        now = datetime.now(timezone.utc).isoformat()
        props: dict = {
            "Status": {"status": {"name": new_status}},
            "StatusChangedAt": {"date": {"start": now}},
        }
        if new_status == "완료":
            props["CompletedAt"] = {"date": {"start": now}}

        try:
            self.client.pages.update(page_id=page["id"], properties=props)
        except APIResponseError as e:
            logger.error("Notion API 오류 (update_status): %s", e)
            raise NotionServiceError(f"상태 변경 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (update_status): %s", e)
            raise NotionServiceError(f"상태 변경 중 오류: {e}") from e

        return {
            "task_id": task_id,
            "name": self._extract_title(page),
            "status": new_status,
        }

    # ── 태스크 완료 (shortcut) ─────────────────────────────
    def complete_task(self, task_id: str) -> Optional[dict]:
        """태스크를 done으로 마킹."""
        return self.update_status(task_id, "완료")

    # ── 태스크 수정 ────────────────────────────────────────
    def edit_task(
        self,
        task_id: str,
        name: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Optional[dict]:
        """태스크 이름/우선순위 수정."""
        page = self._find_page_by_task_id(task_id)
        if not page:
            return None

        props: dict = {}
        if name:
            props["Name"] = {"title": [{"text": {"content": name}}]}
        if priority and priority in self.VALID_PRIORITIES:
            props["Priority"] = {"rich_text": [{"text": {"content": priority}}]}

        if not props:
            return None

        try:
            self.client.pages.update(page_id=page["id"], properties=props)
        except APIResponseError as e:
            logger.error("Notion API 오류 (edit_task): %s", e)
            raise NotionServiceError(f"태스크 수정 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (edit_task): %s", e)
            raise NotionServiceError(f"태스크 수정 중 오류: {e}") from e

        updated = self._find_page_by_task_id(task_id)
        return self._parse_page(updated) if updated else None

    # ── 태스크 삭제 (아카이브) ──────────────────────────────
    def delete_task(self, task_id: str) -> bool:
        """태스크를 Notion에서 아카이브 처리."""
        page = self._find_page_by_task_id(task_id)
        if not page:
            return False

        try:
            self.client.pages.update(page_id=page["id"], archived=True)
        except APIResponseError as e:
            logger.error("Notion API 오류 (delete_task): %s", e)
            raise NotionServiceError(f"태스크 삭제 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (delete_task): %s", e)
            raise NotionServiceError(f"태스크 삭제 중 오류: {e}") from e

        return True

    # ── 오늘 완료된 태스크 ──────────────────────────────────
    def get_today_completed(self) -> list[dict]:
        """오늘 완료된 태스크 목록."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                filter={
                    "and": [
                        {"property": "Status", "status": {"equals": "완료"}},
                        {"property": "CompletedAt", "date": {"on_or_after": today}},
                    ]
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (get_today_completed): %s", e)
            raise NotionServiceError(f"완료 태스크 조회 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (get_today_completed): %s", e)
            raise NotionServiceError(f"완료 태스크 조회 중 오류: {e}") from e

        return [self._parse_page(page) for page in response["results"]]

    # ── 진행 중 태스크 ──────────────────────────────────────
    def get_in_progress(self) -> list[dict]:
        """현재 doing 상태인 태스크."""
        return self.list_tasks(status_filter="진행 중")

    # ── 방치된 긴급 태스크 조회 ──────────────────────────────
    def get_stale_high_priority(self, max_hours: int = 24) -> list[dict]:
        """HIGH 우선순위이면서 todo/doing 상태가 오래된 태스크 조회."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_hours)).isoformat()

        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                filter={
                    "and": [
                        {"property": "Priority", "rich_text": {"equals": "high"}},
                        {
                            "or": [
                                {"property": "Status", "status": {"equals": "시작 전"}},
                                {"property": "Status", "status": {"equals": "진행 중"}},
                            ]
                        },
                        {
                            "or": [
                                {
                                    "property": "StatusChangedAt",
                                    "date": {"on_or_before": cutoff},
                                },
                                {
                                    "property": "StatusChangedAt",
                                    "date": {"is_empty": True},
                                },
                            ]
                        },
                    ]
                },
                sorts=[{"property": "StatusChangedAt", "direction": "ascending"}],
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (get_stale_high_priority): %s", e)
            raise NotionServiceError(f"긴급 태스크 조회 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (get_stale_high_priority): %s", e)
            raise NotionServiceError(f"긴급 태스크 조회 중 오류: {e}") from e

        return [self._parse_page(page) for page in response["results"]]

    # ── 내부 헬퍼 ──────────────────────────────────────────
    def _find_page_by_task_id(self, task_id: str) -> Optional[dict]:
        """TaskID 필드로 Notion 페이지 검색."""
        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                filter={
                    "property": "TaskID",
                    "rich_text": {"equals": task_id},
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (_find_page): %s", e)
            raise NotionServiceError(f"태스크 검색 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (_find_page): %s", e)
            raise NotionServiceError(f"태스크 검색 중 오류: {e}") from e

        results = response.get("results", [])
        return results[0] if results else None

    @staticmethod
    def _extract_title(page: dict) -> str:
        title_prop = page["properties"].get("Name", {}).get("title", [])
        return title_prop[0]["text"]["content"] if title_prop else "(제목 없음)"

    @staticmethod
    def _extract_rich_text(page: dict, prop_name: str) -> str:
        rt = page["properties"].get(prop_name, {}).get("rich_text", [])
        return rt[0]["text"]["content"] if rt else ""

    @staticmethod
    def _extract_status(page: dict, prop_name: str) -> str:
        """Notion 기본 status 타입 속성 추출."""
        status = page["properties"].get(prop_name, {}).get("status")
        return status["name"] if status else ""

    @staticmethod
    def _extract_date(page: dict, prop_name: str) -> str:
        date = page["properties"].get(prop_name, {}).get("date")
        return date["start"] if date else ""

    def _parse_page(self, page: dict) -> dict:
        return {
            "page_id": page["id"],
            "task_id": self._extract_rich_text(page, "TaskID"),
            "name": self._extract_title(page),
            "status": self._extract_status(page, "Status"),
            "priority": self._extract_rich_text(page, "Priority"),
            "created_at": self._extract_date(page, "CreatedAt"),
            "completed_at": self._extract_date(page, "CompletedAt"),
            "status_changed_at": self._extract_date(page, "StatusChangedAt"),
        }
