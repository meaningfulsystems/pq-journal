"""Journal entry CRUD routes."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.dependencies import require_unlocked, get_db
from app.models.db import JournalEntry, get_db as get_db_dep
from app.services.crypto import encrypt_entry, decrypt_entry
from app.services.session import SessionData
import yaml

router = APIRouter(prefix="/journal", tags=["journal"])
templates = Jinja2Templates(directory="app/templates")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entries_dir() -> Path:
    d = get_settings().entries_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_entry_file(entry_id: str, payload: dict, session: SessionData) -> str:
    """Encrypt and write a .pqj file. Returns the filename."""
    keys = session.as_key_dict()
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob = encrypt_entry(plaintext, keys["kem_pub"], keys["x25519_pub"])
    filename = f"{entry_id}.pqj"
    path = _entries_dir() / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(blob, f, separators=(",", ":"))
    os.chmod(path, 0o600)
    return filename


def _read_entry_file(filename: str, session: SessionData) -> dict:
    """Decrypt and return entry payload from a .pqj file."""
    keys = session.as_key_dict()
    path = _entries_dir() / filename
    blob = json.loads(path.read_text(encoding="utf-8"))
    plaintext = decrypt_entry(blob, keys["kem_priv"], keys["x25519_priv"])
    return json.loads(plaintext.decode("utf-8"))


def _load_prompts() -> list[dict]:
    try:
        with open(get_settings().prompts_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("prompts", [])
    except Exception:
        return []


# ── list ────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def list_entries(
    request: Request,
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    result = await db.execute(
        select(JournalEntry).order_by(JournalEntry.created_at.desc())
    )
    entries = result.scalars().all()
    cfg = get_settings()
    return templates.TemplateResponse(
        "journal_list.html",
        {
            "request": request,
            "entries": [e.to_dict() for e in entries],
            "journal_dir": str(cfg.journal_dir),
            "key_dir": session.key_dir,
        },
    )


# ── create ───────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def new_entry(
    request: Request,
    session: SessionData = Depends(require_unlocked),
):
    import random
    prompts = _load_prompts()
    prompt = random.choice(prompts) if prompts else None
    cfg = get_settings()
    return templates.TemplateResponse(
        "entry_editor.html",
        {"request": request, "entry": None, "prompt": prompt, "enable_webcam": cfg.enable_webcam, "enable_debug": cfg.enable_debug},
    )


@router.post("", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    title: str = Form(default="Untitled"),
    body: str = Form(default=""),
    tags: str = Form(default=""),
    emotion_label: str = Form(default=""),
    emotion_scores: str = Form(default="{}"),
    paragraphs_json: str = Form(default="[]"),
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    entry_id = str(uuid.uuid4())
    now = _now()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        para_list = json.loads(paragraphs_json)
    except Exception:
        para_list = []

    word_count = len(body.split())

    payload = {
        "id": entry_id,
        "title": title,
        "created": now.isoformat(),
        "modified": now.isoformat(),
        "tags": tag_list,
        "body": body,
        "paragraphs": para_list,
        "overall_emotion": emotion_label,
        "word_count": word_count,
    }

    filename = _write_entry_file(entry_id, payload, session)

    db_entry = JournalEntry(
        id=entry_id,
        title=title,
        created_at=now,
        modified_at=now,
        tags=json.dumps(tag_list),
        emotion_label=emotion_label or None,
        emotion_scores=emotion_scores if emotion_scores != "{}" else None,
        file_name=filename,
        word_count=word_count,
    )
    db.add(db_entry)
    await db.commit()

    # HTMX redirect to view the entry
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/journal/{entry_id}"
    return response


# ── autosave ─────────────────────────────────────────────────────────────────

@router.post("/autosave")
async def autosave_entry(
    request: Request,
    entry_id: str = Form(default=""),
    title: str = Form(default="Untitled"),
    body: str = Form(default=""),
    tags: str = Form(default=""),
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    now = _now()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    word_count = len(body.split())

    if entry_id:
        db_entry = await db.get(JournalEntry, entry_id)
        if db_entry is not None:
            existing = _read_entry_file(db_entry.file_name, session)
            payload = {
                **existing,
                "title": title or "Untitled",
                "modified": now.isoformat(),
                "tags": tag_list,
                "body": body,
                "word_count": word_count,
            }
            _write_entry_file(entry_id, payload, session)
            db_entry.title = title or "Untitled"
            db_entry.modified_at = now
            db_entry.tags = json.dumps(tag_list)
            db_entry.word_count = word_count
            await db.commit()
            file_path = str(_entries_dir() / db_entry.file_name)
            return JSONResponse({"id": entry_id, "saved_at": now.isoformat(), "file_path": file_path})

    # Create new entry
    entry_id = str(uuid.uuid4())
    payload = {
        "id": entry_id,
        "title": title or "Untitled",
        "created": now.isoformat(),
        "modified": now.isoformat(),
        "tags": tag_list,
        "body": body,
        "paragraphs": [],
        "overall_emotion": "",
        "word_count": word_count,
    }
    filename = _write_entry_file(entry_id, payload, session)
    db_entry = JournalEntry(
        id=entry_id,
        title=title or "Untitled",
        created_at=now,
        modified_at=now,
        tags=json.dumps(tag_list),
        file_name=filename,
        word_count=word_count,
    )
    db.add(db_entry)
    await db.commit()
    file_path = str(_entries_dir() / filename)
    return JSONResponse({"id": entry_id, "saved_at": now.isoformat(), "created": True, "file_path": file_path})


# ── search ───────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_entries(
    request: Request,
    q: str = "",
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    """SSE endpoint: decrypts each entry and streams matches back to the client."""
    query = q.strip().lower()

    async def generate():
        if not query:
            yield {"data": json.dumps({"done": True, "total": 0})}
            return

        result = await db.execute(
            select(JournalEntry).order_by(JournalEntry.created_at.desc())
        )
        entries = result.scalars().all()
        total = len(entries)
        yield {"data": json.dumps({"total": total})}

        for i, entry in enumerate(entries):
            # Check metadata without decryption first
            tag_str = entry.tags or "[]"
            meta_hit = (
                query in (entry.title or "").lower()
                or query in tag_str.lower()
                or query in (entry.emotion_label or "").lower()
            )

            excerpt = ""
            body_hit = False
            if not meta_hit:
                try:
                    payload = _read_entry_file(entry.file_name, session)
                    body = payload.get("body", "")
                    idx = body.lower().find(query)
                    if idx != -1:
                        body_hit = True
                        start = max(0, idx - 60)
                        end = min(len(body), idx + 120)
                        excerpt = ("…" if start > 0 else "") + body[start:end].strip() + ("…" if end < len(body) else "")
                except Exception:
                    pass

            yield {"data": json.dumps({"progress": i + 1, "total": total})}

            if meta_hit or body_hit:
                try:
                    tags = json.loads(entry.tags or "[]")
                except Exception:
                    tags = []
                yield {"data": json.dumps({
                    "id": entry.id,
                    "title": entry.title or "Untitled",
                    "created_at": entry.created_at.isoformat() if entry.created_at else "",
                    "tags": tags,
                    "emotion_label": entry.emotion_label or "",
                    "excerpt": excerpt,
                })}

            await asyncio.sleep(0)  # keep event loop unblocked

        yield {"data": json.dumps({"done": True, "total": total})}

    return EventSourceResponse(generate())


# ── view ─────────────────────────────────────────────────────────────────────

@router.get("/{entry_id}", response_class=HTMLResponse)
async def view_entry(
    request: Request,
    entry_id: str,
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    db_entry = await db.get(JournalEntry, entry_id)
    if db_entry is None:
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": "Entry not found"}, status_code=404
        )
    payload = _read_entry_file(db_entry.file_name, session)
    return templates.TemplateResponse(
        "entry_view.html",
        {"request": request, "entry": payload, "meta": db_entry.to_dict()},
    )


# ── edit ─────────────────────────────────────────────────────────────────────

@router.get("/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry(
    request: Request,
    entry_id: str,
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    db_entry = await db.get(JournalEntry, entry_id)
    if db_entry is None:
        return templates.TemplateResponse(
            "error.html", {"request": request, "message": "Entry not found"}, status_code=404
        )
    payload = _read_entry_file(db_entry.file_name, session)
    import random
    prompts = _load_prompts()
    prompt = random.choice(prompts) if prompts else None
    cfg = get_settings()
    return templates.TemplateResponse(
        "entry_editor.html",
        {
            "request": request,
            "entry": payload,
            "meta": db_entry.to_dict(),
            "prompt": prompt,
            "enable_webcam": cfg.enable_webcam,
            "enable_debug": cfg.enable_debug,
        },
    )


@router.put("/{entry_id}", response_class=HTMLResponse)
async def update_entry(
    request: Request,
    entry_id: str,
    title: str = Form(default="Untitled"),
    body: str = Form(default=""),
    tags: str = Form(default=""),
    emotion_label: str = Form(default=""),
    emotion_scores: str = Form(default="{}"),
    paragraphs_json: str = Form(default="[]"),
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    db_entry = await db.get(JournalEntry, entry_id)
    if db_entry is None:
        return Response(status_code=404)

    now = _now()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        para_list = json.loads(paragraphs_json)
    except Exception:
        para_list = []

    word_count = len(body.split())

    # Read existing to preserve created timestamp
    existing = _read_entry_file(db_entry.file_name, session)

    payload = {
        **existing,
        "title": title,
        "modified": now.isoformat(),
        "tags": tag_list,
        "body": body,
        "paragraphs": para_list,
        "overall_emotion": emotion_label,
        "word_count": word_count,
    }

    _write_entry_file(entry_id, payload, session)

    db_entry.title = title
    db_entry.modified_at = now
    db_entry.tags = json.dumps(tag_list)
    db_entry.emotion_label = emotion_label or None
    db_entry.emotion_scores = emotion_scores if emotion_scores != "{}" else None
    db_entry.word_count = word_count
    await db.commit()

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/journal/{entry_id}"
    return response


# ── delete ────────────────────────────────────────────────────────────────────

@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: str,
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    db_entry = await db.get(JournalEntry, entry_id)
    if db_entry is None:
        return Response(status_code=404)

    # Delete the .pqj file
    file_path = _entries_dir() / db_entry.file_name
    if file_path.exists():
        file_path.unlink()

    await db.delete(db_entry)
    await db.commit()

    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/journal"
    return response


# ── export ────────────────────────────────────────────────────────────────────

@router.get("/{entry_id}/export")
async def export_entry(
    entry_id: str,
    format: str = "md",
    session: SessionData = Depends(require_unlocked),
    db: AsyncSession = Depends(get_db_dep),
):
    db_entry = await db.get(JournalEntry, entry_id)
    if db_entry is None:
        return Response(status_code=404)

    payload = _read_entry_file(db_entry.file_name, session)

    if format == "md":
        from app.services.export import to_markdown
        content = to_markdown(payload)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in payload.get("title", "entry"))
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.md"'},
        )
    elif format == "pdf":
        try:
            from app.services.export import to_pdf
            content = to_pdf(payload)
            safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in payload.get("title", "entry"))
            return Response(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
            )
        except ImportError:
            return Response(content="PDF export requires weasyprint: pip install weasyprint", status_code=400)
    else:
        return Response(status_code=400, content="Unsupported format")


# ── prompts ───────────────────────────────────────────────────────────────────

@router.get("/prompts/random", response_class=HTMLResponse)
async def random_prompt(
    request: Request,
    session: SessionData = Depends(require_unlocked),
):
    import random
    prompts = _load_prompts()
    prompt = random.choice(prompts) if prompts else {"text": "What do you want to explore today?", "category": "open"}
    return templates.TemplateResponse(
        "components/prompt_sidebar.html",
        {"request": request, "prompt": prompt},
    )
