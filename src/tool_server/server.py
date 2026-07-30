# server.py — the CRM tool-server.
from __future__ import annotations

import argparse
import logging
import sqlite3
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP

from src.tool_server import services
from src.tool_server.envelope import APIResponse
from src.tool_server.models import (
    CreateContactArgs, CreateDealArgs, CreateLeadArgs, FindContactsArgs,
    FindDealsArgs, FindLeadsArgs, GetActivitiesArgs, GetByIdArgs,
    GetFollowupsArgs, LogActivityArgs, ScheduleFollowupArgs, UpdateContactArgs,
    UpdateDealArgs, UpdateFollowupArgs, UpdateLeadArgs,
)

logger = logging.getLogger("tool_server")

_conn: sqlite3.Connection | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _conn
    _conn = sqlite3.connect(app.state.db_path)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA foreign_keys=ON")
    yield
    _conn.close()


app = FastAPI(title="CRM Tool Server", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p != "body")
        details.append(f"{loc or '<root>'}: {err['msg']} (type={err['type']})")
    technical_message = "; ".join(details) or "request validation failed"
    resp = APIResponse.fail(code="validation_error", technical_message=technical_message)
    return JSONResponse(status_code=200, content=resp.model_dump())


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.exception("unhandled exception in %s", request.url.path)
    resp = APIResponse.fail(code="internal_error", technical_message=f"{type(exc).__name__}: {exc}")
    return JSONResponse(status_code=200, content=resp.model_dump())


@app.post("/list_reps", operation_id="list_reps")
async def list_reps():
    """List every sales rep."""
    return services.list_reps(_conn)


@app.post("/find_contacts", operation_id="find_contacts")
async def find_contacts(args: FindContactsArgs):
    """Search contacts by name, email, company, or rep. All arguments are optional — omit any you don't need."""
    return services.find_contacts(_conn, args)


@app.post("/get_contact", operation_id="get_contact")
async def get_contact(args: GetByIdArgs):
    """Fetch one contact by id."""
    return services.get_contact(_conn, args)


@app.post("/find_leads", operation_id="find_leads")
async def find_leads(args: FindLeadsArgs):
    """Search leads by contact, rep, status, or minimum score. All arguments are optional — omit any you don't need."""
    return services.find_leads(_conn, args)


@app.post("/get_lead", operation_id="get_lead")
async def get_lead(args: GetByIdArgs):
    """Fetch one lead by id."""
    return services.get_lead(_conn, args)


@app.post("/get_deal", operation_id="get_deal")
async def get_deal(args: GetByIdArgs):
    """Fetch one deal by id."""
    return services.get_deal(_conn, args)


@app.post("/find_deals", operation_id="find_deals")
async def find_deals(args: FindDealsArgs):
    """Search deals by lead, stage, rep, or minimum value. All arguments are optional — omit any you don't need."""
    return services.find_deals(_conn, args)


@app.post("/get_activities", operation_id="get_activities")
async def get_activities(args: GetActivitiesArgs):
    """List activities for a deal or a contact. One of deal_id/contact_id is required (not both need to be set, but at least one must be)."""
    return services.get_activities(_conn, args)


@app.post("/get_followups", operation_id="get_followups")
async def get_followups(args: GetFollowupsArgs):
    """Search follow-ups by deal, rep, or status. All arguments are optional — omit any you don't need."""
    return services.get_followups(_conn, args)


@app.post("/create_contact", operation_id="create_contact")
async def create_contact(args: CreateContactArgs):
    """Create a new contact; fails if the email already exists."""
    return services.create_contact(_conn, args)


@app.post("/update_contact", operation_id="update_contact")
async def update_contact(args: UpdateContactArgs):
    """Update one or more fields on an existing contact. Only the fields you pass are changed."""
    return services.update_contact(_conn, args)


@app.post("/create_lead", operation_id="create_lead")
async def create_lead(args: CreateLeadArgs):
    """Create a new lead for a contact."""
    return services.create_lead(_conn, args)


@app.post("/update_lead", operation_id="update_lead")
async def update_lead(args: UpdateLeadArgs):
    """Update a lead's status, score, and/or source. Only the fields you pass are changed."""
    return services.update_lead(_conn, args)


@app.post("/create_deal", operation_id="create_deal")
async def create_deal(args: CreateDealArgs):
    """Create a new deal under a lead."""
    return services.create_deal(_conn, args)


@app.post("/update_deal", operation_id="update_deal")
async def update_deal(args: UpdateDealArgs):
    """Update a deal's stage, value, and/or close date. Only the fields you pass are changed."""
    return services.update_deal(_conn, args)


@app.post("/log_activity", operation_id="log_activity")
async def log_activity(args: LogActivityArgs):
    """Log a call, email, meeting, or note on a deal or contact. At least one of deal_id/contact_id should be set; if you pass only deal_id, contact_id is filled in automatically from the deal's contact."""
    return services.log_activity(_conn, args)


@app.post("/schedule_followup", operation_id="schedule_followup")
async def schedule_followup(args: ScheduleFollowupArgs):
    """Schedule a follow-up on a deal."""
    return services.schedule_followup(_conn, args)


@app.post("/update_followup", operation_id="update_followup")
async def update_followup(args: UpdateFollowupArgs):
    """Update a follow-up's status (e.g. mark done), due date, and/or note."""
    return services.update_followup(_conn, args)


mcp = FastApiMCP(app)
mcp.mount_http()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app.state.db_path = args.db_path
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
