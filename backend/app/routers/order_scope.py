"""Validate original URL tokens before FastAPI's numeric coercion."""
import re

from fastapi import HTTPException, Request


def validate_order_page_scope(request: Request) -> None:
    p=request.query_params
    for key in ("account_name","offset","limit","search","kind","from_date","to_date","drip_threshold"):
        if len(p.getlist(key))>1:
            raise HTTPException(422, f"Repeated filter: {key}")
    for key in ("instrument_ids","group_ids"):
        values=p.getlist(key)
        if len(values)>200 or len(values)!=len(set(values)) or any(not re.fullmatch(r"[1-9][0-9]*",v) or int(v)>9007199254740991 for v in values):
            raise HTTPException(422,f"Invalid {key}; use unique positive integer IDs.")
    for key in ("offset","limit"):
        if key in p and not re.fullmatch(r"0|[1-9][0-9]*",p[key]):
            raise HTTPException(422,f"Invalid {key}")
    for key in ("from_date","to_date"):
        if key in p and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",p[key]):
            raise HTTPException(422,"Transaction dates must use YYYY-MM-DD.")
