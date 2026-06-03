import traceback
from pathlib import Path

from qt.core import QApplication
from qt.core import QCheckBox
from qt.core import QDialog
from qt.core import QDialogButtonBox
from qt.core import QFileDialog
from qt.core import QFormLayout
from qt.core import QHBoxLayout
from qt.core import QLabel
from qt.core import QLineEdit
from qt.core import QToolButton
from qt.core import QVBoxLayout

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.dialogs.progress import ProgressDialog
from calibre.gui2.actions import InterfaceAction

from .exporter import export_and_sync_local


class CalibreDriveSyncAction(InterfaceAction):
    name = "Calibre Drive Sync Export"
    action_type = "current"
    action_add_menu = True
    action_menu_clone_qaction = "Actualizar y cargar"
    popup_type = QToolButton.ToolButtonPopupMode.InstantPopup
    action_spec = (
        "Actualizar y cargar",
        "wizard.png",
        "Sincroniza index.json y archivos en una carpeta local para Google Drive Desktop",
        None,
    )

    def genesis(self):
        self.qaction.triggered.connect(self.run_export)

    def _get_sync_options(self):
        dialog = QDialog(self.gui)
        dialog.setWindowTitle("Opciones de sincronización")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        all_formats_checkbox = QCheckBox("Respaldar todos los formatos disponibles")
        all_formats_checkbox.setChecked(True)

        formats_edit = QLineEdit()
        formats_edit.setPlaceholderText("epub,pdf,docx")
        formats_edit.setEnabled(False)

        def toggle_formats(enabled):
            formats_edit.setEnabled(not enabled)

        all_formats_checkbox.toggled.connect(toggle_formats)

        include_cover_checkbox = QCheckBox("Respaldar portadas")
        include_cover_checkbox.setChecked(True)

        form.addRow(all_formats_checkbox)
        form.addRow(QLabel("Si desactivas lo anterior, escribe formatos separados por coma:"), formats_edit)
        form.addRow(include_cover_checkbox)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        if all_formats_checkbox.isChecked():
            formats = None
        else:
            formats = [x.strip() for x in formats_edit.text().split(",") if x.strip()]

        return {
            "formats": formats,
            "include_cover": include_cover_checkbox.isChecked(),
        }

    def run_export(self):
        progress = None
        try:
            default_dir = str(Path.home())
            selected_dir = QFileDialog.getExistingDirectory(
                self.gui,
                "Selecciona carpeta de sincronizacion local (Google Drive Desktop)",
                default_dir,
            )
            if not selected_dir:
                return

            options = self._get_sync_options()
            if options is None:
                return

            db = self.gui.current_db.new_api
            progress = ProgressDialog(
                "Calibre Drive Sync",
                "Preparando sincronización...",
                min=0,
                max=1,
                parent=self.gui,
                icon="wizard.png",
                cancelable=True,
            )
            progress.setWindowTitle("Calibre Drive Sync")
            progress.show()

            def on_progress(stage, current, total, message):
                progress.max = max(1, int(total or 1))
                progress.value = max(0, min(int(current or 0), progress.max))
                progress.msg = f"{message}"
                QApplication.processEvents()
                return bool(getattr(progress, 'canceled', False))

            result = export_and_sync_local(
                db,
                sync_root=Path(selected_dir),
                formats=options["formats"],
                include_cover=options["include_cover"],
                progress_callback=on_progress,
            )

            progress.close()

            if result.get("canceled"):
                info_dialog(
                    self.gui,
                    "Calibre Drive Sync",
                    "Sincronización cancelada por el usuario.",
                    show=True,
                )
                return

            info_dialog(
                self.gui,
                "Calibre Drive Sync",
                "Sincronizacion completada\n\n"
                f"Libros procesados: {result['books']}\n"
                f"Archivos copiados/actualizados: {result['files_copied']}\n"
                f"Index generado: {result['index_path']}",
                show=True,
            )
        except Exception:
            error_dialog(
                self.gui,
                "Calibre Drive Sync",
                "Error exportando index.json\n\n" + traceback.format_exc(),
                show=True,
            )
        finally:
            if progress is not None:
                progress.close()
