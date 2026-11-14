from sqlalchemy import String, JSON, Double, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    current_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[float] = mapped_column(Double)
class DatasetRevision(Base):
    __tablename__ = 'dataset_revisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    version: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(20), default='import')  # import / correct / withdraw
    reason: Mapped[str] = mapped_column(String(500), default='')
    records: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
