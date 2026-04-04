from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC)
    )
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    diff_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    snapshots: Mapped[list[HoldingSnapshot]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("account_name", "identifier", name="uq_account_identifier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(String(512), index=True)
    identifier: Mapped[str] = mapped_column(String(128), index=True)
    security_name: Mapped[str] = mapped_column(String(1024))
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC)
    )

    snapshots: Mapped[list[HoldingSnapshot]] = relationship(back_populates="instrument")
    orders: Mapped[list[Order]] = relationship(back_populates="instrument")
    group_links: Mapped[list[InstrumentGroupMember]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )


class HoldingSnapshot(Base):
    __tablename__ = "holding_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))

    investment_label: Mapped[str] = mapped_column(String(1024))
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_ccy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_ccy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fx_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_pence: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_cost_ccy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    average_fx_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_cost_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)

    batch: Mapped[ImportBatch] = relationship(back_populates="snapshots")
    instrument: Mapped[Instrument] = relationship(back_populates="snapshots")


class OrderImportBatch(Base):
    __tablename__ = "order_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC)
    )
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)

    orders: Mapped[list["Order"]] = relationship(
        back_populates="import_batch", cascade="all, delete-orphan"
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("order_import_batches.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    security_name: Mapped[str] = mapped_column(String(1024), index=True)
    order_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    order_status: Mapped[str] = mapped_column(String(64))
    account_name: Mapped[str] = mapped_column(String(512))
    side: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_proceeds_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_drip: Mapped[bool] = mapped_column(Boolean, default=False)

    import_batch: Mapped[OrderImportBatch] = relationship(back_populates="orders")
    instrument: Mapped[Instrument | None] = relationship(back_populates="orders")


class InstrumentGroup(Base):
    __tablename__ = "instrument_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC)
    )

    members: Mapped[list[InstrumentGroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class InstrumentGroupMember(Base):
    __tablename__ = "instrument_group_members"
    __table_args__ = (UniqueConstraint("group_id", "instrument_id", name="uq_group_instrument"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("instrument_groups.id", ondelete="CASCADE"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))

    group: Mapped[InstrumentGroup] = relationship(back_populates="members")
    instrument: Mapped[Instrument] = relationship(back_populates="group_links")
