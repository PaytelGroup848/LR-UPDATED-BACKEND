from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QFrame

from api_client import AdminApiClient


SMOOTH_TRANSFORMATION = getattr(
    getattr(Qt, "TransformationMode", Qt),
    "SmoothTransformation",
)


class LoginWindow(QWidget):

    def __init__(self, base_url: str, on_success):
        super().__init__()

        self.client = AdminApiClient(base_url)
        self.on_success = on_success

        self.setWindowTitle("LR Admin Panel - Login")
        self.setFixedSize(430, 485)
        self.setStyleSheet("""
            QWidget {
                background: #f6faf8;
                color: #10231c;
                font-family: Segoe UI;
                font-size: 13px;
            }
            QFrame#loginCard {
                background: #ffffff;
                border: 1px solid #dce8e2;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #d6e5de;
                border-radius: 6px;
                padding: 10px 11px;
            }
            QLineEdit:focus {
                border: 1px solid #05a85c;
            }
            QPushButton {
                background: #05a85c;
                color: white;
                border: 0;
                border-radius: 6px;
                padding: 11px 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #049552;
            }
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(30, 30, 30, 30)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("loginCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 34, 34, 30)
        layout.setSpacing(14)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo_path = Path(__file__).resolve().parent / "resources" / "lr-remote-logo.png"
        pixmap = QPixmap(str(logo_path))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToWidth(235, SMOOTH_TRANSFORMATION))
            layout.addWidget(logo)

        title = QLabel("Admin Panel")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 800; margin-top: 4px;")

        subtitle = QLabel("Sign in to manage LR Remote Access.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #5f7068;")

        self.company_code_input = QLineEdit()
        self.company_code_input.setPlaceholderText("Company Code")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.try_login)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d63031;")
        self.error_label.setWordWrap(True)

        login_button = QPushButton("Login")
        login_button.clicked.connect(self.try_login)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.company_code_input)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(login_button)
        layout.addWidget(self.error_label)
        layout.addStretch(1)

        root_layout.addWidget(card)

    def try_login(self):

        company_code = self.company_code_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not company_code or not username or not password:
            self.error_label.setText("Company code, username and password are required.")
            return

        try:
            self.client.login(username, password, company_code)

        except ValueError as error:
            self.error_label.setText(str(error))
            return

        except Exception:
            self.error_label.setText("Could not reach the server.")
            return

        self.error_label.setText("")
        self.on_success(self.client)
