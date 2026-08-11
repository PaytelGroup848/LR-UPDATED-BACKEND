import unittest
from unittest.mock import Mock, patch

from bson import ObjectId

from backend.services.agent_enrollment_service import AgentEnrollmentService
from backend.services.agent_presence_service import AgentPresenceService


MACHINE_A = "a" * 64
MACHINE_B = "b" * 64


class MachineBoundEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.tokens = Mock()
        self.credentials = Mock()
        self.server_collection = Mock()
        self.server_collection.find_one.return_value = None
        self.tokens_patch = patch.object(AgentEnrollmentService, "tokens", self.tokens)
        self.credentials_patch = patch.object(
            AgentEnrollmentService,
            "credentials",
            self.credentials,
        )
        self.server_collection_patch = patch(
            "backend.services.agent_enrollment_service.Server.collection",
            self.server_collection,
        )
        self.tokens_patch.start()
        self.credentials_patch.start()
        self.server_collection_patch.start()

    def tearDown(self):
        self.server_collection_patch.stop()
        self.credentials_patch.stop()
        self.tokens_patch.stop()

    @patch("backend.services.agent_enrollment_service.tenant_id_from_user")
    @patch("backend.services.agent_enrollment_service.Server.get_by_id")
    def test_issue_binds_token_to_matching_local_machine(
        self,
        get_server,
        tenant_id_from_user,
    ):
        tenant_id = ObjectId()
        server_id = ObjectId()
        tenant_id_from_user.return_value = tenant_id
        get_server.return_value = {
            "_id": server_id,
            "tenant_id": tenant_id,
            "host": "10.20.30.40",
        }
        actor = Mock(id=ObjectId())

        result = AgentEnrollmentService.issue(
            actor,
            str(server_id),
            {
                "machine_id": MACHINE_A,
                "hostname": "WIN-SERVER-01",
                "ip_addresses": ["10.20.30.40"],
            },
        )

        self.assertTrue(result["enrollment_token"])
        inserted = self.tokens.insert_one.call_args.args[0]
        self.assertEqual(inserted["expected_machine_id"], MACHINE_A)
        self.assertEqual(inserted["server_id"], server_id)

    @patch("backend.services.agent_enrollment_service.tenant_id_from_user")
    @patch("backend.services.agent_enrollment_service.Server.get_by_id")
    def test_issue_allows_machine_binding_even_when_server_host_differs(
        self,
        get_server,
        tenant_id_from_user,
    ):
        tenant_id = ObjectId()
        server_id = ObjectId()
        tenant_id_from_user.return_value = tenant_id
        get_server.return_value = {
            "_id": server_id,
            "tenant_id": tenant_id,
            "host": "191.44.87.46",
        }

        result = AgentEnrollmentService.issue(
            Mock(id=ObjectId()),
            str(server_id),
            {
                "machine_id": MACHINE_A,
                "hostname": "WIN-CLOUD87VM38",
                "ip_addresses": ["191.44.87.38"],
            },
        )

        self.assertTrue(result["enrollment_token"])
        inserted = self.tokens.insert_one.call_args.args[0]
        self.assertEqual(inserted["expected_machine_id"], MACHINE_A)
        self.assertEqual(inserted["server_id"], server_id)

    @patch("backend.services.agent_enrollment_service.Server.collection")
    def test_valid_token_replaces_old_binding_and_persists_machine(
        self,
        server_collection,
    ):
        tenant_id = ObjectId()
        server_id = ObjectId()
        self.tokens.find_one_and_update.return_value = {
            "tenant_id": tenant_id,
            "server_id": server_id,
            "expected_machine_id": MACHINE_B,
        }

        result = AgentEnrollmentService.authenticate_or_enroll({
            "agent_id": MACHINE_B,
            "machine_id": MACHINE_B,
            "agent_credential": "",
            "enrollment_token": "one-time-token",
            "hostname": "PAYTEL-SERVER",
            "ip_addresses": ["191.44.87.46"],
        })

        self.assertEqual(result["tenant_id"], tenant_id)
        self.assertEqual(result["server_id"], server_id)
        self.assertEqual(result["machine_id"], MACHINE_B)
        self.assertTrue(result["new_credential"])
        self.credentials.update_many.assert_called_once()
        credential_update = self.credentials.update_one.call_args.args[1]["$set"]
        self.assertEqual(credential_update["machine_id"], MACHINE_B)
        server_update = server_collection.update_one.call_args.args[1]["$set"]
        self.assertEqual(server_update["agent_machine_id"], MACHINE_B)
        self.assertEqual(server_update["agent_hostname"], "PAYTEL-SERVER")

    def test_legacy_unbound_credential_is_not_accepted(self):
        self.credentials.find_one.return_value = None

        result = AgentEnrollmentService.authenticate_or_enroll({
            "agent_id": "legacy-agent",
            "machine_id": MACHINE_A,
            "agent_credential": "legacy-credential",
        })

        self.assertIsNone(result)
        query = self.credentials.find_one.call_args.args[0]
        self.assertEqual(query["machine_id"], MACHINE_A)


class AgentPresenceScaleTests(unittest.TestCase):
    def setUp(self):
        AgentPresenceService._memory.clear()

    def tearDown(self):
        AgentPresenceService._memory.clear()

    @patch.object(AgentPresenceService, "redis_client", return_value=None)
    def test_three_thousand_server_presence_records_route_exactly(self, _redis):
        for index in range(3000):
            AgentPresenceService.register({
                "tenant_id": f"tenant-{index % 25}",
                "server_id": f"server-{index}",
                "agent_id": f"agent-{index}",
                "connection_id": f"sid-{index}",
                "status": "online",
            })

        self.assertEqual(AgentPresenceService.online_count(), 3000)
        exact = AgentPresenceService.get_server("tenant-7", "server-1232")
        self.assertEqual(exact["agent_id"], "agent-1232")
        self.assertEqual(exact["connection_id"], "sid-1232")

    @patch.object(AgentPresenceService, "redis_client", return_value=None)
    def test_mongo_object_ids_are_normalized_for_presence_routing(self, _redis):
        tenant_id = ObjectId()
        server_id = ObjectId()

        AgentPresenceService.register({
            "tenant_id": tenant_id,
            "server_id": server_id,
            "agent_id": MACHINE_A,
            "connection_id": "sid-object-id",
            "status": "online",
        })

        exact = AgentPresenceService.get_server(str(tenant_id), str(server_id))
        self.assertEqual(exact["tenant_id"], str(tenant_id))
        self.assertEqual(exact["server_id"], str(server_id))
        self.assertEqual(exact["agent_id"], MACHINE_A)


if __name__ == "__main__":
    unittest.main()
