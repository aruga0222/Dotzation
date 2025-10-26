"""Entry point for launching Dotzation as a module."""

from PySide6.QtWidgets import QApplication

from .ui.main_window import DotzationWindow


def main() -> int:
    """Create the application and run the main event loop."""
    app = QApplication([])
    window = DotzationWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
