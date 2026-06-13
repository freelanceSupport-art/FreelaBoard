import csv
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from freelaboard_app.store import (
    ProjectStore,
    deadline_notice_signature,
)


class ProjectStoreTest(unittest.TestCase):
    def test_save_list_update_stats_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "freelaboard.sqlite3"
            store = ProjectStore(db_path)

            project_id = store.save_project(
                {
                    "title": "LP制作",
                    "client": "ACME",
                    "status": "進行中",
                    "due_date": "2099-01-01",
                    "amount": "120,000",
                    "invoice_state": "請求済",
                    "payment_state": "未入金",
                    "memo": "初回案件",
                }
            )

            rows = store.list_projects(search="acme")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], project_id)
            self.assertEqual(rows[0]["amount"], 120000)

            store.save_project({**rows[0], "payment_state": "入金済"}, project_id)
            stats = store.stats()
            self.assertEqual(stats.total_projects, 1)
            self.assertEqual(stats.paid_amount, 120000)
            self.assertEqual(stats.unpaid_amount, 0)

            csv_path = Path(temp_dir) / "export.csv"
            count = store.export_csv(csv_path, store.list_projects())
            self.assertEqual(count, 1)
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                exported = list(csv.DictReader(handle))
            self.assertEqual(exported[0]["案件名"], "LP制作")

    def test_settings_and_due_alert_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir) / "freelaboard.sqlite3")
            settings = store.settings()
            self.assertTrue(settings.deadline_notifications)
            self.assertTrue(settings.resident_on_close)
            self.assertEqual(settings.notification_days, 7)

            store.set_bool_setting("deadline_notifications", False)
            store.set_setting("notification_days", "3")
            settings = store.settings()
            self.assertFalse(settings.deadline_notifications)
            self.assertEqual(settings.notification_days, 3)

            today = date.today()
            store.save_project(
                {
                    "title": "通知対象",
                    "status": "進行中",
                    "due_date": (today + timedelta(days=2)).isoformat(),
                }
            )
            store.save_project(
                {
                    "title": "通知対象外",
                    "status": "進行中",
                    "due_date": (today + timedelta(days=9)).isoformat(),
                }
            )
            store.save_project(
                {
                    "title": "完了済み",
                    "status": "完了",
                    "due_date": (today + timedelta(days=1)).isoformat(),
                }
            )

            targets = store.due_alert_projects(window_days=3)
            self.assertEqual([row["title"] for row in targets], ["通知対象"])
            self.assertIn(str(today), deadline_notice_signature(targets, today))

    def test_rejects_invalid_due_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir) / "freelaboard.sqlite3")
            with self.assertRaises(ValueError):
                store.save_project({"title": "不正日付", "due_date": "2099/01/01"})


if __name__ == "__main__":
    unittest.main()
