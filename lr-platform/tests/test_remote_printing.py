import hashlib
import sys
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from flask_login import LoginManager, UserMixin, login_user

from backend.api.routers.printing_route import printing_bp
from backend.printing.models import CaptureMetadata
from backend.printing.capture import WatchedFolderPrintCaptureProvider
from backend.printing.service import PrintJobService
from backend.printing.settings import PrintingSettings


DESKTOP_CLIENT_DIR = Path(__file__).resolve().parents[1] / "desktop-client"
if str(DESKTOP_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_CLIENT_DIR))

from printing.agent import PrintAgent
from printing.providers import get_default_printer, list_local_printers
from printing.settings import ClientPrintSettingsStore


PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


class StaticSettingsStore:
    def __init__(self, value=None):
        self.value = value or PrintingSettings()

    def get(self, **_kwargs):
        return self.value


class FakeBinaryConnection:
    def __init__(self, content):
        self.content = content

    def get_binary(self, _path):
        return self.content, {
            "X-Print-Chunk-Sequence": "0",
            "X-Print-Chunk-Offset": "0",
            "X-Print-Chunk-Final": "1",
        }

    def post_json(self, _path, _payload):
        return {"success": True}


class RemotePrintingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sessions = {
            "session-a": {"_id": "session-a", "user_id": "user-a", "status": "active"},
            "session-b": {"_id": "session-b", "user_id": "user-b", "status": "active"},
        }
        self.service = PrintJobService(
            settings_store=StaticSettingsStore(),
            capture_root=self.root,
            session_lookup=self.sessions.get,
        )
        self.connection_a = str(uuid.uuid4())
        self.connection_b = str(uuid.uuid4())
        self.service.register_client(
            session_id="session-a",
            connection_id=self.connection_a,
            user_id="user-a",
            client_type="desktop",
            capabilities={"binary_chunks": True},
            printers=[],
        )
        self.service.register_client(
            session_id="session-b",
            connection_id=self.connection_b,
            user_id="user-b",
            client_type="desktop",
            capabilities={"binary_chunks": True},
            printers=[],
        )

    def tearDown(self):
        self.temp.cleanup()

    def _submit(self, *, session="session-a", user="user-a", connection=None, content=PDF_BYTES):
        job_id = str(uuid.uuid4())
        processing = self.root / "processing"
        processing.mkdir(parents=True, exist_ok=True)
        pdf = processing / f"{job_id}.pdf"
        sidecar = processing / f"{job_id}.json"
        pdf.write_bytes(content)
        sidecar.write_text("{}", encoding="utf-8")
        metadata = CaptureMetadata.from_dict({
            "session_id": session,
            "user_id": user,
            "connection_id": connection,
            "document_name": "Quarterly Report",
            "copies": 1,
            "color": True,
            "duplex": False,
        })
        return self.service.submit_captured_job(job_id, pdf, sidecar, metadata)

    def test_correct_session_receives_job_and_wrong_session_is_rejected(self):
        job = self._submit(connection=self.connection_a)
        claimed = self.service.claim_next_job("session-a", self.connection_a, "user-a")
        self.assertEqual(claimed.job_id, job.job_id)
        with self.assertRaises(PermissionError):
            self.service.get_chunk(
                job.job_id,
                0,
                session_id="session-b",
                connection_id=self.connection_b,
                user_id="user-b",
            )

    def test_waiting_claim_wakes_immediately_when_job_arrives(self):
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(
                self.service.claim_next_job,
                "session-a",
                self.connection_a,
                "user-a",
                wait_seconds=2,
            )
            time.sleep(0.05)
            job = self._submit(connection=self.connection_a)
            claimed = waiting.result(timeout=1)

        self.assertEqual(claimed.job_id, job.job_id)

    def test_waiting_claim_has_a_bounded_timeout(self):
        started = time.monotonic()
        claimed = self.service.claim_next_job(
            "session-a", self.connection_a, "user-a", wait_seconds=0.05
        )
        elapsed = time.monotonic() - started

        self.assertIsNone(claimed)
        self.assertGreaterEqual(elapsed, 0.04)
        self.assertLess(elapsed, 0.5)

    def test_no_client_fails_safely(self):
        self.service.registry.unregister_print_client("session-a", self.connection_a)
        with self.assertRaisesRegex(RuntimeError, "No print-capable client"):
            self._submit(connection=None)

    def test_watched_folder_detects_stable_pdf_and_sidecar(self):
        provider = WatchedFolderPrintCaptureProvider(
            self.service, self.root, poll_interval=0.01, stability_seconds=0
        )
        provider._ensure_directories()
        job_id = str(uuid.uuid4())
        (provider.incoming / f"{job_id}.pdf").write_bytes(PDF_BYTES)
        (provider.incoming / f"{job_id}.json").write_text(
            '{"session_id":"session-a","user_id":"user-a",'
            f'"connection_id":"{self.connection_a}",'
            '"document_name":"Watched report","copies":1,"color":true,"duplex":false}',
            encoding="utf-8",
        )
        self.assertEqual(list(provider.get_completed_jobs()), [])
        completed = list(provider.get_completed_jobs())
        self.assertEqual(len(completed), 1)
        captured_id, pdf_path, sidecar_path, metadata = completed[0]
        job = self.service.submit_captured_job(
            captured_id, pdf_path, sidecar_path, metadata
        )
        self.assertEqual(job.state, "ready")
        self.assertTrue(str(job.pdf_path).startswith(str(provider.processing)))

    def test_ambiguous_clients_require_connection_id(self):
        self.service.register_client(
            session_id="session-a",
            connection_id=str(uuid.uuid4()),
            user_id="user-a",
            client_type="desktop",
            capabilities={},
            printers=[],
        )
        with self.assertRaisesRegex(RuntimeError, "connection_id is required"):
            self._submit(connection=None)

    def test_duplicate_chunk_is_idempotent(self):
        job = self._submit(connection=self.connection_a)
        first = self.service.get_chunk(
            job.job_id, 0, session_id="session-a", connection_id=self.connection_a, user_id="user-a"
        )
        duplicate = self.service.get_chunk(
            job.job_id, 0, session_id="session-a", connection_id=self.connection_a, user_id="user-a"
        )
        self.assertEqual(first, duplicate)

    def test_oversized_pdf_is_rejected(self):
        self.service.settings = StaticSettingsStore(PrintingSettings(max_job_size_mb=1))
        with self.assertRaisesRegex(ValueError, "maximum"):
            self._submit(connection=self.connection_a, content=b"%PDF-" + b"x" * (1024 * 1024))

    def test_expired_job_is_rejected(self):
        job = self._submit(connection=self.connection_a)
        from datetime import timedelta
        from backend.printing.models import utcnow

        job.expires_at = utcnow() - timedelta(seconds=1)
        with self.assertRaisesRegex(RuntimeError, "expired"):
            self.service.get_chunk(
                job.job_id, 0, session_id="session-a", connection_id=self.connection_a, user_id="user-a"
            )

    def test_cancellation_cleans_temporary_files(self):
        job = self._submit(connection=self.connection_a)
        self.assertTrue(job.pdf_path.exists())
        cancelled = self.service.cancel_job(job.job_id, user_id="user-a")
        self.assertEqual(cancelled.state, "cancelled")
        self.assertFalse(job.pdf_path.exists())
        self.assertFalse(job.sidecar_path.exists())

    def test_multiple_jobs_can_be_submitted_concurrently(self):
        def submit(_index):
            return self._submit(connection=self.connection_a).job_id

        with ThreadPoolExecutor(max_workers=8) as executor:
            ids = list(executor.map(submit, range(20)))
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20)
        self.assertEqual(len(self.service.list_jobs()), 20)

    def test_browser_download_is_user_bound_expiring_and_single_use(self):
        self.service.registry.unregister_print_client("session-a", self.connection_a)
        browser_connection = str(uuid.uuid4())
        self.service.register_client(
            session_id="session-a",
            connection_id=browser_connection,
            user_id="user-a",
            client_type="browser",
            capabilities={"download": True},
            printers=[],
        )
        job = self._submit(connection=browser_connection)
        token = self.service.issue_browser_download_token(job)
        with self.assertRaises(PermissionError):
            self.service.consume_browser_download(job.job_id, token, "user-b")
        received = self.service.consume_browser_download(job.job_id, token, "user-a")
        self.assertEqual(received.state, "received")
        with self.assertRaises(PermissionError):
            self.service.consume_browser_download(job.job_id, token, "user-a")

    def test_document_name_path_traversal_is_removed(self):
        metadata = CaptureMetadata.from_dict({
            "session_id": "session-a",
            "user_id": "user-a",
            "document_name": "../../secret\\invoice",
            "copies": 1,
            "color": True,
            "duplex": False,
        })
        self.assertNotIn("/", metadata.document_name)
        self.assertNotIn("\\", metadata.document_name)


