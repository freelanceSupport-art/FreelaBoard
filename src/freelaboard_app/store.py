from __future__ import annotations

import csv
import os
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


STATUSES = ("相談中", "進行中", "レビュー中", "納品済", "完了", "保留")
INVOICE_STATES = ("未請求", "請求済", "請求不要")
PAYMENT_STATES = ("未入金", "一部入金", "入金済")
FINAL_STATUSES = {"納品済", "完了"}
ALL_FILTER = "すべて"
DUE_FILTERS = (ALL_FILTER, "7日以内", "期限超過", "期限なし")

CSV_COLUMNS = (
    ("id", "ID"),
    ("title", "案件名"),
    ("client", "クライアント"),
    ("status", "ステータス"),
    ("due_date", "納期"),
    ("amount", "金額"),
    ("invoice_state", "請求状態"),
    ("payment_state", "入金状態"),
    ("memo", "メモ"),
    ("created_at", "作成日時"),
    ("updated_at", "更新日時"),
)

DEFAULT_SETTINGS = {
    "deadline_notifications": "1",
    "resident_on_close": "1",
    "notification_days": "7",
    "last_deadline_notice": "",
}


@dataclass(frozen=True)
class AppStats:
    total_projects: int
    active_projects: int
    due_soon: int
    overdue: int
    unpaid_amount: int
    paid_amount: int


@dataclass(frozen=True)
class AppSettings:
    deadline_notifications: bool
    resident_on_close: bool
    notification_days: int
    last_deadline_notice: str


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".freelaboard_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def default_db_path() -> Path:
    """Return a portable writable database path for dev and frozen builds."""
    candidates: list[Path] = []

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    else:
        candidates.append(Path(__file__).resolve().parents[2])

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "FreelaBoard")
    candidates.append(Path.home() / "FreelaBoard")

    for base in candidates:
        if _is_writable_dir(base):
            return base / "freelaboard.sqlite3"

    return Path.cwd() / "freelaboard.sqlite3"


def parse_due_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def days_until(value: str | None, today: date | None = None) -> int | None:
    due = parse_due_date(value)
    if due is None:
        return None
    return (due - (today or date.today())).days


def describe_due(value: str | None, today: date | None = None) -> str:
    text = (value or "").strip()
    if not text:
        return "-"
    days = days_until(text, today)
    if days is None:
        return text
    if days < 0:
        return f"{text} / {abs(days)}日超過"
    if days == 0:
        return f"{text} / 今日"
    if days <= 7:
        return f"{text} / あと{days}日"
    return text


