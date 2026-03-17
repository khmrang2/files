"""Notion API 래퍼 — 이슈 CRUD 관리."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from notion_client import APIResponseError, Client

from utils.id_gen import generate_task_id

logger = logging.getLogger(__name__)


class NotionIssueServiceError(Exception):
    """Notion API 호출 중 발생한 이슈 관련 오류를 래핑."""


class NotionIssueService:
    """이슈(태스크 하위 문제) 관리 서비스."""

    VALID_STATUSES = ("보고됨", "처리 중", "해결됨")
    VALID_SEVERITIES = ("high", "medium", "low")

    def __init__(self) -> None:
        self.client = Client(auth=os.getenv("NOTION_TOKEN"))
        self.database_id = os.getenv("NOTION_ISSUE_DATABASE_ID")
        self.datasource_id = os.getenv("NOTION_ISSUE_DATASOURCE_ID")
        # 상위 태스크 검증용
        self.task_datasource_id = os.getenv("NOTION_DATASOURCE_ID")

    # ── 이슈 생성 ─────────────────────────────────────────
    def create_issue(
        self, parent_task_id: str, name: str, severity: str = "medium"
    ) -> dict:
        """새 이슈를 생성. 상위 태스크 존재 여부를 먼저 검증."""
        parent_page = self._validate_parent_task(parent_task_id)
        if not parent_page:
            raise NotionIssueServiceError(
                f"상위 태스크를 찾을 수 없습니다: {parent_task_id}"
            )

        issue_id = generate_task_id()
        now = datetime.now(timezone.utc).isoformat()

        try:
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Name": {"title": [{"text": {"content": name}}]},
                    "IssueID": {"rich_text": [{"text": {"content": issue_id}}]},
                    "ParentTask": {"relation": [{"id": parent_page["id"]}]},
                    "ParentTaskID": {
                        "rich_text": [{"text": {"content": parent_task_id}}]
                    },
                    "Status": {"status": {"name": "보고됨"}},
                    "Severity": {"rich_text": [{"text": {"content": severity}}]},
                    "CreatedAt": {"date": {"start": now}},
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (create_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 생성 중 Notion API 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (create_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 생성 중 오류 발생: {e}") from e

        return {
            "page_id": page["id"],
            "issue_id": issue_id,
            "parent_task_id": parent_task_id,
            "name": name,
            "status": "보고됨",
            "severity": severity,
        }

    # ── 이슈 목록 조회 ───────────────────────────────────
    def list_issues(self, parent_task_id: Optional[str] = None) -> list[dict]:
        """이슈 목록 조회. parent_task_id가 있으면 해당 태스크의 이슈만."""
        query_kwargs: dict = {
            "sorts": [{"property": "CreatedAt", "direction": "descending"}],
        }
        if parent_task_id:
            query_kwargs["filter"] = {
                "property": "ParentTaskID",
                "rich_text": {"equals": parent_task_id},
            }

        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                **query_kwargs,
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (list_issues): %s", e)
            raise NotionIssueServiceError(f"이슈 목록 조회 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (list_issues): %s", e)
            raise NotionIssueServiceError(f"이슈 목록 조회 중 오류: {e}") from e

        return [self._parse_issue(page) for page in response["results"]]

    # ── 이슈 해결 처리 ───────────────────────────────────
    def resolve_issue(self, issue_id: str) -> Optional[dict]:
        """이슈를 해결됨으로 마킹."""
        page = self._find_page_by_issue_id(issue_id)
        if not page:
            return None

        now = datetime.now(timezone.utc).isoformat()
        props: dict = {
            "Status": {"status": {"name": "해결됨"}},
            "ResolvedAt": {"date": {"start": now}},
        }

        try:
            self.client.pages.update(page_id=page["id"], properties=props)
        except APIResponseError as e:
            logger.error("Notion API 오류 (resolve_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 해결 처리 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (resolve_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 해결 처리 중 오류: {e}") from e

        return {
            "issue_id": issue_id,
            "name": self._extract_title(page),
            "status": "해결됨",
        }

    # ── 이슈 삭제 (아카이브) ──────────────────────────────
    def delete_issue(self, issue_id: str) -> bool:
        """이슈를 Notion에서 아카이브 처리."""
        page = self._find_page_by_issue_id(issue_id)
        if not page:
            return False

        try:
            self.client.pages.update(page_id=page["id"], archived=True)
        except APIResponseError as e:
            logger.error("Notion API 오류 (delete_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 삭제 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (delete_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 삭제 중 오류: {e}") from e

        return True

    # ── 내부 헬퍼 ──────────────────────────────────────────
    def _validate_parent_task(self, task_id: str) -> Optional[dict]:
        """Task DB에서 상위 태스크 존재 여부 확인."""
        try:
            response = self.client.data_sources.query(
                data_source_id=self.task_datasource_id,
                filter={
                    "property": "TaskID",
                    "rich_text": {"equals": task_id},
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (_validate_parent_task): %s", e)
            raise NotionIssueServiceError(f"상위 태스크 검증 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (_validate_parent_task): %s", e)
            raise NotionIssueServiceError(f"상위 태스크 검증 중 오류: {e}") from e

        results = response.get("results", [])
        return results[0] if results else None

    def _find_page_by_issue_id(self, issue_id: str) -> Optional[dict]:
        """IssueID 필드로 Notion 페이지 검색."""
        try:
            response = self.client.data_sources.query(
                data_source_id=self.datasource_id,
                filter={
                    "property": "IssueID",
                    "rich_text": {"equals": issue_id},
                },
            )
        except APIResponseError as e:
            logger.error("Notion API 오류 (_find_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 검색 중 오류: {e}") from e
        except Exception as e:
            logger.error("예상치 못한 오류 (_find_issue): %s", e)
            raise NotionIssueServiceError(f"이슈 검색 중 오류: {e}") from e

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
        status = page["properties"].get(prop_name, {}).get("status")
        return status["name"] if status else ""

    @staticmethod
    def _extract_date(page: dict, prop_name: str) -> str:
        date = page["properties"].get(prop_name, {}).get("date")
        return date["start"] if date else ""

    def _parse_issue(self, page: dict) -> dict:
        return {
            "page_id": page["id"],
            "issue_id": self._extract_rich_text(page, "IssueID"),
            "parent_task_id": self._extract_rich_text(page, "ParentTaskID"),
            "name": self._extract_title(page),
            "status": self._extract_status(page, "Status"),
            "severity": self._extract_rich_text(page, "Severity"),
            "created_at": self._extract_date(page, "CreatedAt"),
            "resolved_at": self._extract_date(page, "ResolvedAt"),
        }
