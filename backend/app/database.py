from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


def safe_migrate_db(sync_conn):
    """Idempotent SQLite column migrations preserving compatibility with existing stored data."""
    migrations = {
        "transactions": [
            ("anomaly_explanation", "TEXT"),
            ("anomaly_feedback_status", "VARCHAR(50)"),
            ("anomaly_alert_type", "VARCHAR(50)"),
            ("anomaly_confidence", "FLOAT"),
        ],
        "business_profiles": [
            ("operating_model", "VARCHAR(100) DEFAULT 'B2B'"),
            ("relevant_expense_categories", "JSON"),
        ],
        "documents": [
            ("file_hash", "VARCHAR(64)"),
            ("raw_text", "TEXT"),
            ("extraction_metadata", "JSON"),
        ],
    }
    for table_name, columns in migrations.items():
        try:
            res = sync_conn.execute(text(f"PRAGMA table_info({table_name});"))
            existing_cols = {r[1] for r in res.fetchall()}
            if not existing_cols:
                continue
            for col_name, col_def in columns:
                if col_name not in existing_cols:
                    sync_conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};"))
        except Exception as e:
            print(f"[safe_migrate_db] Migration notice for {table_name}: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
