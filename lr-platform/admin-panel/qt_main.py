import sys

from PySide6.QtWidgets import QApplication

from config import DEFAULT_BACKEND_URL
from dashboard_window import DashboardWindow
from login_window import LoginWindow


class AdminPanelApp:
    def __init__(self):
        self.login_window = LoginWindow(DEFAULT_BACKEND_URL, self.open_dashboard)
        self.dashboard_window = None

    def show(self):
        self.login_window.show()

    def open_dashboard(self, client):
        self.dashboard_window = DashboardWindow(client)
        self.dashboard_window.show()
        self.login_window.close()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LR Admin Panel")
    window = AdminPanelApp()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
