import unittest
from datetime import datetime, timezone
import concurrent.futures

from backend.core.app_factory import create_app
from backend.extensions import db
from backend.models.server import Server
from backend.models.user import User
from backend.services.agent_enrollment_service import AgentEnrollmentService
from backend.services.auth_service import AuthService
from backend.services.portal_service import PortalService, _rdp_identity_for_user
from backend.sockets.agent_socket import handle_agent_connect
from shared.security.password import hash_password


class AgentConcurrencyAndTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app("gateway")
        cls.app_context = cls.app.app_context()
        cls.app_context.push()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        db["agent_enrollment_tokens"].delete_many({})
        db["agent_credentials"].delete_many({})
        db["servers"].delete_many({})
        db["users"].delete_many({})
        db["tenants"].delete_many({})
        db["rdp_sessions"].delete_many({})

    def tearDown(self):
        db["agent_enrollment_tokens"].delete_many({})
        db["agent_credentials"].delete_many({})
        db["servers"].delete_many({})
        db["users"].delete_many({})
        db["tenants"].delete_many({})
        db["rdp_sessions"].delete_many({})

    # ==========================================
    # 1. PYREFLY TYPE CHECK & RDP IDENTITY TESTS
    # ==========================================

    def test_rdp_identity_for_user_type_safety(self):
        user = {
            "username": "testuser",
            "windows_username": "winuser",
            "windows_password": "enc:v1:secretpassword",
        }
        server = {
            "hostname": "win-server",
            "windows_domain": "CORP",
            "username": "admin",
            "password": "enc:v1:serverpass",
        }
        identity = _rdp_identity_for_user(user, server)

        self.assertIsInstance(identity["password"], str)
        self.assertIsInstance(identity["username"], str)
        self.assertIsInstance(identity["domain"], str)
        self.assertIsInstance(identity["isolated"], bool)
        self.assertEqual(identity["username"], "winuser")

    # ==========================================
    # 2. AGENT ENROLLMENT & RECONNECT TESTS
    # ==========================================

    def test_first_agent_enrollment_succeeds(self):
        server = Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        result = AgentEnrollmentService.authenticate_or_enroll({
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.50",
            "hostname": "host-001",
        })
        self.assertIsNotNone(result)
        self.assertEqual(result["server_id"], server.get("_id"))
        self.assertIsNotNone(result.get("new_credential"))

    def test_same_agent_reconnect_succeeds(self):
        server = Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        data = {
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.50",
            "hostname": "host-001",
        }
        res1 = AgentEnrollmentService.authenticate_or_enroll(data)
        cred = res1.get("new_credential") or res1.get("agent_credential")

        data_reconnect = dict(data, agent_credential=cred)
        res2 = AgentEnrollmentService.authenticate_or_enroll(data_reconnect)
        self.assertIsNotNone(res2)
        self.assertEqual(res2["server_id"], server.get("_id"))

    def test_same_agent_reconnect_with_changed_ip_succeeds(self):
        server = Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        data1 = {
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.50",
            "hostname": "host-001",
        }
        res1 = AgentEnrollmentService.authenticate_or_enroll(data1)

        data2 = {
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.51",  # Changed IP
            "hostname": "host-001",
            "agent_credential": res1.get("new_credential"),
        }
        res2 = AgentEnrollmentService.authenticate_or_enroll(data2)
        self.assertIsNotNone(res2)
        self.assertEqual(res2["server_ip"], "192.168.1.51")

        updated_server = Server.collection.find_one({"_id": server.get("_id")})
        self.assertEqual(updated_server["agent_ip"], "192.168.1.51")

    def test_same_agent_reconnect_with_changed_hostname_succeeds(self):
        server = Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        data1 = {
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.50",
            "hostname": "host-old",
        }
        res1 = AgentEnrollmentService.authenticate_or_enroll(data1)

        data2 = {
            "agent_id": "agent-001",
            "machine_id": "mach-001",
            "ip_address": "192.168.1.50",
            "hostname": "host-new",
            "agent_credential": res1.get("new_credential"),
        }
        res2 = AgentEnrollmentService.authenticate_or_enroll(data2)
        self.assertIsNotNone(res2)

        updated_server = Server.collection.find_one({"_id": server.get("_id")})
        self.assertEqual(updated_server["agent_hostname"], "host-new")

    def test_simultaneous_enrollments_do_not_create_duplicate_credentials(self):
        Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        data = {
            "agent_id": "agent-concurrent",
            "machine_id": "mach-concurrent",
            "ip_address": "192.168.1.50",
            "hostname": "host-concurrent",
        }

        def run_enroll():
            with self.app.app_context():
                return AgentEnrollmentService.authenticate_or_enroll(data)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_enroll) for _ in range(4)]
            results = [f.result() for f in futures]

        for res in results:
            self.assertIsNotNone(res)

        credential_count = db["agent_credentials"].count_documents({"agent_id": "agent-concurrent"})
        self.assertLessEqual(credential_count, 1)

    def test_duplicate_ip_belonging_to_another_server_handled_safely(self):
        server1 = Server.create({"name": "Server 1", "host": "192.168.1.10", "is_active": True})
        server2 = Server.create({"name": "Server 2", "host": "192.168.1.20", "is_active": True})

        Server.collection.update_one({"_id": server1.get("_id")}, {"$set": {"agent_ip": "192.168.1.99", "agent_status": "online", "agent_id": "other-agent"}})

        # Enroll agent 2 claiming IP 192.168.1.99
        data = {
            "agent_id": "agent-002",
            "machine_id": "mach-002",
            "ip_address": "192.168.1.99",
            "hostname": "host-002",
        }

        # Should handle gracefully without DuplicateKeyError exception
        res = AgentEnrollmentService.authenticate_or_enroll(data)
        self.assertIsNotNone(res)

    def test_duplicate_key_error_does_not_escape_socket_handler(self):
        Server.create({"name": "Server 1", "host": "192.168.1.50", "is_active": True})
        data = {
            "agent_id": "agent-socket-test",
            "machine_id": "mach-socket",
            "ip_address": "192.168.1.50",
            "hostname": "host-socket",
        }
        with self.app.test_request_context():
            res = handle_agent_connect(data)
            self.assertIsNotNone(res)
            self.assertTrue(isinstance(res, dict))

    # ==========================================
    # 3. REMEMBER ME LOGIN TESTS
    # ==========================================

    def test_remember_me_false_uses_normal_auth(self):
        user_doc = User.create("remuser1", hash_password("pass123"), "User")
        user = User.get_by_id(user_doc["_id"])

        with self.app.test_request_context():
            auth_user, msg, status = AuthService.login("remuser1", "pass123", remember_me=False)
            self.assertEqual(status, 200)
            self.assertIsNotNone(auth_user)

    def test_remember_me_true_persists_auth(self):
        user_doc = User.create("remuser2", hash_password("pass123"), "User")
        user = User.get_by_id(user_doc["_id"])

        with self.app.test_request_context():
            auth_user, msg, status = AuthService.login("remuser2", "pass123", remember_me=True)
            self.assertEqual(status, 200)
            self.assertIsNotNone(auth_user)

    def test_logout_invalidates_persistent_auth(self):
        user_doc = User.create("remuser3", hash_password("pass123"), "User")
        user = User.get_by_id(user_doc["_id"])
        with self.app.test_request_context():
            AuthService.login("remuser3", "pass123", remember_me=True)
            logged_out = AuthService.logout(user)
            self.assertTrue(logged_out)


if __name__ == "__main__":
    unittest.main()