class DesktopPrintAgentTests(unittest.TestCase):
    def test_hash_mismatch_is_rejected_and_partial_file_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ClientPrintSettingsStore(Path(directory) / "settings.json")
            agent = PrintAgent(
                FakeBinaryConnection(PDF_BYTES),
                store,
                lambda callback, *args: callback(*args),
                Mock(),
            )
            agent.session_id = "session-a"
            agent.temp_root = Path(directory) / "jobs"
            agent.temp_root.mkdir()
            metadata = {
                "job_id": str(uuid.uuid4()),
                "session_id": "session-a",
                "size": len(PDF_BYTES),
                "sha256": "0" * 64,
            }
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                agent._download_job(metadata)
            self.assertEqual(list(agent.temp_root.iterdir()), [])

    def test_printer_discovery_failure_and_no_default_are_safe(self):
        with patch("printing.providers.platform.system", return_value="Linux"):
            self.assertEqual(list_local_printers(), [])
            self.assertIsNone(get_default_printer())


class _PanelUser(UserMixin):
    def __init__(self, user_id, admin=False):
        self.id = user_id
        self.admin = admin

    def has_role(self, *_roles):
        return self.admin


class PrintingAdminAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"
        login_manager = LoginManager(self.app)
        users = {
            "user": _PanelUser("user", admin=False),
            "admin": _PanelUser("admin", admin=True),
        }

        @login_manager.user_loader
        def load_user(user_id):
            return users.get(user_id)

        @self.app.route("/test-login/<user_id>", methods=["POST"])
        def test_login(user_id):
            login_user(users[user_id])
            return {"success": True}

        self.app.register_blueprint(printing_bp)
        self.client = self.app.test_client()

    @patch("backend.api.routers.printing_route.get_print_job_service")
    def test_admin_status_rejects_non_admin(self, service):
        self.client.post("/test-login/user")
        response = self.client.get("/api/printing/status")
        self.assertEqual(response.status_code, 403)
        service.assert_not_called()

    @patch("backend.api.routers.printing_route.get_print_job_service")
    def test_admin_status_allows_admin(self, service_factory):
        service = service_factory.return_value
        service.list_jobs.return_value = []
        service.registry.list_clients.return_value = []
        service.settings.get.return_value.enabled = True
        service.capture_root = Path("spool")
        self.client.post("/test-login/admin")
        response = self.client.get("/api/printing/status")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
