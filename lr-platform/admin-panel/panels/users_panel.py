from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)


GREEN = "#16A34A"
GREEN_DARK = "#12823c"
BLUE = "#2563EB"
BLUE_DARK = "#1d4ed8"
RED = "#DC2626"
RED_DARK = "#b91c1c"
ORANGE = "#F59E0B"
ORANGE_DARK = "#d97706"
TEXT = "#111827"
MUTED = "#6B7280"
BORDER = "#DDE7E1"
PANEL = "#F8FAF9"


def _qt_align(value):
    return getattr(Qt.AlignmentFlag, value, getattr(Qt, value))


class UsersPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.users: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self._button("Create Windows User Account", GREEN))
        toolbar.addWidget(self._button("Edit", ORANGE))
        toolbar.addWidget(self._button("Delete", RED))
        toolbar.addStretch(1)
        refresh_button = self._button("Refresh", BLUE)
        refresh_button.clicked.connect(self.load_users)
        toolbar.addWidget(refresh_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Username", "Role", "Windows Session", "Active", "Last Login"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self.open_user_details)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.total_label = QLabel("Total Users: 0")
        self.total_label.setObjectName("mutedLabel")
        layout.addWidget(self.total_label)

        self.load_users()

    def _button(self, text: str, color: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("tone", color)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background: {color};
                color: #ffffff;
                border: 0;
                border-radius: 6px;
                padding: 9px 14px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: {self._hover_color(color)}; }}
            """
        )
        return button

    def _hover_color(self, color: str) -> str:
        return {
            GREEN: GREEN_DARK,
            BLUE: BLUE_DARK,
            RED: RED_DARK,
            ORANGE: ORANGE_DARK,
        }.get(color, color)

    def load_users(self):
        try:
            if hasattr(self.client, "get_users"):
                users = self.client.get_users()
            else:
                users = self.client.users()
        except Exception as error:
            QMessageBox.warning(self, "Could not load users", str(error))
            return

        self.users = users if isinstance(users, list) else []
        self.table.setRowCount(len(self.users))

        for row, user in enumerate(self.users):
            values = [
                user.get("id", ""),
                user.get("username", ""),
                user.get("role", ""),
                user.get("windows_username") or user.get("windows_session") or "shared",
                "Yes" if user.get("is_active", True) else "No",
                user.get("last_login_at") or user.get("last_login") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 4 and str(value).lower() == "yes":
                    item.setForeground(Qt.GlobalColor.darkGreen)
                self.table.setItem(row, column, item)

        self.total_label.setText(f"Total Users: {len(self.users)}")

    def open_user_details(self, row: int, _column: int):
        if row < 0 or row >= len(self.users):
            return
        dialog = UserDetailsDialog(self.users[row], self)
        dialog.exec()


class UserDetailsDialog(QDialog):
    def __init__(self, user: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.user = user
        username = str(user.get("username") or "User")

        self.setWindowTitle(f"User Details - {username}")
        self.resize(1080, 760)
        self.setMinimumSize(920, 620)
        self.setModal(False)
        self.setStyleSheet(self._style())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(14)

        root.addLayout(self._header(username))
        root.addLayout(self._top_actions())

        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(), "Overview")
        tabs.addTab(self._placeholder_tab("Live Activity"), "Live Activity")
        tabs.addTab(self._placeholder_tab("Processes"), "Processes")
        tabs.addTab(self._placeholder_tab("Network"), "Network")
        tabs.addTab(self._policies_tab(), "Policies")
        tabs.addTab(self._placeholder_tab("Apps"), "Apps")
        tabs.addTab(self._placeholder_tab("URLs"), "URLs")
        tabs.addTab(self._placeholder_tab("Sessions"), "Sessions")
        tabs.addTab(self._placeholder_tab("Logs"), "Logs")
        root.addWidget(tabs, 1)

        root.addLayout(self._bottom_actions())

    def showEvent(self, event):
        super().showEvent(event)
        if self.parentWidget():
            parent_rect = self.parentWidget().window().geometry()
            self.move(parent_rect.center() - self.rect().center())

    def _header(self, username: str) -> QHBoxLayout:
        header = QHBoxLayout()
        title = QLabel(f"User Details - {username}")
        title.setObjectName("dialogTitle")
        header.addWidget(title)
        header.addStretch(1)

        status = QLabel("Status: Online")
        status.setObjectName("onlineStatus")
        dot = QWidget()
        dot.setFixedSize(10, 10)
        dot.setObjectName("greenDot")
        header.addWidget(status)
        header.addWidget(dot)
        return header

    def _top_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._action_button("Remote Desktop", GREEN))
        row.addWidget(self._action_button("Remote Control", BLUE))
        row.addWidget(self._action_button("Send Message", ORANGE))
        row.addWidget(self._action_button("Log Off User", RED))
        row.addStretch(1)
        return row

    def _overview_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(10, 12, 10, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        grid.addWidget(self._summary_card(), 0, 0)
        grid.addWidget(self._network_card(), 0, 1)
        grid.addWidget(self._usage_card(), 0, 2)
        grid.addWidget(self._activity_card(), 1, 0)
        grid.addWidget(self._apps_card(), 1, 1)
        grid.addWidget(self._processes_card(), 1, 2)
        grid.addWidget(self._recent_activity_card(), 2, 0, 1, 2)
        grid.addWidget(self._quick_actions_card(), 2, 2)

        for column in range(3):
            grid.setColumnStretch(column, 1)

        scroll.setWidget(content)
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        return wrapper

    def _summary_card(self) -> QGroupBox:
        return self._info_card(
            "User Summary",
            [
                ("Username", self.user.get("username", "")),
                ("User ID", self.user.get("id", "")),
                ("Role", self.user.get("role", "User")),
                ("Windows Session", self.user.get("windows_username") or "shared"),
                ("Active", "Yes" if self.user.get("is_active", True) else "No"),
                ("Last Login", self.user.get("last_login_at") or "2026-07-06 13:21:22"),
                ("Assigned Server", self.user.get("assigned_server") or "SERVER01"),
                ("Assigned Group", self.user.get("assigned_group") or "Employees"),
                ("License Type", self.user.get("license_type") or "Standard"),
            ],
        )

    def _network_card(self) -> QGroupBox:
        return self._info_card(
            "Device / Network Information",
            [
                ("Computer Name", "DESKTOP-9F2K21"),
                ("Local IP", "192.168.1.25"),
                ("Public IP", "103.21.45.67"),
                ("MAC Address", "3C-52-82-12-4A-8B"),
                ("OS Version", "Windows 11 Pro 23H2"),
                ("Windows Build", "22631.3593"),
                ("Domain / Workgroup", "WORKGROUP"),
                ("Connected Network", "Wi-Fi"),
                ("Last Boot Time", "2026-07-06 08:15:44"),
            ],
        )

    def _usage_card(self) -> QGroupBox:
        card = self._card("Live System Usage")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.addLayout(self._progress_row("CPU Usage", 12, GREEN))
        layout.addLayout(self._progress_row("RAM Usage", 43, BLUE))
        layout.addLayout(self._progress_row("Disk Usage", 38, "#65A34D"))
        layout.addLayout(self._value_row("Download Speed", "2.4 Mbps"))
        layout.addLayout(self._value_row("Upload Speed", "1.1 Mbps"))
        layout.addLayout(self._value_row("Idle Time", "02 min 15 sec"))
        layout.addLayout(self._value_row("Screen Status", "Unlocked"))
        return card

    def _activity_card(self) -> QGroupBox:
        return self._info_card(
            "Current Activity",
            [
                ("Active Window", "Gmail - Google Chrome"),
                ("Active Application", "Google Chrome"),
                ("Opened Since", "13:45:12"),
                ("Keyboard/Mouse Idle", "02 min 15 sec"),
                ("Session Duration", "01:48:32"),
                ("Screen Resolution", "1920 x 1080"),
                ("Monitors", "1"),
            ],
        )

    def _apps_card(self) -> QGroupBox:
        card = self._card("Running Applications")
        layout = QVBoxLayout(card)
        for app in [
            "Google Chrome",
            "Microsoft Word",
            "Windows Explorer",
            "WhatsApp Desktop",
            "Notepad",
        ]:
            layout.addLayout(self._value_row(app, "Running"))
        layout.addStretch(1)
        return card

    def _processes_card(self) -> QGroupBox:
        card = self._card("Top Processes")
        layout = QVBoxLayout(card)
        table = QTableWidget(5, 3)
        table.setHorizontalHeaderLabels(["Process Name", "CPU %", "Memory"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rows = [
            ("chrome.exe", "4.3%", "512.6 MB"),
            ("explorer.exe", "1.2%", "132.1 MB"),
            ("MsMpEng.exe", "0.8%", "98.7 MB"),
            ("WINWORD.EXE", "0.6%", "76.4 MB"),
            ("dwm.exe", "0.4%", "45.3 MB"),
        ]
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(table)
        return card

    def _recent_activity_card(self) -> QGroupBox:
        card = self._card("Recent Activity")
        layout = QVBoxLayout(card)
        for time, event in [
            ("13:21:22", "Login Successful"),
            ("13:22:10", "Chrome Launched"),
            ("13:24:30", "Opened Gmail"),
            ("13:30:11", "Word Launched"),
            ("13:45:12", "Active Window Changed"),
        ]:
            layout.addLayout(self._value_row(time, event))
        return card

    def _quick_actions_card(self) -> QGroupBox:
        card = self._card("Quick Actions")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        for text in [
            "Kill Process",
            "Block Application",
            "Clear Clipboard",
            "Lock Screen",
            "Restart Explorer",
            "Refresh Information",
        ]:
            layout.addWidget(self._secondary_button(text))
        layout.addStretch(1)
        return card

    def _policies_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(10, 12, 10, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        groups = [
            ("Desktop", ["Prevent Delete", "Prevent Rename", "Prevent Create", "Disable Right Click", "Lock Wallpaper", "Hide Desktop Icons"]),
            ("Explorer", ["Hide C Drive", "Hide D Drive", "Block Copy", "Block Paste", "Disable USB", "Read Only USB"]),
            ("System", ["Disable CMD", "Disable PowerShell", "Disable Registry", "Disable Task Manager", "Disable Control Panel", "Disable Settings"]),
            ("Applications", ["Allow Assigned Apps Only", "Block Software Install", "Block EXE Files", "Block Games"]),
            ("Browser", ["Block Downloads", "Disable Incognito", "Website Filtering"]),
        ]

        for index, (title, options) in enumerate(groups):
            grid.addWidget(self._checkbox_card(title, options), index // 2, index % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(3, 1)
        scroll.setWidget(content)

        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        return wrapper

    def _checkbox_card(self, title: str, options: list[str]) -> QGroupBox:
        card = self._card(title)
        layout = QGridLayout(card)
        layout.setVerticalSpacing(12)
        for index, option in enumerate(options):
            checkbox = QCheckBox(option)
            layout.addWidget(checkbox, index // 2, index % 2)
        return card

    def _placeholder_tab(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(f"{title} data will appear here.")
        label.setObjectName("mutedLabel")
        label.setAlignment(_qt_align("AlignCenter"))
        layout.addWidget(label)
        return page

    def _bottom_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._action_button("Apply Policy", GREEN))
        row.addWidget(self._action_button("Save Changes", BLUE))
        row.addWidget(self._secondary_button("Export Report"))
        row.addStretch(1)
        close_button = self._secondary_button("Close")
        close_button.clicked.connect(self.close)
        row.addWidget(close_button)
        return row

    def _info_card(self, title: str, rows: list[tuple[str, object]]) -> QGroupBox:
        card = self._card(title)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        for label, value in rows:
            layout.addLayout(self._value_row(label, str(value)))
        layout.addStretch(1)
        return card

    def _card(self, title: str) -> QGroupBox:
        card = QGroupBox(title)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    def _value_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        key = QLabel(label)
        key.setObjectName("fieldLabel")
        val = QLabel(value)
        val.setObjectName("fieldValue")
        val.setWordWrap(True)
        row.addWidget(key, 1)
        row.addWidget(val, 1)
        return row

    def _progress_row(self, label: str, value: int, color: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label), 1)
        bar = QProgressBar()
        bar.setValue(value)
        bar.setTextVisible(False)
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: #E5E7EB;
                border: 0;
                border-radius: 5px;
                height: 10px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 5px;
            }}
            """
        )
        row.addWidget(bar, 2)
        percent = QLabel(f"{value}%")
        percent.setAlignment(_qt_align("AlignRight") | _qt_align("AlignVCenter"))
        row.addWidget(percent)
        return row

    def _action_button(self, text: str, color: str) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background: {color};
                color: #ffffff;
                border: 0;
                border-radius: 6px;
                padding: 9px 14px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: {self._hover_color(color)}; }}
            """
        )
        return button

    def _secondary_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(
            """
            QPushButton {
                background: #F3F6F5;
                color: #1F2937;
                border: 1px solid #DDE7E1;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #EAF3EE; }
            """
        )
        return button

    def _hover_color(self, color: str) -> str:
        return {
            GREEN: GREEN_DARK,
            BLUE: BLUE_DARK,
            RED: RED_DARK,
            ORANGE: ORANGE_DARK,
        }.get(color, color)

    def _style(self) -> str:
        return f"""
        QDialog, QWidget {{
            background: #FFFFFF;
            color: {TEXT};
            font-family: Segoe UI;
            font-size: 13px;
        }}
        QLabel#dialogTitle {{
            font-size: 18px;
            font-weight: 800;
        }}
        QLabel#onlineStatus {{
            color: {GREEN};
            font-weight: 800;
        }}
        QWidget#greenDot {{
            background: {GREEN};
            border-radius: 5px;
        }}
        QLabel#mutedLabel {{
            color: {MUTED};
        }}
        QLabel#fieldLabel {{
            color: #374151;
            font-weight: 600;
        }}
        QLabel#fieldValue {{
            color: {TEXT};
        }}
        QTabWidget::pane {{
            background: #FFFFFF;
            border: 1px solid {BORDER};
            border-radius: 8px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: #EEF5F1;
            color: #4B5563;
            padding: 10px 18px;
            border: 1px solid {BORDER};
            border-bottom: 0;
            font-weight: 700;
            min-width: 74px;
        }}
        QTabBar::tab:selected {{
            background: {GREEN};
            color: #FFFFFF;
        }}
        QGroupBox {{
            background: {PANEL};
            border: 1px solid {BORDER};
            border-radius: 8px;
            margin-top: 22px;
            padding: 16px 12px 12px 12px;
            font-weight: 800;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #1F2937;
        }}
        QTableWidget {{
            background: #FFFFFF;
            border: 1px solid {BORDER};
            border-radius: 6px;
            gridline-color: #E5E7EB;
        }}
        QHeaderView::section {{
            background: #EEF5F1;
            color: {TEXT};
            border: 0;
            padding: 7px;
            font-weight: 800;
        }}
        QCheckBox {{
            color: #1F2937;
            spacing: 8px;
            padding: 4px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid #B7C7BF;
            border-radius: 4px;
            background: #FFFFFF;
        }}
        QCheckBox::indicator:checked {{
            background: {GREEN};
            border: 1px solid {GREEN};
        }}
        QScrollArea {{
            background: #FFFFFF;
            border: 0;
        }}
        """
