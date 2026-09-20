package ragsec.memory

import rego.v1

default allow := false

allow if {
    data.ragsec.data_access.valid
    input.resource.owner == input.actor.id
    input.resource.classification == "private"
    input.resource.status == "active"
    input.action in {"memory_read", "memory_write", "memory_delete"}
    input.action in input.actor.grants
}

decision := {"allow": allow, "version": "ragsec-1"}
