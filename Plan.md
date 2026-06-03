# 1. Arquitectura recomendada
Componente A (portátil): script de sincronización desde calibre a Google Drive.
Componente B (Android APK): app ligera que lee un índice de metadatos y muestra/ordena libros.
Componente C (opcional): visor EPUB integrado.
# Decisión clave (muy importante)
No conviene que la APK lea directamente metadata.db de calibre.
Conviene exportar un index.json (o SQLite simplificada) desde tu portátil, con todos tus metadatos ya “limpios”, y subirlo junto a portadas/epubs a Drive.

# Qué metadatos exportar (mínimo útil)

book_id
title, authors, sort
series, series_index
tags, rating, languages
publisher, pubdate, timestamp
columnas personalizadas de calibre (#mi_columna)
rutas/IDs de cover y epub en Drive
Así podrás replicar búsqueda y ordenamiento casi como calibre, sin cargar toda su complejidad.

# APK Android (MVP)
Login con Google (Google Identity).
Acceso a carpeta de Drive con la biblioteca.
Descarga/sincronización del index.json a base local (Room).
Búsqueda rápida (FTS5) y filtros/sort por metadatos.
Lista tipo biblioteca + detalle simple.
Botón “Abrir EPUB”.
# Visor EPUB
Dos opciones:
Rápida: abrir con app externa instalada en Android.
Integrada (mejor UX): usar Readium Kotlin Toolkit para visualizar dentro de tu APK.
# “Estilo calibre” sin copiarlo tal cual
Podemos replicar la experiencia:
Panel de filtros (autor, tags, series, idioma).
Orden por título/autor/fecha/rating/series.
Vista lista y vista rejilla.
Diseño sobrio tipo biblioteca.
Plan por fases (recomendado)
Fase 1: script portátil exporta metadatos + subida a Drive.
Fase 2: APK con sync + búsqueda + ordenamiento (sin lector EPUB).
Fase 3: integración lector EPUB y mejoras UX.