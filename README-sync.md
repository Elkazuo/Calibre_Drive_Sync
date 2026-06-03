# Sync Calibre -> Google Drive

Este script exporta metadatos de Calibre a `index.json` y opcionalmente sube `index.json`, portadas y EPUB (u otros formatos) a Google Drive.

## 1) Requisitos

- Python 3.10+
- Biblioteca Calibre (carpeta con subcarpetas de libros y archivos `metadata.opf`)
- Proyecto en Google Cloud con OAuth Client ID (Desktop app)

Instala dependencias:

```powershell
pip install -r requirements-sync.txt
```

## 2) Preparar Google Drive API

1. En Google Cloud Console, habilita **Google Drive API**.
2. Crea credenciales OAuth de tipo **Desktop app**.
3. Descarga el JSON y guárdalo como `credentials.json` en esta carpeta (o usa `--credentials`).
4. Crea (o elige) una carpeta de destino en Drive y copia su `folderId` desde la URL.

## 3) Ejecutar

Solo generar índice local:

```powershell
python sync_calibre_to_drive.py --library "E:\\Calibre Library"
```

Generar índice y subir archivos a Drive:

```powershell
python sync_calibre_to_drive.py --library "E:\Calibre Library" --drive-folder-id "TU_FOLDER_ID" --upload-files
```

Subir varios formatos además de EPUB:

```powershell
python sync_calibre_to_drive.py --library "E:\Calibre Library" --drive-folder-id "TU_FOLDER_ID" --upload-files --formats "epub,pdf,mobi"
```

Probar sin subir nada (dry-run):

```powershell
python sync_calibre_to_drive.py --library "E:\Calibre Library" --drive-folder-id "TU_FOLDER_ID" --upload-files --dry-run --max-books 20
```

## 4) Resultado

- Se crea `index.json` con metadatos listos para la app Android.
- Si usas `--upload-files`, el script:
  - Subirá `index.json` a la carpeta de Drive.
  - Creará estructura de carpetas por libro.
  - Subirá portada y formatos seleccionados.
  - Actualizará `index.json` con IDs/enlaces de Drive (`drive_files`).

## 5) Notas

- Este enfoque evita leer `metadata.db` desde Android.
- Extrae metadatos desde `metadata.opf` (incluye campos de Calibre y columnas personalizadas detectables como `calibre:#...`).
- El `index.json` incluye `schema_version` y `source` para control de compatibilidad en Android.
- El primer login OAuth abrirá navegador para autorizar; luego se guarda `token.json`.

## 6) Contrato para Android

La estructura exacta que debe consumir la APK está documentada en `ANDROID_INDEX_CONTRACT.md`.
