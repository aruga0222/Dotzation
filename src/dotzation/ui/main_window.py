"""Main application window for Dotzation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import halftone


class DotzationWindow(QMainWindow):
    """Main window that wires UI events to the halftoning logic."""

    PREVIEW_SIZE = QSize(360, 360)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dotzation")
        self.resize(960, 640)

        self._original_image: Optional[Image.Image] = None
        self._processed_image: Optional[Image.Image] = None

        self._create_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ UI
    def _create_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Controls row
        controls_layout = QHBoxLayout()
        self.load_button = QPushButton("画像を開く…")
        self.save_button = QPushButton("保存…")
        self.save_button.setEnabled(False)
        controls_layout.addWidget(self.load_button)
        controls_layout.addWidget(self.save_button)
        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

        # Preview area
        previews_layout = QHBoxLayout()
        self.original_preview = self._create_preview_box("元画像")
        self.processed_preview = self._create_preview_box("変換後")
        previews_layout.addWidget(self.original_preview)
        previews_layout.addWidget(self.processed_preview)
        main_layout.addLayout(previews_layout, stretch=1)

        # Settings
        settings_group = QGroupBox("ハーフトーン設定")
        settings_layout = QFormLayout(settings_group)

        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(50, 300)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setSingleStep(10)
        settings_layout.addRow("Zoom", self.zoom_spin)

        self.dot_size_spin = QSpinBox()
        self.dot_size_spin.setRange(2, 64)
        self.dot_size_spin.setValue(12)
        self.dot_size_spin.setSuffix(" px")
        settings_layout.addRow("ドットサイズ", self.dot_size_spin)

        self.method_combo = QComboBox()
        for method_name in halftone.available_methods():
            self.method_combo.addItem(method_name)
        settings_layout.addRow("方式", self.method_combo)

        self.method_description = QLabel()
        self.method_description.setWordWrap(True)
        self.method_description.setAlignment(Qt.AlignmentFlag.AlignTop)
        settings_layout.addRow("説明", self.method_description)

        self.convert_button = QPushButton("変換")
        self.convert_button.setEnabled(False)
        self.merge_button = QPushButton("マージ")
        self.merge_button.setEnabled(False)

        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self.convert_button)
        buttons_layout.addWidget(self.merge_button)
        buttons_layout.addStretch(1)
        settings_layout.addRow("", buttons_widget)

        main_layout.addWidget(settings_group)

        self._update_method_description()

    def _create_preview_box(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        label = QLabel("画像が読み込まれていません")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(self.PREVIEW_SIZE)
        label.setStyleSheet("border: 1px solid #cccccc; background: #fdfdfd;")
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

        group.image_label = label  # type: ignore[attr-defined]
        return group

    # ------------------------------------------------------------- Signals
    def _connect_signals(self) -> None:
        self.load_button.clicked.connect(self._select_image)
        self.save_button.clicked.connect(self._save_image)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self.convert_button.clicked.connect(self._on_convert_clicked)
        self.merge_button.clicked.connect(self._on_merge_clicked)
        self.zoom_spin.valueChanged.connect(self._on_zoom_changed)

    # ----------------------------------------------------------- Handlers
    def _select_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "画像を選択",
            str(Path.home()),
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not filename:
            return

        try:
            self._original_image = halftone.load_image(filename)
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._show_error("画像の読み込みに失敗しました", str(exc))
            return

        self._update_original_preview()
        self._update_processed_preview()
        self.save_button.setEnabled(True)
        self.convert_button.setEnabled(True)

    def _save_image(self) -> None:
        if self._processed_image is None:
            self._show_error("保存できません", "変換後の画像がありません。")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "画像を保存",
            str(Path.home() / "dotzation.png"),
            "PNG 画像 (*.png);;JPEG 画像 (*.jpg *.jpeg);;BMP 画像 (*.bmp)"
        )
        if not filename:
            return

        try:
            halftone.save_image(self._processed_image, filename)
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._show_error("保存に失敗しました", str(exc))
        else:
            QMessageBox.information(self, "保存しました", f"画像を保存しました: {filename}")

    def _on_convert_clicked(self) -> None:
        self._update_processed_preview()

    def _on_merge_clicked(self) -> None:
        if self._original_image is None or self._processed_image is None:
            self._show_error("マージできません", "元画像または変換結果がありません。")
            return

        try:
            merged = halftone.merge_with_original(self._original_image, self._processed_image)
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._show_error("マージに失敗しました", str(exc))
            return

        self._processed_image = merged
        target_size = self._target_preview_size()
        pixmap = halftone.scaled_pixmap(
            merged,
            target_size.width(),
            target_size.height(),
        )
        self.processed_preview.image_label.setText("")
        self.processed_preview.image_label.setPixmap(pixmap)

    def _on_method_changed(self, index: int) -> None:  # noqa: ARG002 - signal signature
        self._update_method_description()
        self._update_processed_preview()

    def _on_zoom_changed(self, value: int) -> None:  # noqa: ARG002
        if self._original_image is not None:
            self._update_original_preview()
        if self._processed_image is not None:
            self._update_processed_preview()

    # -------------------------------------------------------------- Helpers
    def _update_original_preview(self) -> None:
        assert self._original_image is not None
        target_size = self._target_preview_size()
        pixmap = halftone.scaled_pixmap(
            self._original_image,
            target_size.width(),
            target_size.height(),
        )
        self.original_preview.image_label.setText("")
        self.original_preview.image_label.setMinimumSize(target_size)
        self.original_preview.image_label.setPixmap(pixmap)

    def _update_processed_preview(self) -> None:
        if self._original_image is None:
            return

        target_size = self._target_preview_size()
        try:
            self._processed_image = halftone.process_image(
                self._original_image,
                self.method_combo.currentText(),
                self.dot_size_spin.value(),
            )
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._show_error("変換に失敗しました", str(exc))
            return

        pixmap = halftone.scaled_pixmap(
            self._processed_image,
            target_size.width(),
            target_size.height(),
        )
        self.processed_preview.image_label.setText("")
        self.processed_preview.image_label.setMinimumSize(target_size)
        self.processed_preview.image_label.setPixmap(pixmap)
        self.merge_button.setEnabled(True)

    def _update_method_description(self) -> None:
        method_name = self.method_combo.currentText()
        if not method_name:
            self.method_description.setText("")
            return
        self.method_description.setText(halftone.describe_method(method_name))

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _target_preview_size(self) -> QSize:
        scale = max(self.zoom_spin.value(), 1) / 100.0
        width = max(1, int(self.PREVIEW_SIZE.width() * scale))
        height = max(1, int(self.PREVIEW_SIZE.height() * scale))
        return QSize(width, height)
