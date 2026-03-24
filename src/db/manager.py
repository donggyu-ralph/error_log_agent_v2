"""Database manager for error log agent."""
import json
import uuid
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from src.config.settings import DatabaseSettings
from src.config.logging_config import get_logger
from src.models.log_entry import ErrorInfo

logger = get_logger(__name__)

psycopg2.extras.register_uuid()

INIT_SQL = """
CREATE TABLE IF NOT EXISTS error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP NOT NULL,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    traceback TEXT,
    file_path VARCHAR(500),
    line_number INT,
    function_name VARCHAR(200),
    error_type VARCHAR(200),
    source VARCHAR(20) NOT NULL,
    pod_name VARCHAR(200),
    namespace VARCHAR(100),
    service_name VARCHAR(200),
    signature VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_statistics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    hour INT NOT NULL,
    error_type VARCHAR(200),
    error_level VARCHAR(20),
    service_name VARCHAR(200),
    count INT DEFAULT 1,
    UNIQUE(date, hour, error_type, error_level, service_name)
);

CREATE TABLE IF NOT EXISTS fix_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    error_log_id UUID REFERENCES error_logs(id),
    thread_id VARCHAR(200),
    analysis TEXT,
    fix_plan JSONB,
    action VARCHAR(20),
    git_branch VARCHAR(200),
    git_commit VARCHAR(64),
    harbor_image VARCHAR(500),
    staging_result VARCHAR(20),
    production_deployed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitored_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    namespace VARCHAR(100),
    label_selector VARCHAR(200),
    log_path VARCHAR(500),
    git_repo VARCHAR(500),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_error_logs_timestamp ON error_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_service ON error_logs(service_name);
CREATE INDEX IF NOT EXISTS idx_error_logs_signature ON error_logs(signature);
CREATE INDEX IF NOT EXISTS idx_fix_history_created ON fix_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_stats_date ON error_statistics(date, hour);
"""


class DBManager:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.conn = None

    async def initialize(self) -> None:
        self.conn = psycopg2.connect(
            host=self.settings.host,
            port=self.settings.port,
            database=self.settings.database,
            user=self.settings.user,
            password=self.settings.password,
        )
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(INIT_SQL)
        logger.info("db_initialized", database=self.settings.database)

    async def close(self) -> None:
        if self.conn and not self.conn.closed:
            self.conn.close()

    # --- Error Logs ---

    async def insert_error_log(self, error: ErrorInfo) -> str:
        error_id = str(uuid.uuid4())
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO error_logs
                   (id, timestamp, level, message, traceback, file_path, line_number,
                    function_name, error_type, source, pod_name, namespace, service_name, signature)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (error_id, error.timestamp, error.level, error.message,
                 error.traceback, error.file_path, error.line_number,
                 error.function_name, error.error_type, error.source,
                 error.pod_name, error.namespace, error.service_name, error.signature),
            )
        return error_id

    async def check_duplicate(self, signature: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM error_logs WHERE signature = %s LIMIT 1",
                (signature,),
            )
            return cur.fetchone() is not None

    async def list_error_logs(
        self, service_name: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if service_name:
                cur.execute(
                    "SELECT * FROM error_logs WHERE service_name = %s ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                    (service_name, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT * FROM error_logs ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    # --- Fix History ---

    async def create_fix_history(self, error_log_id: str, thread_id: str, analysis: str, fix_plan: dict) -> str:
        fix_id = str(uuid.uuid4())
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fix_history (id, error_log_id, thread_id, analysis, fix_plan)
                   VALUES (%s, %s, %s, %s, %s)""",
                (fix_id, error_log_id, thread_id, analysis, json.dumps(fix_plan)),
            )
        return fix_id

    async def update_fix_history(self, fix_id: str, **kwargs) -> None:
        set_parts = []
        values = []
        for k, v in kwargs.items():
            set_parts.append(f"{k} = %s")
            values.append(v)
        values.append(fix_id)
        with self.conn.cursor() as cur:
            cur.execute(
                f"UPDATE fix_history SET {', '.join(set_parts)} WHERE id = %s",
                values,
            )

    async def list_fix_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM fix_history ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    # --- Error Statistics ---

    async def update_error_stats(self, error: ErrorInfo) -> None:
        ts = datetime.fromisoformat(error.timestamp) if isinstance(error.timestamp, str) else error.timestamp
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO error_statistics (date, hour, error_type, error_level, service_name, count)
                   VALUES (%s, %s, %s, %s, %s, 1)
                   ON CONFLICT (date, hour, error_type, error_level, service_name)
                   DO UPDATE SET count = error_statistics.count + 1""",
                (ts.date(), ts.hour, error.error_type, error.level, error.service_name),
            )

    async def get_error_timeline(self, days: int = 7) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT date, hour, SUM(count) as total
                   FROM error_statistics
                   WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                   GROUP BY date, hour
                   ORDER BY date, hour""",
                (days,),
            )
            return [dict(r) for r in cur.fetchall()]

    async def get_error_by_type(self, days: int = 7) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT error_type, SUM(count) as total
                   FROM error_statistics
                   WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                   GROUP BY error_type
                   ORDER BY total DESC""",
                (days,),
            )
            return [dict(r) for r in cur.fetchall()]

    # --- Monitored Services ---

    async def list_monitored_services(self) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM monitored_services ORDER BY name")
            return [dict(r) for r in cur.fetchall()]

    async def add_monitored_service(self, **kwargs) -> str:
        svc_id = str(uuid.uuid4())
        cols = ["id"] + list(kwargs.keys())
        vals = [svc_id] + list(kwargs.values())
        placeholders = ", ".join(["%s"] * len(vals))
        col_str = ", ".join(cols)
        with self.conn.cursor() as cur:
            cur.execute(f"INSERT INTO monitored_services ({col_str}) VALUES ({placeholders})", vals)
        return svc_id

    async def update_monitored_service(self, svc_id: str, **kwargs) -> None:
        set_parts = []
        values = []
        for k, v in kwargs.items():
            set_parts.append(f"{k} = %s")
            values.append(v)
        values.append(svc_id)
        with self.conn.cursor() as cur:
            cur.execute(f"UPDATE monitored_services SET {', '.join(set_parts)} WHERE id = %s", values)

    async def delete_monitored_service(self, svc_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM monitored_services WHERE id = %s", (svc_id,))
