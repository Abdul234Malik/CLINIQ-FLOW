"""One-way sync worker for local events -> Supabase.

This service reads local unsynced events, upserts them into Supabase tables,
then marks local rows as synced.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.storage import list_unsynced_events, mark_events_synced


class SupabaseSyncService:
    def __init__(self, supabase_dsn: str | None = None) -> None:
        self.supabase_dsn = supabase_dsn or os.getenv("DATABASE_URL_SUPABASE")

    def status(self) -> dict[str, Any]:
        pending = list_unsynced_events(limit_per_table=5000)
        return {
            "configured": bool(self.supabase_dsn),
            "pending": {table: len(rows) for table, rows in pending.items()},
        }

    def sync_once(self, limit_per_table: int = 200) -> dict[str, Any]:
        if not self.supabase_dsn:
            return {"ok": False, "message": "DATABASE_URL_SUPABASE is not set", "synced": {}}

        pending = list_unsynced_events(limit_per_table=limit_per_table)
        synced_counts: dict[str, int] = {}
        with _supabase_connect(self.supabase_dsn) as conn:
            for table, rows in pending.items():
                if not rows:
                    synced_counts[table] = 0
                    continue
                event_ids = [row["event_id"] for row in rows]
                _upsert_rows(conn, table, rows)
                mark_events_synced(table, event_ids)
                synced_counts[table] = len(rows)
            conn.commit()

        return {"ok": True, "synced": synced_counts}


def _supabase_connect(dsn: str):
    try:
        import psycopg
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for Supabase sync") from exc
    return psycopg.connect(dsn)


def _upsert_rows(conn, table: str, rows: list[dict[str, Any]]) -> None:
    if table == "intake_events":
        for r in rows:
            red_flags = r.get("red_flags_json", [])
            if not isinstance(red_flags, str):
                red_flags = json.dumps(red_flags)
            conn.execute(
                """
                INSERT INTO intake_events (
                    event_id, visit_id, urgency_level, red_flags_json, sync_status, source_system, last_synced_at, created_at
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, NOW(), %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    visit_id = EXCLUDED.visit_id,
                    urgency_level = EXCLUDED.urgency_level,
                    red_flags_json = EXCLUDED.red_flags_json,
                    sync_status = EXCLUDED.sync_status,
                    source_system = EXCLUDED.source_system,
                    last_synced_at = NOW()
                """,
                (
                    r["event_id"],
                    r["visit_id"],
                    r["urgency_level"],
                    red_flags,
                    "synced",
                    r.get("source_system", "local"),
                    r.get("created_at"),
                ),
            )
        return

    if table == "dose_checks":
        for r in rows:
            warnings = r.get("warnings_json", [])
            if not isinstance(warnings, str):
                warnings = json.dumps(warnings)
            conn.execute(
                """
                INSERT INTO dose_checks (
                    event_id, visit_id, drug_name, chosen_dose_mg_per_day, safe, warnings_json, sync_status, source_system, last_synced_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, NOW(), %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    visit_id = EXCLUDED.visit_id,
                    drug_name = EXCLUDED.drug_name,
                    chosen_dose_mg_per_day = EXCLUDED.chosen_dose_mg_per_day,
                    safe = EXCLUDED.safe,
                    warnings_json = EXCLUDED.warnings_json,
                    sync_status = EXCLUDED.sync_status,
                    source_system = EXCLUDED.source_system,
                    last_synced_at = NOW()
                """,
                (
                    r["event_id"],
                    r["visit_id"],
                    r["drug_name"],
                    r["chosen_dose_mg_per_day"],
                    bool(r["safe"]),
                    warnings,
                    "synced",
                    r.get("source_system", "local"),
                    r.get("created_at"),
                ),
            )
        return

    if table == "overrides":
        for r in rows:
            conn.execute(
                """
                INSERT INTO overrides (
                    event_id, med_order_id, override_reason, actor_role, doctor_id, sync_status, source_system, last_synced_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    med_order_id = EXCLUDED.med_order_id,
                    override_reason = EXCLUDED.override_reason,
                    actor_role = EXCLUDED.actor_role,
                    doctor_id = EXCLUDED.doctor_id,
                    sync_status = EXCLUDED.sync_status,
                    source_system = EXCLUDED.source_system,
                    last_synced_at = NOW()
                """,
                (
                    r["event_id"],
                    r["med_order_id"],
                    r["override_reason"],
                    r["actor_role"],
                    r.get("doctor_id"),
                    "synced",
                    r.get("source_system", "local"),
                    r.get("created_at"),
                ),
            )
