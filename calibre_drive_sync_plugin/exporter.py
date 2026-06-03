import datetime as dt
import json
import shutil
from pathlib import Path


INDEX_SCHEMA_VERSION = "1.0.0"
STATE_FILE_NAME = ".calibre_drive_sync_state.json"
CONTENT_FOLDER_NAME = "books"


def _normalize_formats(raw_formats):
    if not raw_formats:
        return []
    if isinstance(raw_formats, str):
        items = raw_formats.split(",")
    else:
        try:
            items = list(raw_formats)
        except TypeError:
            items = [raw_formats]
    return [str(fmt).strip().lower() for fmt in items if str(fmt).strip()]


def _safe_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    return str(value)


def _get_custom_columns(db, book_id):
    custom = {}
    try:
        for key in db.field_metadata.custom_field_keys():
            value = db.field_for(key, book_id, default_value=None)
            custom[str(key)] = _safe_value(value)
    except Exception:
        return custom
    return custom


def _book_formats(db, book_id):
    try:
        formats_raw = db.formats(book_id)
    except Exception:
        formats_raw = None

    formats = _normalize_formats(formats_raw)

    files = {}
    for fmt in formats:
        try:
            files[fmt] = db.format_abspath(book_id, fmt)
        except Exception:
            continue
    return files


def _all_book_formats(db, book_id):
    try:
        formats_raw = db.formats(book_id)
    except Exception:
        formats_raw = None

    formats = _normalize_formats(formats_raw)
    if not formats:
        return {}

    return _book_formats(db, book_id)


