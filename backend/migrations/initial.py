from sqlalchemy import text, select
from src.config.database import Base, engine, Session
from src import models
NEW_COLUMNS = [
    ('datasets', 'current_version', 'INTEGER NOT NULL DEFAULT 1'),
    ('jobs', 'dataset_version', 'INTEGER NOT NULL DEFAULT 1'),
    ('jobs', 'stale', 'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('jobs', 'recalc_of', 'INTEGER NULL'),
    ('reports', 'paused', 'BOOLEAN NOT NULL DEFAULT FALSE'),
]
def ensure_columns():
    # create_all 不会给已有表加列，这里做幂等补齐，兼容 SQLite 与 MySQL
    with engine.begin() as conn:
        for table, column, ddl in NEW_COLUMNS:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
            except Exception:
                pass  # 列已存在
def ensure_revisions():
    # 历史批次没有版本记录时，按当前内容补齐 v1 快照，保证每个批次都可追溯
    from src.models import Dataset, DatasetRevision
    with Session() as db:
        for d in db.scalars(select(Dataset)):
            if not db.scalar(select(DatasetRevision.id).where(DatasetRevision.dataset_id == d.id)):
                db.add(DatasetRevision(dataset_id=d.id, version=1, action='import', reason='初始导入（历史数据补齐版本快照）', records=d.records, checksum=d.checksum, created_by=None, created_at=d.created_at))
        db.commit()
def migrate():
    Base.metadata.create_all(engine)
    ensure_columns()
    ensure_revisions()
if __name__=='__main__':migrate()
