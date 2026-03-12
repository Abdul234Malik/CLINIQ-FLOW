"""Unified data-access layer for CLINIQ-FLOW.

This file hides database details from route handlers.
Routes call simple functions like `create_patient(...)` or `get_metrics()`,
and this module writes/reads from either local SQLite or local Postgres.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

EventMap = dict[str, list[dict[str, Any]]]
TABLES = ("intake_events", "dose_checks", "overrides")


def _backend() -> str:
    configured = (os.getenv("CLINIQ_DB_BACKEND") or "").strip().lower()
    if configured in {"postgres", "sqlite"}:
        return configured
    if os.getenv("DATABASE_URL_LOCAL"):
        return "postgres"
    return "sqlite"


def _db_path() -> str:
    env_path = os.getenv("CLINIQ_DB_PATH")
    if env_path:
        return env_path
    base = Path(__file__).resolve().parents[2]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "cliniq_flow.db")


def _sqlite_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_connect(dsn: str | None = None):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - exercised only in postgres mode.
        raise RuntimeError("psycopg is required for Postgres mode") from exc

    url = dsn or os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_LOCAL or DATABASE_URL is required for Postgres mode")
    return psycopg.connect(url, row_factory=dict_row)


def init_db() -> None:
    if _backend() == "postgres":
        _init_postgres()
    else:
        _init_sqlite()


def _init_postgres() -> None:
    with _postgres_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                date_of_birth TEXT,
                gender TEXT,
                phone TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                visit_status TEXT NOT NULL DEFAULT 'open',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intakes (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                normalized_text TEXT,
                structured_json JSONB,
                urgency_level TEXT,
                red_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                summary_json JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS med_orders (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                drug_name TEXT NOT NULL,
                dose_mg_per_day INTEGER NOT NULL,
                frequency_per_day INTEGER NOT NULL,
                dose_check_result JSONB,
                is_safe BOOLEAN NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doctor_conversations (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                structured_json JSONB,
                soap_json JSONB,
                urgency_json JSONB,
                validation_json JSONB,
                audio_reference TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intake_events (
                event_id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                urgency_level TEXT NOT NULL,
                red_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dose_checks (
                event_id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                drug_name TEXT NOT NULL,
                chosen_dose_mg_per_day INTEGER NOT NULL,
                safe BOOLEAN NOT NULL,
                warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS overrides (
                event_id TEXT PRIMARY KEY,
                med_order_id TEXT NOT NULL,
                override_reason TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                doctor_id TEXT,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()


def _init_sqlite() -> None:
    with _sqlite_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                date_of_birth TEXT,
                gender TEXT,
                phone TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                visit_status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intakes (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                normalized_text TEXT,
                structured_json TEXT,
                urgency_level TEXT,
                red_flags_json TEXT NOT NULL,
                summary_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS med_orders (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                drug_name TEXT NOT NULL,
                dose_mg_per_day INTEGER NOT NULL,
                frequency_per_day INTEGER NOT NULL,
                dose_check_result TEXT,
                is_safe INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doctor_conversations (
                id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                structured_json TEXT,
                soap_json TEXT,
                urgency_json TEXT,
                validation_json TEXT,
                audio_reference TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intake_events (
                event_id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                urgency_level TEXT NOT NULL,
                red_flags_json TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dose_checks (
                event_id TEXT PRIMARY KEY,
                visit_id TEXT NOT NULL,
                drug_name TEXT NOT NULL,
                chosen_dose_mg_per_day INTEGER NOT NULL,
                safe INTEGER NOT NULL,
                warnings_json TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS overrides (
                event_id TEXT PRIMARY KEY,
                med_order_id TEXT NOT NULL,
                override_reason TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                doctor_id TEXT,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                source_system TEXT NOT NULL DEFAULT 'local',
                last_synced_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        _ensure_sqlite_columns(conn)


def _ensure_sqlite_columns(conn: sqlite3.Connection) -> None:
    for table, required in {
        "intake_events": {"sync_status": "TEXT DEFAULT 'pending'", "source_system": "TEXT DEFAULT 'local'", "last_synced_at": "TEXT"},
        "dose_checks": {"sync_status": "TEXT DEFAULT 'pending'", "source_system": "TEXT DEFAULT 'local'", "last_synced_at": "TEXT"},
        "overrides": {"sync_status": "TEXT DEFAULT 'pending'", "source_system": "TEXT DEFAULT 'local'", "last_synced_at": "TEXT"},
    }.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_def in required.items():
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
    conn.commit()


def log_intake(event_id: str, visit_id: str, urgency_level: str, red_flags: list[str]) -> None:
    init_db()
    source_system = os.getenv("SOURCE_SYSTEM", "local")
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO intake_events (event_id, visit_id, urgency_level, red_flags_json, sync_status, source_system)
                VALUES (%s, %s, %s, %s::jsonb, 'pending', %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, visit_id, urgency_level, json.dumps(red_flags), source_system),
            )
            conn.commit()
        return

    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO intake_events (
                event_id, visit_id, urgency_level, red_flags_json, sync_status, source_system
            )
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (event_id, visit_id, urgency_level, json.dumps(red_flags), source_system),
        )
        conn.commit()


def log_dose_check(
    event_id: str,
    visit_id: str,
    drug_name: str,
    chosen_dose_mg_per_day: int,
    safe: bool,
    warnings: list[str],
) -> None:
    init_db()
    source_system = os.getenv("SOURCE_SYSTEM", "local")
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO dose_checks (
                    event_id, visit_id, drug_name, chosen_dose_mg_per_day, safe, warnings_json, sync_status, source_system
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending', %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, visit_id, drug_name, chosen_dose_mg_per_day, safe, json.dumps(warnings), source_system),
            )
            conn.commit()
        return

    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO dose_checks (
                event_id, visit_id, drug_name, chosen_dose_mg_per_day, safe, warnings_json, sync_status, source_system
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (event_id, visit_id, drug_name, chosen_dose_mg_per_day, int(safe), json.dumps(warnings), source_system),
        )
        conn.commit()


def log_override(event_id: str, med_order_id: str, override_reason: str, actor_role: str, doctor_id: str | None) -> None:
    init_db()
    source_system = os.getenv("SOURCE_SYSTEM", "local")
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO overrides (
                    event_id, med_order_id, override_reason, actor_role, doctor_id, sync_status, source_system
                )
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event_id, med_order_id, override_reason, actor_role, doctor_id, source_system),
            )
            conn.commit()
        return

    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO overrides (
                event_id, med_order_id, override_reason, actor_role, doctor_id, sync_status, source_system
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (event_id, med_order_id, override_reason, actor_role, doctor_id, source_system),
        )
        conn.commit()


def get_metrics() -> dict[str, Any]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            intakes = conn.execute("SELECT urgency_level, red_flags_json FROM intake_events").fetchall()
            unsafe_count = conn.execute("SELECT COUNT(*) AS c FROM dose_checks WHERE safe = FALSE").fetchone()["c"]
            override_count = conn.execute("SELECT COUNT(*) AS c FROM overrides").fetchone()["c"]
    else:
        with _sqlite_connect() as conn:
            intakes = conn.execute("SELECT urgency_level, red_flags_json FROM intake_events").fetchall()
            unsafe_count = conn.execute("SELECT COUNT(*) AS c FROM dose_checks WHERE safe = 0").fetchone()["c"]
            override_count = conn.execute("SELECT COUNT(*) AS c FROM overrides").fetchone()["c"]

    urgency_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "EMERGENCY": 0}
    red_flag_counter: Counter[str] = Counter()
    for row in intakes:
        level = (row["urgency_level"] or "").upper()
        if level in urgency_distribution:
            urgency_distribution[level] += 1
        raw_flags = row["red_flags_json"] or []
        flags = raw_flags if isinstance(raw_flags, list) else json.loads(raw_flags)
        red_flag_counter.update(flags)

    top_red_flags = [{"flag": flag, "count": count} for flag, count in red_flag_counter.most_common(5)]

    return {
        "total_intakes": len(intakes),
        "urgency_distribution": urgency_distribution,
        "top_red_flags": top_red_flags,
        "unsafe_dose_warnings": unsafe_count,
        "overrides": override_count,
    }


def list_unsynced_events(limit_per_table: int = 200) -> EventMap:
    init_db()
    events: EventMap = {table: [] for table in TABLES}
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            for table in TABLES:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE sync_status = 'pending' ORDER BY created_at ASC LIMIT %s",
                    (limit_per_table,),
                ).fetchall()
                events[table] = [dict(row) for row in rows]
        return events

    with _sqlite_connect() as conn:
        for table in TABLES:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE sync_status = 'pending' ORDER BY created_at ASC LIMIT ?",
                (limit_per_table,),
            ).fetchall()
            events[table] = [dict(row) for row in rows]
    return events


def mark_events_synced(table: str, event_ids: list[str]) -> None:
    if table not in TABLES or not event_ids:
        return
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                f"""
                UPDATE {table}
                SET sync_status = 'synced', last_synced_at = NOW()
                WHERE event_id = ANY(%s)
                """,
                (event_ids,),
            )
            conn.commit()
        return

    placeholders = ",".join("?" for _ in event_ids)
    with _sqlite_connect() as conn:
        conn.execute(
            f"""
            UPDATE {table}
            SET sync_status = 'synced', last_synced_at = CURRENT_TIMESTAMP
            WHERE event_id IN ({placeholders})
            """,
            tuple(event_ids),
        )
        conn.commit()


def create_patient(patient_id: str, full_name: str, date_of_birth: str | None, gender: str | None, phone: str | None) -> dict[str, Any]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO patients (id, full_name, date_of_birth, gender, phone)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (patient_id, full_name, date_of_birth, gender, phone),
            )
            row = conn.execute("SELECT * FROM patients WHERE id = %s", (patient_id,)).fetchone()
            conn.commit()
            return dict(row)
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO patients (id, full_name, date_of_birth, gender, phone)
            VALUES (?, ?, ?, ?, ?)
            """,
            (patient_id, full_name, date_of_birth, gender, phone),
        )
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        conn.commit()
        return dict(row)


