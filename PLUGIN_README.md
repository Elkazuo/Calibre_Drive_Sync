# Plugin para Calibre: Actualizar y Cargar

Este plugin agrega una acción en Calibre para sincronizar en una carpeta local:

- `index.json`
- todos los formatos del libro disponibles en Calibre
- portadas

El destino ideal es una carpeta sincronizada por Google Drive Desktop.

## Por que plugin

- Aprovecha la API de Calibre en lugar de parsear archivos externos.
- Evita copiar codigo interno de Calibre (no hacemos copia literal de su codigo fuente).
- Deja un contrato de datos estable para la app Android.
- Permite sincronización incremental (solo copia cambios).

## Estructura

- `calibre_drive_sync_plugin/__init__.py`
- `calibre_drive_sync_plugin/ui.py`
- `calibre_drive_sync_plugin/exporter.py`

## Como empaquetar en ZIP

Desde PowerShell en esta carpeta:

```powershell
Set-Location "c:\Users\ACER\Desktop\UNIVERSITAS DOCTUS\Notas OneNote\Programación\Python\PersonalProjects\Calibre"
Compress-Archive -Path .\calibre_drive_sync_plugin\__init__.py, .\calibre_drive_sync_plugin\ui.py, .\calibre_drive_sync_plugin\exporter.py -DestinationPath .\calibre_drive_sync_plugin.zip -Force
```

El ZIP debe tener estos archivos en la raiz (sin carpeta contenedora):

- `__init__.py`
- `ui.py`
- `exporter.py`

## Como instalar en Calibre

1. Abre Calibre.
2. Preferencias -> Plugins -> Cargar plugin desde archivo.
3. Selecciona `calibre_drive_sync_plugin.zip`.
4. Reinicia Calibre.

## Diagnostico rapido

- Las advertencias en VS Code sobre `calibre` o `qt` son esperadas: esos modulos existen dentro del runtime de Calibre, no en tu entorno Python normal.
- Si no aparece la accion del plugin:
	1. Revisa en Preferencias -> Plugins que el plugin este habilitado.
	2. Abre `Preferencias -> Reiniciar en modo depuracion` y mira errores de carga del plugin en la consola.
	3. Reinstala el ZIP y reinicia Calibre.

## Uso

- En la barra/menus del plugin, ejecuta: `Actualizar y cargar (index + EPUB + portada)`.
- Elige la carpeta local sincronizada por Google Drive Desktop.
- Después el plugin te deja elegir entre:
	- respaldar todos los formatos disponibles (opción por defecto)
	- respaldar solo formatos concretos, por ejemplo `epub,pdf,docx`
- También puedes activar o desactivar el respaldo de portadas.

- El plugin genera:
	- `index.json`
	- `library/<autor>/<libro>/...` con todos los formatos del libro y portada.
	- `.calibre_drive_sync_state.json` para copia incremental.

## Estado actual

Este MVP ya implementa:

1. Boton unico "Actualizar y cargar".
2. Copia incremental de EPUB + portada.
3. Exportacion de `index.json` con esquema versionado.

## Siguiente paso recomendado

1. Añadir preferencias del plugin (carpeta fija y formatos extra: pdf, mobi).
2. Añadir boton secundario para "solo regenerar index".
3. Añadir filtro por biblioteca virtual o etiquetas.
