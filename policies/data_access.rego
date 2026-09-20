package ragsec.data_access

import rego.v1

default allow := false

valid if {
    input.policy_version == "ragsec-1"
    input.actor.enabled == true
    input.actor.id > 0
    input.actor.access_version > 0
    input.resource.access_version > 0
    input.resource.version > 0
    input.actor.tenant == input.resource.tenant
    input.resource.classification in {"public", "private", "restricted"}
    input.resource.owner > 0
    is_string(input.resource.id)
    input.resource.id != ""
}

readable if { input.resource.classification == "public" }
readable if { input.resource.owner == input.actor.id }

allow if {
    valid
    input.action in {"read", "cite", "download"}
    input.action in input.actor.grants
    input.resource.status == "indexed"
    readable
}

allow if {
    valid
    input.action == "preview"
    "read" in input.actor.grants
    readable
    input.resource.status in {"staged", "scanned", "quarantined", "approved", "indexed"}
}

allow if {
    valid
    input.actor.role == "admin"
    input.action in {"ingest", "approve", "delete", "publish", "manage"}
    input.action in input.actor.grants
}

decision := {"allow": allow, "version": "ragsec-1"}
