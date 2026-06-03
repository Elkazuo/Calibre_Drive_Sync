#!/usr/bin/env python3
"""Sync a Calibre library to Google Drive.

What this script does:
1. Scans a Calibre library folder for metadata.opf files.
2. Builds an index.json with searchable metadata.
3. Optionally uploads index.json, covers, and selected formats (default: EPUB)
   to a target Google Drive folder.

Usage example:
python sync_calibre_to_drive.py \
  --library "E:/Calibre Library" \
  --drive-folder-id "YOUR_DRIVE_FOLDER_ID" \
  --credentials "credentials.json" \
  --upload-files
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET


OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NS = {"opf": OPF_NS, "dc": DC_NS}

SCOPES = ["https://www.googleapis.com/auth/drive"]
INDEX_SCHEMA_VERSION = "1.0.0"


@dataclass
class BookRecord:
    book_id: str
    title: str
    title_sort: str
    authors: List[str]
    author_sort: List[str]
    series: Optional[str]
    series_index: Optional[float]
    tags: List[str]
    rating: Optional[float]
    languages: List[str]
    publisher: Optional[str]
    pubdate: Optional[str]
    timestamp: Optional[str]
    identifiers: Dict[str, str]
    custom_columns: Dict[str, Any]
    relative_dir: str
    cover_local_path: Optional[str]
    format_files: Dict[str, str]
    drive_files: Dict[str, Dict[str, str]] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export and sync Calibre metadata to Google Drive")
    parser.add_argument("--library", required=True, help="Path to Calibre library root")
    parser.add_argument("--drive-folder-id", help="Target Google Drive folder ID")
    parser.add_argument("--credentials", default="credentials.json", help="OAuth client credentials JSON")
    parser.add_argument("--token", default="token.json", help="OAuth token cache file")
    parser.add_argument("--output-index", default="index.json", help="Output index JSON path")
    parser.add_argument(
        "--formats",
        default="epub",
        help="Comma-separated formats to sync (example: epub,pdf,mobi)",
    )
    parser.add_argument("--upload-files", action="store_true", help="Upload index + files to Drive")
    parser.add_argument("--max-books", type=int, default=0, help="Limit processed books (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Show actions but do not upload")
    parser.add_argument(
        "--populate-drive-ids",
        action="store_true",
        help=(
            "Query Drive to find existing file IDs for all books, populate drive_files in the index, "
            "and upload only the updated index.json — without re-uploading any book files. "
            "Use this when books are already on Drive but the index was generated without Drive file IDs."
        ),
    )
    return parser.parse_args()


def text_or_none(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    text = (el.text or "").strip()
    return text if text else None


def collect_dc_texts(metadata: ET.Element, tag: str) -> List[str]:
    items = metadata.findall(f"dc:{tag}", NS)
    out = []
    for item in items:
        val = text_or_none(item)
        if val:
            out.append(val)
    return out


def parse_meta_pairs(metadata: ET.Element) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for meta in metadata.findall("opf:meta", NS):
        name = meta.attrib.get("name")
        content = meta.attrib.get("content")
        if name and content is not None:
            pairs[name] = content

    # Some OPF files may not have namespace-bound meta elements.
    for meta in metadata.findall("meta"):
        name = meta.attrib.get("name")
        content = meta.attrib.get("content")
        if name and content is not None:
            pairs[name] = content

    return pairs


def parse_identifiers(metadata: ET.Element) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for ident in metadata.findall("dc:identifier", NS):
        key = ident.attrib.get(f"{{{OPF_NS}}}scheme") or ident.attrib.get("id") or "identifier"
        value = text_or_none(ident)
        if value:
            out[key.lower()] = value
    return out


def parse_author_sort(metadata: ET.Element) -> List[str]:
    out: List[str] = []
    for creator in metadata.findall("dc:creator", NS):
        file_as = creator.attrib.get(f"{{{OPF_NS}}}file-as")
        if file_as:
            out.append(file_as)
    return out


def safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_custom_columns(meta_pairs: Dict[str, str]) -> Dict[str, Any]:
    custom: Dict[str, Any] = {}
    for key, value in meta_pairs.items():
        if key.startswith("calibre:#"):
            # Keep the # prefix so Android filters can map exactly to Calibre custom columns.
            column_name = "#" + key.replace("calibre:#", "", 1)
            custom[column_name] = value
    return custom


def discover_formats(book_dir: Path, wanted_formats: List[str]) -> Dict[str, str]:
    wanted = {fmt.lower().strip() for fmt in wanted_formats if fmt.strip()}
    found: Dict[str, str] = {}
    for file in book_dir.iterdir():
        if not file.is_file():
            continue
        suffix = file.suffix.lower().lstrip(".")
        if suffix in wanted:
            found[suffix] = str(file)
    return found


def parse_book_from_opf(opf_path: Path, library_root: Path, formats: List[str]) -> BookRecord:
    tree = ET.parse(opf_path)
    root = tree.getroot()
    metadata = root.find("opf:metadata", NS)
    if metadata is None:
        metadata = root.find("metadata")
    if metadata is None:
        raise ValueError(f"metadata section not found in {opf_path}")

    meta_pairs = parse_meta_pairs(metadata)
    title = text_or_none(metadata.find("dc:title", NS)) or "(untitled)"
    title_sort = meta_pairs.get("calibre:title_sort", title)
    authors = collect_dc_texts(metadata, "creator")
    author_sort = parse_author_sort(metadata)
    tags = collect_dc_texts(metadata, "subject")
    languages = collect_dc_texts(metadata, "language")
    publisher = text_or_none(metadata.find("dc:publisher", NS))
    pubdate = text_or_none(metadata.find("dc:date", NS))
    identifiers = parse_identifiers(metadata)

    series = meta_pairs.get("calibre:series")
    series_index = safe_float(meta_pairs.get("calibre:series_index"))
    rating = safe_float(meta_pairs.get("calibre:rating"))
    timestamp = meta_pairs.get("calibre:timestamp")

    calibre_book_id = meta_pairs.get("calibre:book_id") or identifiers.get("calibre")
    if not calibre_book_id:
        calibre_book_id = str(opf_path.parent.relative_to(library_root)).replace("\\", "/")

    cover_path: Optional[str] = None
    for cover_name in ["cover.jpg", "cover.jpeg", "cover.png"]:
        candidate = opf_path.parent / cover_name
        if candidate.exists():
            cover_path = str(candidate)
            break

    book_dir_rel = str(opf_path.parent.relative_to(library_root)).replace("\\", "/")
    format_files = discover_formats(opf_path.parent, formats)

    return BookRecord(
        book_id=str(calibre_book_id),
        title=title,
        title_sort=title_sort,
        authors=authors,
        author_sort=author_sort,
        series=series,
        series_index=series_index,
        tags=tags,
        rating=rating,
        languages=languages,
        publisher=publisher,
        pubdate=pubdate,
        timestamp=timestamp,
        identifiers=identifiers,
        custom_columns=parse_custom_columns(meta_pairs),
        relative_dir=book_dir_rel,
        cover_local_path=cover_path,
        format_files=format_files,
    )


def scan_library(library_root: Path, formats: List[str], max_books: int = 0) -> List[BookRecord]:
    books: List[BookRecord] = []
    opf_files = sorted(library_root.rglob("metadata.opf"))

    for idx, opf in enumerate(opf_files, start=1):
        if max_books and idx > max_books:
            break
        try:
            record = parse_book_from_opf(opf, library_root, formats)
            books.append(record)
        except Exception as exc:
            print(f"[WARN] Could not parse {opf}: {exc}")

    return books


def build_index(books: List[BookRecord], library_root: Path) -> Dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source": "calibre-opf",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "library_root": str(library_root),
        "book_count": len(books),
        "books": [
            {
                "book_id": b.book_id,
                "title": b.title,
                "title_sort": b.title_sort,
                "authors": b.authors,
                "author_sort": b.author_sort,
                "series": b.series,
                "series_index": b.series_index,
                "tags": b.tags,
                "rating": b.rating,
                "languages": b.languages,
                "publisher": b.publisher,
                "pubdate": b.pubdate,
                "timestamp": b.timestamp,
                "identifiers": b.identifiers,
                "custom_columns": b.custom_columns,
                "relative_dir": b.relative_dir,
                "cover_local_path": b.cover_local_path,
                "format_files": b.format_files,
                "drive_files": b.drive_files,
            }
            for b in books
        ],
    }


def auth_drive(credentials_path: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds)


def list_all_children(service, folder_id: str) -> List[Dict]:
    """List all direct children of a Drive folder, handling pagination automatically."""
    results: List[Dict] = []
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, mimeType, webViewLink)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        response = service.files().list(**params).execute()
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def populate_drive_ids_from_existing(
    service, root_folder_id: str, books: List[BookRecord], wanted_formats: List[str]
) -> None:
    """Populate drive_files for each book by listing existing files on Drive.

    Does NOT upload or modify any file — only reads Drive metadata and updates
    the in-memory BookRecord.drive_files mapping so the index can be rebuilt.
    """
    FOLDER_MIME = "application/vnd.google-apps.folder"

    # 1. Find the 'books' subfolder inside the root Drive folder.
    root_children = list_all_children(service, root_folder_id)
    books_folder = next(
        (c for c in root_children if c["name"] == "books" and c["mimeType"] == FOLDER_MIME),
        None,
    )
    if books_folder is None:
        print("[ERROR] Could not find 'books' folder inside the Drive root folder.")
        return
    print(f"[INFO] Found 'books' folder: id={books_folder['id']}")

    # 2. Build a relativeDir → BookRecord lookup.
    by_rel_dir: Dict[str, BookRecord] = {b.relative_dir: b for b in books}

    # 3. List all relativeDir subdirectories inside 'books/'.
    book_dirs = list_all_children(service, books_folder["id"])
    dir_count = sum(1 for d in book_dirs if d["mimeType"] == FOLDER_MIME)
    print(f"[INFO] Found {dir_count} book-directory entries on Drive.")

    # 4. For each matched directory, list its files and populate drive_files.
    matched = 0
    format_hits = 0
    for book_dir in book_dirs:
        if book_dir["mimeType"] != FOLDER_MIME:
            continue
        rel_dir = book_dir["name"]
        book = by_rel_dir.get(rel_dir)
        if book is None:
            continue
        matched += 1

        drive_files_in_dir = list_all_children(service, book_dir["id"])
        drive_name_map: Dict[str, Dict] = {f["name"].lower(): f for f in drive_files_in_dir}

        for fmt, local_path in book.format_files.items():
            if fmt not in wanted_formats:
                continue
            expected_name = Path(local_path).name.lower()
            hit = drive_name_map.get(expected_name)
            if hit:
                book.drive_files[fmt] = {
                    "id": hit["id"],
                    "name": hit["name"],
                    "webViewLink": hit.get("webViewLink", ""),
                }
                format_hits += 1

    print(f"[INFO] Matched {matched}/{len(by_rel_dir)} books. Populated {format_hits} format drive_files entries.")


def find_file_in_folder(service, parent_id: str, name: str, mime_type: Optional[str] = None) -> Optional[Dict[str, str]]:
    query = [
        f"'{parent_id}' in parents",
        f"name = '{name.replace("'", "\\'")}'",
        "trashed = false",
    ]
    if mime_type:
        query.append(f"mimeType = '{mime_type}'")

    result = (
        service.files()
        .list(
            q=" and ".join(query),
            spaces="drive",
            fields="files(id, name, webViewLink)",
            pageSize=1,
        )
        .execute()
    )
    files = result.get("files", [])
    return files[0] if files else None


def ensure_folder(service, parent_id: str, name: str, cache: Dict[str, str]) -> str:
    cache_key = f"{parent_id}/{name}"
    if cache_key in cache:
        return cache[cache_key]

    existing = find_file_in_folder(service, parent_id, name, mime_type="application/vnd.google-apps.folder")
    if existing:
        cache[cache_key] = existing["id"]
        return existing["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=metadata, fields="id").execute()
    cache[cache_key] = created["id"]
    return created["id"]


def upsert_file(service, parent_id: str, local_path: Path, drive_name: Optional[str] = None) -> Dict[str, str]:
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    name = drive_name or local_path.name
    mime_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)

    existing = find_file_in_folder(service, parent_id, name)
    if existing:
        updated = (
            service.files()
            .update(fileId=existing["id"], media_body=media, fields="id, name, webViewLink")
            .execute()
        )
        return updated

    metadata = {"name": name, "parents": [parent_id]}
    created = (
        service.files()
        .create(body=metadata, media_body=media, fields="id, name, webViewLink")
        .execute()
    )
    return created


def upload_book_assets(service, root_folder_id: str, book: BookRecord, dry_run: bool, folder_cache: Dict[str, str]) -> None:
    rel_parts = [p for p in Path(book.relative_dir).parts if p]
    parent_id = root_folder_id

    for part in rel_parts:
        if dry_run:
            continue
        parent_id = ensure_folder(service, parent_id, part, folder_cache)

    if book.cover_local_path:
        if dry_run:
            print(f"[DRY] Upload cover: {book.cover_local_path}")
        else:
            file_info = upsert_file(service, parent_id, Path(book.cover_local_path))
            book.drive_files["cover"] = {
                "id": file_info["id"],
                "name": file_info["name"],
                "webViewLink": file_info.get("webViewLink", ""),
            }

    for fmt, local_file in book.format_files.items():
        if dry_run:
            print(f"[DRY] Upload {fmt.upper()}: {local_file}")
            continue
        file_info = upsert_file(service, parent_id, Path(local_file))
        book.drive_files[fmt] = {
            "id": file_info["id"],
            "name": file_info["name"],
            "webViewLink": file_info.get("webViewLink", ""),
        }


def main() -> int:
    args = parse_args()

    library_root = Path(args.library).expanduser().resolve()
    if not library_root.exists() or not library_root.is_dir():
        print(f"[ERROR] Library path does not exist or is not a directory: {library_root}")
        return 1

    wanted_formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    if not wanted_formats:
        wanted_formats = ["epub"]

    print(f"[INFO] Scanning library: {library_root}")
    books = scan_library(library_root, wanted_formats, max_books=args.max_books)
    print(f"[INFO] Parsed books: {len(books)}")

    output_index = Path(args.output_index).expanduser().resolve()
    index_data = build_index(books, library_root)
    output_index.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Wrote index: {output_index}")

    if not args.upload_files and not args.populate_drive_ids:
        print("[INFO] Upload disabled (--upload-files not provided). Pass --populate-drive-ids to query Drive for existing file IDs.")
        return 0

    if not args.drive_folder_id:
        print("[ERROR] --drive-folder-id is required when --upload-files is used.")
        return 1

    credentials_path = Path(args.credentials).expanduser().resolve()
    token_path = Path(args.token).expanduser().resolve()

    if not credentials_path.exists():
        print(f"[ERROR] Credentials file not found: {credentials_path}")
        return 1

    if args.dry_run:
        print("[INFO] Dry run mode: no files will be uploaded.")
        folder_cache: Dict[str, str] = {}
        for book in books:
            upload_book_assets(None, args.drive_folder_id, book, dry_run=True, folder_cache=folder_cache)
        print("[INFO] Dry run complete.")
        return 0

    print("[INFO] Authenticating with Google Drive...")
    service = auth_drive(credentials_path, token_path)

    # --- populate-drive-ids: query Drive for existing file IDs, upload only the index ---
    if args.populate_drive_ids:
        print("[INFO] Querying Drive for existing file IDs (no files will be uploaded)...")
        populate_drive_ids_from_existing(service, args.drive_folder_id, books, wanted_formats)
        # Rebuild index with newly-found Drive IDs and upload it.
        index_data = build_index(books, library_root)
        output_index.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] Wrote updated index: {output_index}")
        index_file_info = upsert_file(service, args.drive_folder_id, output_index, drive_name="index.json")
        print(f"[INFO] index.json uploaded: {index_file_info.get('webViewLink', index_file_info['id'])}")
        print("[INFO] Done. Re-run the app and tap 'Recargar índice' to pick up the new Drive file IDs.")
        return 0

    folder_cache: Dict[str, str] = {}

    print("[INFO] Uploading index.json...")
    index_file_info = upsert_file(service, args.drive_folder_id, output_index, drive_name="index.json")
    print(f"[INFO] index.json uploaded: {index_file_info.get('webViewLink', index_file_info['id'])}")

    for i, book in enumerate(books, start=1):
        print(f"[INFO] ({i}/{len(books)}) Syncing: {book.title}")
        upload_book_assets(service, args.drive_folder_id, book, dry_run=False, folder_cache=folder_cache)

    # Rebuild index with Drive IDs/links and upload updated index.
    index_data = build_index(books, library_root)
    output_index.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_file(service, args.drive_folder_id, output_index, drive_name="index.json")
    print("[INFO] Sync complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
