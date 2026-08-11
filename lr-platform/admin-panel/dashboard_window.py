from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QTabWidget
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QPushButton

from panels.users_panel import UsersPanel


SMOOTH_TRANSFORMATION = getattr(
    getattr(Qt, "TransformationMode", Qt),
    "SmoothTransformation",
)


class DashboardWindow(QMainWindow):

    def __init__(self, client):
        super().__init__()

        self.client = client

        self.setWindowTitle("LR Admin Panel")
        self.resize(1240, 780)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #f6faf8;
                color: #10231c;
                font-family: Segoe UI;
                font-size: 13px;
            }
            QWidget#header {
                background: #ffffff;
                border-bottom: 1px solid #dce8e2;
            }
            QLabel#title {
                font-size: 22px;
                font-weight: 800;
                color: #10231c;
            }
            QLabel#subtitle {
                color: #5f7068;
            }
            QLabel#loginStatus {
                color: #16A34A;
                font-weight: 800;
            }
            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #dce8e2;
                top: -1px;
            }
            QTabBar::tab {
                background: #edf5f1;
                color: #5f7068;
                padding: 10px 16px;
                font-weight: 700;
            }
            QTabBar::tab:selected {
                background: #16A34A;
                color: #ffffff;
            }
            QPushButton {
                background: #16A34A;
                color: white;
                border: 0;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #12823c;
            }
            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #d6e5de;
                border-radius: 5px;
                padding: 7px 9px;
            }
            QTableWidget {
                background: #ffffff;
                gridline-color: #dce8e2;
                border: 1px solid #dce8e2;
            }
            QHeaderView::section {
                background: #eef5f1;
                color: #10231c;
                border: 0;
                padding: 8px;
                font-weight: 700;
            }
        """)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QWidget()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 14, 22, 14)
        header_layout.setSpacing(14)

        logo = QLabel()
        logo_path = Path(__file__).resolve().parent / "resources" / "lr-remote-logo.png"
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToWidth(210, SMOOTH_TRANSFORMATION))
            header_layout.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Admin Panel")
        title.setObjectName("title")
        subtitle = QLabel("Manage users, servers and software")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)

        login_status = QLabel("Logged in: admin")
        login_status.setObjectName("loginStatus")
        header_layout.addWidget(login_status)

        update_button = QPushButton("Check Update")
        header_layout.addWidget(update_button)

        tabs = QTabWidget()
        tabs.addTab(UsersPanel(client), "Users")
        tabs.addTab(self._placeholder_tab("Servers"), "Servers")
        tabs.addTab(self._placeholder_tab("Software"), "Software")
        tabs.addTab(self._placeholder_tab("Assign"), "Assign")
        tabs.addTab(self._placeholder_tab("URLs"), "URLs")
        tabs.addTab(self._placeholder_tab("Monitor"), "Monitor")
        tabs.addTab(self._placeholder_tab("Policies"), "Policies")
        tabs.addTab(self._placeholder_tab("Settings"), "Settings")
        layout.addWidget(header)
        layout.addWidget(tabs, 1)
        layout.setContentsMargins(0, 0, 0, 16)

        self.setCentralWidget(page)

    def _placeholder_tab(self, title: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(f"{title} panel")
        label.setAlignment(getattr(Qt.AlignmentFlag, "AlignCenter", Qt.AlignCenter))
        label.setStyleSheet("color: #5f7068; font-weight: 700;")
        layout.addWidget(label)
        return page
