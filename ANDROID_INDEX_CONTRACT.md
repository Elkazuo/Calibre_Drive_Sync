FALTA PULIR LAS PORTADAS.
FALTA INCLUIR RESUMENES?
# Contrato de index.json para Android

Este documento define la estructura de `index.json` generada por `sync_calibre_to_drive.py`.

## Metadatos raíz

- `schema_version` (string): versión de contrato. Actual: `1.0.0`.
- `source` (string): origen de datos. Actual: `calibre-opf`.
- `generated_at` (string ISO-8601 UTC)
- `library_root` (string)
- `book_count` (number)
- `books` (array)

## Estructura de cada libro

- `book_id` (string)
- `title` (string)
- `title_sort` (string)
- `authors` (string[])
- `author_sort` (string[])
- `series` (string | null)
- `series_index` (number | null)
- `tags` (string[])
- `rating` (number | null)
- `languages` (string[])
- `publisher` (string | null)
- `pubdate` (string | null)
- `timestamp` (string | null)
- `identifiers` (object<string,string>)
- `custom_columns` (object<string,any>)
- `relative_dir` (string)
- `cover_local_path` (string | null)
- `format_files` (object<string,string>)
- `drive_files` (object<string, { id: string, name: string, webViewLink: string }>)

## Reglas importantes para el APK

- Validar `schema_version` antes de parsear.
- `custom_columns` conserva prefijo `#` para alinear con Calibre (`#mi_columna`).
- `drive_files` puede venir vacío cuando no se ejecuta con `--upload-files`.
- Para lectura EPUB en Android, usar `drive_files["epub"].id` o `webViewLink`.

## Ejemplo mínimo

```json
{
  "schema_version": "1.0.0",
  "source": "calibre-opf",
  "generated_at": "2026-06-01T12:00:00+00:00",
  "library_root": "E:/Calibre Library",
  "book_count": 1,
  "books": [
    {
      "book_id": "123",
      "title": "Example Book",
      "title_sort": "Example Book",
      "authors": ["Autor Uno"],
      "author_sort": ["Uno, Autor"],
      "series": "Saga X",
      "series_index": 1.0,
      "tags": ["Fiction"],
      "rating": 8.0,
      "languages": ["es"],
      "publisher": "Editorial",
      "pubdate": "2025-01-01",
      "timestamp": "2026-05-30T10:00:00+00:00",
      "identifiers": {"isbn": "9780000000000"},
      "custom_columns": {"#estado": "leido"},
      "relative_dir": "Autor Uno/Example Book (123)",
      "cover_local_path": "E:/Calibre Library/Autor Uno/Example Book (123)/cover.jpg",
      "format_files": {
        "epub": "E:/Calibre Library/Autor Uno/Example Book (123)/Example Book - Autor Uno.epub"
      },
      "drive_files": {
        "epub": {
          "id": "1abcDEF...",
          "name": "Example Book - Autor Uno.epub",
          "webViewLink": "https://drive.google.com/file/d/..."
        },
        "cover": {
          "id": "1xyzDEF...",
          "name": "cover.jpg",
          "webViewLink": "https://drive.google.com/file/d/..."
        }
      }
    }
  ]
}
```
