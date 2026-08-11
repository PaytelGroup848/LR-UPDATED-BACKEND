from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    description: str
    blueprints: tuple[str, ...]
    sockets: bool = False
    rdp_namespace: bool = False


GATEWAY_BLUEPRINTS = (
    "admin_features",
    "agent",
    "apps",
    "auth",
    "files",
    "logs",
    "lr",
    "license_admin",
    "portal",
    "printing",
    "process",
    "server",
    "services",
    "sessions",
    "terminal",
    "windows",
)


SERVICE_SPECS = {
    "gateway": ServiceSpec(
        name="gateway",
        description="LR Platform gateway",
        blueprints=GATEWAY_BLUEPRINTS,
        sockets=True,
        rdp_namespace=True,
    ),
    "portal": ServiceSpec(
        name="portal",
        description="User portal",
        blueprints=("auth", "portal", "apps", "sessions", "lr"),
        sockets=True,
    ),
    "admin": ServiceSpec(
        name="admin",
        description="Admin APIs",
        blueprints=GATEWAY_BLUEPRINTS,
        sockets=True,
        rdp_namespace=True,
    ),
    "agent": ServiceSpec(
        name="agent",
        description="Agent and streaming APIs",
        blueprints=("agent", "terminal", "process", "windows", "services"),
        sockets=True,
    ),
}


def get_service_spec(name: str) -> ServiceSpec:
    return SERVICE_SPECS.get(name, SERVICE_SPECS["gateway"])