def _normalize_amount(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    text = str(value).replace(",", "").replace("円", "").strip()
    if not text:
        return 0
    return max(int(float(text)), 0)


def _normalize_choice(value: object, choices: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip()
    return text if text in choices else default


def deadline_notice_signature(
    rows: Iterable[dict[str, object]], today: date | None = None
) -> str:
    target_date = today or date.today()
    parts = [
        f"{row.get('id')}:{row.get('due_date')}:{row.get('updated_at')}"
        for row in rows
    ]
    return f"{target_date.isoformat()}|" + ",".join(parts)


class ProjectStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or default_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    client TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '相談中',
                    due_date TEXT NOT NULL DEFAULT '',
                    amount INTEGER NOT NULL DEFAULT 0,
                    invoice_state TEXT NOT NULL DEFAULT '未請求',
                    payment_state TEXT NOT NULL DEFAULT '未入金',
                    memo TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_projects_due_date
                    ON projects(due_date);
                CREATE INDEX IF NOT EXISTS idx_projects_status
                    ON projects(status);
                CREATE INDEX IF NOT EXISTS idx_projects_invoice_payment
                    ON projects(invoice_state, payment_state);

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                DEFAULT_SETTINGS.items(),
            )

    def _clean_payload(self, payload: dict[str, object]) -> dict[str, object]:
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("案件名を入力してください。")

        due_date = str(payload.get("due_date", "")).strip()
        if due_date:
            try:
                date.fromisoformat(due_date)
            except ValueError as exc:
                raise ValueError("納期は YYYY-MM-DD 形式で入力してください。") from exc

        return {
            "title": title,
            "client": str(payload.get("client", "")).strip(),
            "status": _normalize_choice(payload.get("status"), STATUSES, STATUSES[0]),
            "due_date": due_date,
            "amount": _normalize_amount(payload.get("amount")),
            "invoice_state": _normalize_choice(
                payload.get("invoice_state"), INVOICE_STATES, INVOICE_STATES[0]
            ),
            "payment_state": _normalize_choice(
                payload.get("payment_state"), PAYMENT_STATES, PAYMENT_STATES[0]
            ),
            "memo": str(payload.get("memo", "")).strip(),
        }

    def save_project(
        self, payload: dict[str, object], project_id: int | None = None
    ) -> int:
        clean = self._clean_payload(payload)
        now = datetime.now().isoformat(timespec="seconds")

        with self._connection() as connection:
            if project_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO projects (
                        title, client, status, due_date, amount,
                        invoice_state, payment_state, memo, created_at, updated_at
                    )
                    VALUES (
                        :title, :client, :status, :due_date, :amount,
                        :invoice_state, :payment_state, :memo, :created_at, :updated_at
                    )
                    """,
                    {**clean, "created_at": now, "updated_at": now},
                )
                return int(cursor.lastrowid)

            connection.execute(
                """
                UPDATE projects
                SET title = :title,
                    client = :client,
                    status = :status,
                    due_date = :due_date,
                    amount = :amount,
                    invoice_state = :invoice_state,
                    payment_state = :payment_state,
                    memo = :memo,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                {**clean, "updated_at": now, "id": project_id},
            )
            return project_id

    def delete_project(self, project_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def get_project(self, project_id: int) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_projects(
        self,
        search: str = "",
        status_filter: str = ALL_FILTER,
        due_filter: str = ALL_FILTER,
    ) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM projects
                    ORDER BY
                        CASE WHEN due_date = '' THEN 1 ELSE 0 END,
                        due_date ASC,
                        updated_at DESC,
                        id DESC
                    """
                ).fetchall()
            ]

        query = search.strip().lower()
        if query:
            rows = [
                row
                for row in rows
                if query
                in " ".join(
                    str(row.get(key, ""))
                    for key in ("title", "client", "status", "memo")
                ).lower()
            ]

        if status_filter and status_filter != ALL_FILTER:
            rows = [row for row in rows if row.get("status") == status_filter]

        if due_filter and due_filter != ALL_FILTER:
            today = date.today()
            if due_filter == "7日以内":
                rows = [
                    row
                    for row in rows
                    if (days := days_until(str(row.get("due_date", "")), today))
                    is not None
                    and 0 <= days <= 7
                ]
            elif due_filter == "期限超過":
                rows = [
                    row
                    for row in rows
                    if (days := days_until(str(row.get("due_date", "")), today))
                    is not None
                    and days < 0
                ]
            elif due_filter == "期限なし":
                rows = [row for row in rows if not str(row.get("due_date", ""))]

        return rows

    def due_alert_projects(self, window_days: int = 7) -> list[dict[str, object]]:
        today = date.today()
        rows: list[dict[str, object]] = []
        for row in self.list_projects():
            if row.get("status") in FINAL_STATUSES:
                continue
            days = days_until(str(row.get("due_date", "")), today)
            if days is None:
                continue
            if days <= window_days:
                enriched = dict(row)
                enriched["days_until"] = days
                rows.append(enriched)
        return sorted(rows, key=lambda row: int(row.get("days_until", 9999)))

    def stats(self) -> AppStats:
        rows = self.list_projects()
        today = date.today()

        active_rows = [row for row in rows if row.get("status") not in FINAL_STATUSES]
        due_soon = 0
        overdue = 0
        unpaid_amount = 0
        paid_amount = 0

        for row in rows:
            amount = int(row.get("amount") or 0)
            if row.get("payment_state") == "入金済":
                paid_amount += amount
            elif row.get("invoice_state") == "請求済":
                unpaid_amount += amount

            if row.get("status") in FINAL_STATUSES:
                continue

            days = days_until(str(row.get("due_date", "")), today)
            if days is None:
                continue
            if days < 0:
                overdue += 1
            elif days <= 7:
                due_soon += 1

        return AppStats(
            total_projects=len(rows),
            active_projects=len(active_rows),
            due_soon=due_soon,
            overdue=overdue,
            unpaid_amount=unpaid_amount,
            paid_amount=paid_amount,
        )

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: object) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )

    def get_bool_setting(self, key: str, default: bool = False) -> bool:
        return self.get_setting(key, "1" if default else "0") == "1"

    def set_bool_setting(self, key: str, value: bool) -> None:
        self.set_setting(key, "1" if value else "0")

    def get_int_setting(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get_setting(key, str(default)))
        except ValueError:
            return default

    def settings(self) -> AppSettings:
        days = max(1, min(30, self.get_int_setting("notification_days", 7)))
        return AppSettings(
            deadline_notifications=self.get_bool_setting(
                "deadline_notifications", True
            ),
            resident_on_close=self.get_bool_setting("resident_on_close", True),
            notification_days=days,
            last_deadline_notice=self.get_setting("last_deadline_notice", ""),
        )

    def export_csv(self, path: str | Path, rows: Iterable[dict[str, object]]) -> int:
        row_list = list(rows)
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=[label for _, label in CSV_COLUMNS]
            )
            writer.writeheader()
            for row in row_list:
                writer.writerow(
                    {label: row.get(key, "") for key, label in CSV_COLUMNS}
                )
        return len(row_list)
