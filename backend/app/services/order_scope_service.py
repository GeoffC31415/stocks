"""Account scope follows existing instrument links, never guessed account aliases."""
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import Instrument, Order


def order_account_scope(account_name: str) -> ColumnElement[bool]:
    return or_(Order.account_name == account_name,
               Order.instrument.has(Instrument.account_name == account_name))
