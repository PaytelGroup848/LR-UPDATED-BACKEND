import unittest

from shared.windows.rds_provisioner import RDS_PROVISIONER_SCRIPT
from shared.windows.remote_app import _REMOTE_APP_SCRIPT


class RDSProvisionerTests(unittest.TestCase):
    def test_rds_provisioner_script_contains_infrastructure_function(self):
        self.assertIn("function Ensure-LRRDSInfrastructure", RDS_PROVISIONER_SCRIPT)

    def test_rds_provisioner_checks_and_installs_rds_features(self):
        self.assertIn("RDS-RD-Server", RDS_PROVISIONER_SCRIPT)
        self.assertIn("RDS-Connection-Broker", RDS_PROVISIONER_SCRIPT)
        self.assertIn("RDS-Web-Access", RDS_PROVISIONER_SCRIPT)
        self.assertIn("RSAT-RDS-Tools", RDS_PROVISIONER_SCRIPT)
        self.assertIn("Install-WindowsFeature", RDS_PROVISIONER_SCRIPT)
        self.assertIn("-IncludeManagementTools", RDS_PROVISIONER_SCRIPT)

    def test_rds_provisioner_manages_rds_services(self):
        self.assertIn("TermService", RDS_PROVISIONER_SCRIPT)
        self.assertIn("SessionEnv", RDS_PROVISIONER_SCRIPT)
        self.assertIn("UmRdpService", RDS_PROVISIONER_SCRIPT)
        self.assertIn("tssdis", RDS_PROVISIONER_SCRIPT)

    def test_rds_provisioner_creates_deployment_and_collection(self):
        self.assertIn("New-RDSessionDeployment", RDS_PROVISIONER_SCRIPT)
        self.assertIn("New-RDSessionCollection", RDS_PROVISIONER_SCRIPT)
        self.assertIn("Get-RDDeployment", RDS_PROVISIONER_SCRIPT)
        self.assertIn("Get-RDSessionCollection", RDS_PROVISIONER_SCRIPT)

    def test_rds_provisioner_handles_reboot_requirement(self):
        self.assertIn("Restart-Computer", RDS_PROVISIONER_SCRIPT)
        self.assertIn("RebootPending", RDS_PROVISIONER_SCRIPT)

    def test_rds_provisioner_verifies_collection_existence(self):
        self.assertIn("$verifiedCollection = Get-RDSessionCollection", RDS_PROVISIONER_SCRIPT)

    def test_remote_app_script_embeds_rds_provisioner(self):
        self.assertIn("function Ensure-LRRDSInfrastructure", _REMOTE_APP_SCRIPT)
        self.assertIn("Ensure-LRRDSInfrastructure -RequestedCollection", _REMOTE_APP_SCRIPT)
        self.assertIn("pending_reboot", _REMOTE_APP_SCRIPT)


if __name__ == "__main__":
    unittest.main()
