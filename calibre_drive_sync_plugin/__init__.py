from calibre.customize import InterfaceActionBase


PLUGIN_PACKAGE = __package__ or "calibre_plugins.calibre_drive_sync_plugin"


class CalibreDriveSyncPlugin(InterfaceActionBase):
    name = "Calibre Drive Sync"
    description = "Actualiza index.json y sincroniza EPUB/portadas a carpeta local"
    supported_platforms = ["windows", "osx", "linux"]
    author = "ACER + Copilot"
    version = (0, 2, 2)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = f"{PLUGIN_PACKAGE}.ui:CalibreDriveSyncAction"
