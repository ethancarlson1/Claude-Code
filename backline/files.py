"""Event documents on disk: stage plots, input lists, tech packs, maps...

Files are stored under the uploads folder with random names (the original
name is kept in the database for display and downloads), so user-supplied
filenames never touch the filesystem."""

import mimetypes
import os
import uuid

from flask import current_app, send_from_directory

from . import db, util

ALLOWED_EXTENSIONS = {
    # documents
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "rtf", "ppt", "pptx", "pages", "numbers", "key",
    # images
    "png", "jpg", "jpeg", "gif", "webp", "heic",
    # stage plot / CAD files
    "vwx", "dwg", "dxf",
    "zip",
}
# Shown in the browser; everything else downloads. (No HTML or SVG: they can carry scripts.)
INLINE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "txt"}


def extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def upload_folder():
    path = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(path, exist_ok=True)
    return path


def save_event_file(event_id, filename, data, category="Other", description=None, source=None,
                    crew_visible=True, uploaded_by=None):
    """Store an uploaded file (a werkzeug FileStorage or raw bytes) for an event.
    Raises ValueError with a readable message if it can't be accepted."""
    original = os.path.basename((filename or "").replace("\\", "/")).strip()[:200]
    ext = extension(original)
    if not original or ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"{original or 'That file'}: this file type isn't accepted.")
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(upload_folder(), stored)
    if hasattr(data, "save"):
        data.save(path)
    else:
        with open(path, "wb") as fh:
            fh.write(data)
    size = os.path.getsize(path)
    if size == 0:
        os.remove(path)
        raise ValueError(f"{original} is empty.")
    return db.insert("event_files", {
        "event_id": event_id, "category": category, "description": description or None, "source": source or None,
        "original_name": original, "stored_name": stored, "size": size, "crew_visible": 1 if crew_visible else 0,
        "uploaded_by": uploaded_by, "uploaded_at": util.now_iso(),
    })


def event_files(event_id, crew_only=False):
    return db.query(
        f"""SELECT * FROM event_files WHERE event_id = ? {'AND crew_visible = 1' if crew_only else ''}
            ORDER BY category, uploaded_at, id""",
        (event_id,),
    )


def _remove_from_disk(row):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], row["stored_name"])
    if os.path.exists(path):
        os.remove(path)


def delete_event_file(row):
    _remove_from_disk(row)
    db.execute("DELETE FROM event_files WHERE id = ?", (row["id"],))


def delete_all_event_files(event_id):
    """Remove an event's files from disk (the rows go with the event)."""
    for row in event_files(event_id):
        _remove_from_disk(row)


def send_event_file(row):
    ext = extension(row["stored_name"])
    response = send_from_directory(
        current_app.config["UPLOAD_FOLDER"], row["stored_name"],
        mimetype=mimetypes.guess_type(row["original_name"])[0] or "application/octet-stream",
        as_attachment=ext not in INLINE_EXTENSIONS, download_name=row["original_name"], max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def filesize(num):
    for unit in ("bytes", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "bytes" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num} bytes"
