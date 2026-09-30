"""Backups: the whole platform (database plus uploaded files) in one zip,
and restoring one onto a platform that has no bookings yet (for example,
moving from a laptop to the live server)."""

import os
import shutil
import sqlite3
import tempfile
import zipfile

from flask import current_app

from . import db, files, quickbooks, util

DB_NAME = "backline.sqlite3"
# A platform only counts as empty (safe to restore onto) if these are all empty.
DATA_TABLES = ("events", "clients", "venues", "crew", "inventory_items", "vehicles", "contracts", "invoices",
               "client_requests")


def make_backup():
    """Write a backup zip to a temporary file and return its path (the caller deletes it)."""
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    snap_fd, snapshot = tempfile.mkstemp(suffix=".sqlite3")
    os.close(snap_fd)
    try:
        # SQLite's backup copies a consistent snapshot even while people are using the platform.
        target = sqlite3.connect(snapshot)
        db.get_db().backup(target)
        target.close()
        counts = {t: db.scalar(f"SELECT COUNT(*) FROM {t}") for t in DATA_TABLES}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, DB_NAME)
            folder = current_app.config["UPLOAD_FOLDER"]
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    full = os.path.join(folder, name)
                    if os.path.isfile(full):
                        zf.write(full, f"uploads/{name}")
            zf.writestr("README.txt", (
                f"{db.get_setting('company_name')} backup, made {util.fdatetime(util.now_iso())}.\n\n"
                f"{DB_NAME} is the database; uploads/ holds event documents and the logo.\n"
                "To use it, sign in to a new, empty copy of the platform and go to Settings → Backup → Restore.\n\n"
                + "\n".join(f"{t}: {n}" for t, n in counts.items()) + "\n"
            ))
    except Exception:
        os.remove(path)
        raise
    finally:
        os.remove(snapshot)
    return path


def is_empty():
    return not any(db.scalar(f"SELECT COUNT(*) FROM {t}") for t in DATA_TABLES)


def _check_database(path):
    try:
        conn = sqlite3.connect(path)
        healthy = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] if "users" in tables else 0
        conn.close()
    except sqlite3.DatabaseError:
        raise ValueError("The database in that file is damaged, so nothing was changed.") from None
    if not healthy or not {"users", "settings", "events"} <= tables:
        raise ValueError("That file doesn't contain a backup of this platform, so nothing was changed.")
    if not users:
        raise ValueError("That backup has no user accounts, so nobody could sign in afterwards. Nothing was changed.")


def _safe_upload_name(name):
    """The file name inside uploads/, or None for anything that could land outside it."""
    if not name.startswith("uploads/"):
        return None
    base = name[len("uploads/"):]
    if not base or base != os.path.basename(base) or "\\" in base or base.startswith(".") or ".." in base:
        return None
    return base


def restore(upload):
    """Replace this platform's data with a backup zip. Only for an empty
    platform. Raises ValueError (with a readable message) if it can't."""
    if not is_empty():
        raise ValueError("This platform already has bookings, so a backup can't be restored over it.")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "backup.zip")
        upload.save(zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("That isn't a backup file. Use a .zip made by Settings → Backup → Download.")
        with zipfile.ZipFile(zip_path) as zf:
            if DB_NAME not in zf.namelist():
                raise ValueError("That .zip doesn't contain a backup of this platform, so nothing was changed.")
            db_path = os.path.join(tmp, DB_NAME)
            with zf.open(DB_NAME) as src, open(db_path, "wb") as out:
                shutil.copyfileobj(src, out)
            _check_database(db_path)

            conn = db.get_db()
            conn.commit()
            source = sqlite3.connect(db_path)
            source.backup(conn)
            source.close()
            db.init_db()  # bring a backup from an older version up to date

            folder = files.upload_folder()
            restored = 0
            for info in zf.infolist():
                base = None if info.is_dir() else _safe_upload_name(info.filename)
                target = os.path.join(folder, base) if base else None
                if not target or os.path.exists(target):
                    continue
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                restored += 1
    # The QuickBooks sign-in belongs to the copy that made it; connect again here.
    quickbooks.forget_connection("")
    return restored