def get_patient(patient_id: str) -> dict[str, Any] | None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            row = conn.execute("SELECT * FROM patients WHERE id = %s", (patient_id,)).fetchone()
            return dict(row) if row else None
    with _sqlite_connect() as conn:
        row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return dict(row) if row else None


def create_visit(visit_id: str, patient_id: str, visit_status: str = "open") -> dict[str, Any]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO visits (id, patient_id, visit_status)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (visit_id, patient_id, visit_status),
            )
            row = conn.execute("SELECT * FROM visits WHERE id = %s", (visit_id,)).fetchone()
            conn.commit()
            return dict(row)
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO visits (id, patient_id, visit_status)
            VALUES (?, ?, ?)
            """,
            (visit_id, patient_id, visit_status),
        )
        row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
        conn.commit()
        return dict(row)


def get_visit(visit_id: str) -> dict[str, Any] | None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            row = conn.execute("SELECT * FROM visits WHERE id = %s", (visit_id,)).fetchone()
            return dict(row) if row else None
    with _sqlite_connect() as conn:
        row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
        return dict(row) if row else None


def create_intake_record(
    intake_id: str,
    visit_id: str,
    transcript: str,
    normalized_text: str,
    structured_json: dict[str, Any],
    urgency_level: str,
    red_flags: list[str],
    summary_json: dict[str, Any],
) -> None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO intakes (
                    id, visit_id, transcript, normalized_text, structured_json, urgency_level, red_flags_json, summary_json
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    intake_id,
                    visit_id,
                    transcript,
                    normalized_text,
                    json.dumps(structured_json),
                    urgency_level,
                    json.dumps(red_flags),
                    json.dumps(summary_json),
                ),
            )
            conn.commit()
        return
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO intakes (
                id, visit_id, transcript, normalized_text, structured_json, urgency_level, red_flags_json, summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intake_id,
                visit_id,
                transcript,
                normalized_text,
                json.dumps(structured_json),
                urgency_level,
                json.dumps(red_flags),
                json.dumps(summary_json),
            ),
        )
        conn.commit()


def get_latest_intake(visit_id: str) -> dict[str, Any] | None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM intakes
                WHERE visit_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (visit_id,),
            ).fetchone()
            return dict(row) if row else None
    with _sqlite_connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM intakes
            WHERE visit_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visit_id,),
        ).fetchone()
        return dict(row) if row else None


def create_med_order(
    med_order_id: str,
    visit_id: str,
    drug_name: str,
    dose_mg_per_day: int,
    frequency_per_day: int,
    dose_check_result: dict[str, Any],
    is_safe: bool,
) -> dict[str, Any]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO med_orders (
                    id, visit_id, drug_name, dose_mg_per_day, frequency_per_day, dose_check_result, is_safe
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (med_order_id, visit_id, drug_name, dose_mg_per_day, frequency_per_day, json.dumps(dose_check_result), is_safe),
            )
            row = conn.execute("SELECT * FROM med_orders WHERE id = %s", (med_order_id,)).fetchone()
            conn.commit()
            return dict(row)
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO med_orders (
                id, visit_id, drug_name, dose_mg_per_day, frequency_per_day, dose_check_result, is_safe
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (med_order_id, visit_id, drug_name, dose_mg_per_day, frequency_per_day, json.dumps(dose_check_result), int(is_safe)),
        )
        row = conn.execute("SELECT * FROM med_orders WHERE id = ?", (med_order_id,)).fetchone()
        conn.commit()
        return dict(row)


def list_visit_med_orders(visit_id: str) -> list[dict[str, Any]]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            rows = conn.execute("SELECT * FROM med_orders WHERE visit_id = %s ORDER BY created_at DESC", (visit_id,)).fetchall()
            return [dict(r) for r in rows]
    with _sqlite_connect() as conn:
        rows = conn.execute("SELECT * FROM med_orders WHERE visit_id = ? ORDER BY created_at DESC", (visit_id,)).fetchall()
        return [dict(r) for r in rows]


def create_doctor_conversation(
    conversation_id: str,
    visit_id: str,
    transcript: str,
    structured_json: dict[str, Any],
    soap_json: dict[str, Any],
    urgency_json: dict[str, Any],
    validation_json: dict[str, Any],
    audio_reference: str | None,
) -> dict[str, Any]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO doctor_conversations (
                    id, visit_id, transcript, structured_json, soap_json, urgency_json, validation_json, audio_reference
                )
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    conversation_id,
                    visit_id,
                    transcript,
                    json.dumps(structured_json),
                    json.dumps(soap_json),
                    json.dumps(urgency_json),
                    json.dumps(validation_json),
                    audio_reference,
                ),
            )
            row = conn.execute("SELECT * FROM doctor_conversations WHERE id = %s", (conversation_id,)).fetchone()
            conn.commit()
            return dict(row)
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO doctor_conversations (
                id, visit_id, transcript, structured_json, soap_json, urgency_json, validation_json, audio_reference
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                visit_id,
                transcript,
                json.dumps(structured_json),
                json.dumps(soap_json),
                json.dumps(urgency_json),
                json.dumps(validation_json),
                audio_reference,
            ),
        )
        row = conn.execute("SELECT * FROM doctor_conversations WHERE id = ?", (conversation_id,)).fetchone()
        conn.commit()
        return dict(row)


def get_latest_doctor_conversation(visit_id: str) -> dict[str, Any] | None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM doctor_conversations
                WHERE visit_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (visit_id,),
            ).fetchone()
            return dict(row) if row else None
    with _sqlite_connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM doctor_conversations
            WHERE visit_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visit_id,),
        ).fetchone()
        return dict(row) if row else None


def add_audit_log(audit_id: str, actor_role: str, action: str, entity_type: str, entity_id: str, metadata: dict[str, Any]) -> None:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, actor_role, action, entity_type, entity_id, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                (audit_id, actor_role, action, entity_type, entity_id, json.dumps(metadata)),
            )
            conn.commit()
        return
    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO audit_logs (id, actor_role, action, entity_type, entity_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (audit_id, actor_role, action, entity_type, entity_id, json.dumps(metadata)),
        )
        conn.commit()


def list_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    if _backend() == "postgres":
        with _postgres_connect() as conn:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
            return [dict(r) for r in rows]
    with _sqlite_connect() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