def _file_signature(path: Path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _load_state(path: Path):
    if not path.exists():
        return {"files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}


def _save_state(path: Path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_if_changed(source_path: Path, target_path: Path, state):
    key = str(source_path)
    files_state = state.setdefault("files", {})
    source_sig = _file_signature(source_path)
    old = files_state.get(key)

    if old and old.get("signature") == source_sig and target_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_path), str(target_path))
    files_state[key] = {"signature": source_sig, "target": str(target_path)}
    return True


def _report_progress(callback, stage, current, total, message):
    if callback is None:
        return False
    try:
        return bool(callback(stage, current, total, message))
    except Exception:
        return False


def export_index(db, output_path: Path):
    books = []
    ids = sorted(db.all_book_ids())

    for book_id in ids:
        mi = db.get_metadata(book_id)
        try:
            identifiers = mi.get_identifiers() or {}
        except Exception:
            identifiers = {}

        authors = list(mi.authors or [])
        author_sort = []
        if getattr(mi, "author_sort", None):
            author_sort = [x.strip() for x in str(mi.author_sort).split("&") if x.strip()]

        relative_dir = None
        try:
            relative_dir = db.path(book_id)
        except Exception:
            relative_dir = None

        if not relative_dir:
            relative_dir = str(book_id)

        books.append(
            {
                "book_id": str(book_id),
                "title": mi.title or "(untitled)",
                "title_sort": getattr(mi, "title_sort", None) or mi.title or "(untitled)",
                "authors": authors,
                "author_sort": author_sort,
                "series": getattr(mi, "series", None),
                "series_index": _safe_value(getattr(mi, "series_index", None)),
                "tags": list(mi.tags or []),
                "rating": _safe_value(getattr(mi, "rating", None)),
                "languages": list(getattr(mi, "languages", None) or []),
                "publisher": getattr(mi, "publisher", None),
                "pubdate": _safe_value(getattr(mi, "pubdate", None)),
                "timestamp": _safe_value(getattr(mi, "timestamp", None)),
                "identifiers": _safe_value(identifiers),
                "custom_columns": _get_custom_columns(db, book_id),
                "relative_dir": str(relative_dir).replace("\\", "/"),
                "cover_local_path": None,
                "format_files": _book_formats(db, book_id),
                "drive_files": {},
            }
        )

        try:
            books[-1]["cover_local_path"] = db.cover(book_id, as_path=True)
        except Exception:
            pass

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source": "calibre-db-plugin",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "book_count": len(books),
        "books": books,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(books)


def export_and_sync_local(db, sync_root: Path, formats=None, include_cover=True, progress_callback=None):
    wanted_formats = None
    if formats is not None:
        wanted_formats = {str(fmt).lower().strip() for fmt in formats if str(fmt).strip()}
        if not wanted_formats or wanted_formats == {"all"}:
            wanted_formats = None

    sync_root = sync_root.expanduser().resolve()
    library_root = sync_root / CONTENT_FOLDER_NAME
    index_path = sync_root / "index.json"
    state_path = sync_root / STATE_FILE_NAME
    state = _load_state(state_path)

    ids = sorted(db.all_book_ids())
    entries = []
    copied_count = 0

    total_steps = 1  # index.json write
    _report_progress(progress_callback, "scan", 0, len(ids), "Scanning library")

    for book_id in ids:
        mi = db.get_metadata(book_id)
        try:
            identifiers = mi.get_identifiers() or {}
        except Exception:
            identifiers = {}

        authors = list(mi.authors or [])
        author_sort = []
        if getattr(mi, "author_sort", None):
            author_sort = [x.strip() for x in str(mi.author_sort).split("&") if x.strip()]

        try:
            relative_dir = db.path(book_id)
        except Exception:
            relative_dir = None
        if not relative_dir:
            relative_dir = str(book_id)
        relative_dir = str(relative_dir).replace("\\", "/")

        if wanted_formats is None:
            format_sources = _all_book_formats(db, book_id)
        else:
            format_sources = {}
            for fmt in sorted(wanted_formats):
                try:
                    source_format_path = db.format_abspath(book_id, fmt)
                except Exception:
                    source_format_path = None
                if source_format_path:
                    format_sources[fmt] = source_format_path

        total_steps += len(format_sources)

        cover_source_path = None
        if include_cover:
            try:
                cover_source_path = db.cover(book_id, as_path=True)
            except Exception:
                cover_source_path = None
            if cover_source_path:
                total_steps += 1

        entries.append(
            {
                "book_id": str(book_id),
                "title": mi.title or "(untitled)",
                "title_sort": getattr(mi, "title_sort", None) or mi.title or "(untitled)",
                "authors": authors,
                "author_sort": author_sort,
                "series": getattr(mi, "series", None),
                "series_index": _safe_value(getattr(mi, "series_index", None)),
                "tags": list(mi.tags or []),
                "rating": _safe_value(getattr(mi, "rating", None)),
                "languages": list(getattr(mi, "languages", None) or []),
                "publisher": getattr(mi, "publisher", None),
                "pubdate": _safe_value(getattr(mi, "pubdate", None)),
                "timestamp": _safe_value(getattr(mi, "timestamp", None)),
                "identifiers": _safe_value(identifiers),
                "custom_columns": _get_custom_columns(db, book_id),
                "relative_dir": relative_dir,
                "book_target_dir": str(library_root / Path(relative_dir)),
                "cover_source_path": cover_source_path,
                "cover_local_path": None,
                "format_sources": format_sources,
                "format_files": {},
                "drive_files": {},
            }
        )

    books = []
    current_step = 0

    for idx, entry in enumerate(entries, start=1):
        if _report_progress(progress_callback, "book", current_step, total_steps, f"{idx}/{len(entries)}: {entry['title']}"):
            return {
                "books": len(books),
                "files_copied": copied_count,
                "index_path": str(index_path),
                "canceled": True,
            }

        book_target_dir = Path(entry["book_target_dir"])
        sync_files = {}

        for fmt, source_format_path in sorted(entry["format_sources"].items()):
            source_path = Path(source_format_path)
            target_path = book_target_dir / source_path.name
            if _copy_if_changed(source_path, target_path, state):
                copied_count += 1
            sync_files[fmt] = str(target_path.relative_to(sync_root)).replace("\\", "/")
            current_step += 1
            if _report_progress(progress_callback, "file", current_step, total_steps, f"{entry['title']}: {fmt.upper()}"):
                return {
                    "books": len(books),
                    "files_copied": copied_count,
                    "index_path": str(index_path),
                    "canceled": True,
                }

        cover_sync_rel = None
        if entry["cover_source_path"]:
            source_cover = Path(entry["cover_source_path"])
            target_cover = book_target_dir / source_cover.name
            if _copy_if_changed(source_cover, target_cover, state):
                copied_count += 1
            cover_sync_rel = str(target_cover.relative_to(sync_root)).replace("\\", "/")
            current_step += 1
            if _report_progress(progress_callback, "file", current_step, total_steps, f"{entry['title']}: COVER"):
                return {
                    "books": len(books),
                    "files_copied": copied_count,
                    "index_path": str(index_path),
                    "canceled": True,
                }

        entry["cover_local_path"] = cover_sync_rel
        entry["format_files"] = sync_files
        entry.pop("book_target_dir", None)
        entry.pop("cover_source_path", None)
        entry.pop("format_sources", None)
        books.append(entry)
        _report_progress(progress_callback, "book", current_step, total_steps, f"Completed: {entry['title']}")

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source": "calibre-db-plugin-local-sync",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "book_count": len(books),
        "library_root": str(sync_root),
        "sync_root": str(sync_root),
        "books": books,
    }

    sync_root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    content_index_path = library_root / "index.json"
    content_index_path.parent.mkdir(parents=True, exist_ok=True)
    content_index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_state(state_path, state)

    _report_progress(progress_callback, "done", total_steps, total_steps, "Synchronization finished")

    return {
        "books": len(books),
        "files_copied": copied_count,
        "index_path": str(index_path),
        "canceled": False,
    }
