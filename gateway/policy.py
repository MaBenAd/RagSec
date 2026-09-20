"""OPA is mandatory. Undefined, malformed and unavailable decisions deny."""
import httpx
from gateway.config import POLICY_VERSION
from gateway.contracts import Actor, Resource
from gateway.errors import ControlError


class Policy:
    def __init__(self, url: str, *, transport=None, token: str | None = None):
        self.client = httpx.Client(
            base_url=url, timeout=1.5, transport=transport, trust_env=False,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    def require(self, actor: Actor, action: str, resource: Resource, *, tool: str = "") -> None:
        package = "tools" if action == "tool" else "memory" if action.startswith("memory_") else "data_access"
        payload = {"actor": actor.model_dump(mode="json"), "action": action,
                   "resource": resource.model_dump(mode="json"), "tool": tool,
                   "policy_version": POLICY_VERSION}
        try:
            import json
            with self.client.stream("POST", f"/v1/data/ragsec/{package}/decision", json={"input": payload}) as response:
                response.raise_for_status()
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > 4096:
                        raise ValueError("size")
            result = json.loads(data)["result"]
            if (not isinstance(result, dict) or set(result) != {"allow", "version"}
                    or type(result["allow"]) is not bool or result["version"] != POLICY_VERSION):
                raise ValueError("decision")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ControlError("policy_unavailable", "unavailable") from None
        if not result["allow"]:
            raise ControlError("policy_denied")

    def ready(self) -> bool:
        actor = Actor(id=1, tenant="readiness", role="member", enabled=True,
                      access_version=1, grants=("read",))
        resource = Resource(id="readiness", tenant="readiness", owner=1,
                            classification="public", status="indexed", version=1, access_version=1)
        try:
            self.require(actor, "read", resource)
            self.require(actor, "read", resource.model_copy(update={"tenant": "different"}))
        except ControlError as exc:
            return exc.reason == "policy_denied"
        return False
