import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


DESKTOP_CLIENT_DIR = Path(__file__).resolve().parents[1] / "desktop-client"
if str(DESKTOP_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_CLIENT_DIR))

# pyrefly: ignore [missing-import]
from session import (
    AgentCredentialStore,
    WindowsCredentialCache,
    _credential_targets,
    prepare_rdp_for_single_sign_on,
)


class RdpSingleSignOnTests(unittest.TestCase):
    def test_rdp_uses_secure_cache_without_writing_plaintext_password(self):
        cache = Mock()
        content = (
            "full address:s:191.44.87.38\r\n"
            "username:s:mycompany\\Paytel\r\n"
            "prompt for credentials:i:1\r\n"
            "promptcredentialonce:i:0\r\n"
            "remoteapplicationmode:i:1\r\n"
        ).encode("utf-8")

        prepared = prepare_rdp_for_single_sign_on(content, "secret-password", cache)
        text = prepared.decode("utf-8")

        cache.store.assert_called_once_with(
            ["TERMSRV/191.44.87.38"],
            "mycompany\\Paytel",
            "secret-password",
            domain="mycompany",
        )
        self.assertIn("prompt for credentials:i:0", text)
        self.assertIn("promptcredentialonce:i:1", text)
        self.assertIn("remoteapplicationmode:i:1", text)
        self.assertNotIn("secret-password", text)
        self.assertNotIn("password 51", text.lower())

    def test_unqualified_username_is_domain_qualified_for_rdp(self):
        cache = Mock()
        content = (
            "full address:s:191.44.87.48\r\n"
            "username:s:ACCOUNTS1\r\n"
        ).encode("utf-8")

        prepared = prepare_rdp_for_single_sign_on(content, "secret-password", cache)
        text = prepared.decode("utf-8")

        self.assertIn("username:s:ACCOUNTS1", text)
        self.assertIn("enablecredsspsupport:i:1", text)
        self.assertIn("prompt for credentials:i:0", text)
        self.assertIn("promptcredentialonce:i:1", text)
        cache.store.assert_called_once_with(["TERMSRV/191.44.87.48"], "ACCOUNTS1", "secret-password", domain="")

    def test_non_default_port_registers_exact_and_host_targets(self):
        self.assertEqual(
            _credential_targets("server.example.test:3390"),
            [
                "TERMSRV/server.example.test:3390",
                "TERMSRV/server.example.test",
            ],
        )

    def test_missing_rdp_identity_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "server address or Windows username"):
            prepare_rdp_for_single_sign_on(
                b"screen mode id:i:2\r\n",
                "secret-password",
                Mock(),
            )


class AgentCredentialStoreTests(unittest.TestCase):
    def test_dpapi_store_roundtrip_with_mocked_dpapi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "credentials.dpapi"
            store = AgentCredentialStore(store_path)

            with patch("session.credential_store._protect", side_effect=lambda b: b"PROTECTED_" + b), \
                 patch("session.credential_store._unprotect", side_effect=lambda b: b[10:]):
                payload = {"username": "domain\\user", "password": "secure-password", "company_code": "COMP"}
                store.save(payload)
                self.assertTrue(store_path.exists())

                loaded = store.load()
                self.assertEqual(loaded, payload)

                store.clear()
                self.assertFalse(store_path.exists())
                self.assertEqual(store.load(), {})


class WindowsCredentialCacheTests(unittest.TestCase):
    def test_temporary_entry_is_deleted_on_restore(self):
        api = Mock()
        api.CRED_TYPE_DOMAIN_PASSWORD = 2
        api.CRED_TYPE_GENERIC = 1
        api.CRED_PERSIST_LOCAL_MACHINE = 2
        api.CredRead.side_effect = RuntimeError("not found")
        cache = WindowsCredentialCache()
        cache._api = Mock(return_value=api)

        cache.store(["TERMSRV/server"], "LAB\\alice", "secret")
        cache.restore_all()

        written = api.CredWrite.call_args_list[0].args[0]
        self.assertEqual(written["TargetName"], "TERMSRV/server")
        self.assertEqual(written["Persist"], api.CRED_PERSIST_LOCAL_MACHINE)
        self.assertEqual(api.CredDelete.call_count, 2)

    def test_existing_windows_credential_is_restored_on_logout(self):
        previous = {
            "Type": 1,
            "TargetName": "TERMSRV/server",
            "UserName": "LAB\\previous",
            "CredentialBlob": "previous-secret",
            "Persist": 2,
        }
        api = Mock()
        api.CRED_TYPE_DOMAIN_PASSWORD = 2
        api.CRED_TYPE_GENERIC = 1
        api.CRED_PERSIST_LOCAL_MACHINE = 2
        api.CredRead.return_value = previous
        cache = WindowsCredentialCache()
        cache._api = Mock(return_value=api)

        cache.store(["TERMSRV/server"], "LAB\\alice", "new-secret")
        cache.restore_all()

        self.assertGreaterEqual(api.CredWrite.call_count, 4)
        restored = api.CredWrite.call_args_list[-1].args[0]
        self.assertEqual(restored["UserName"], "LAB\\previous")
        self.assertEqual(restored["CredentialBlob"], "previous-secret")
        api.CredDelete.assert_not_called()


if __name__ == "__main__":
    unittest.main()

