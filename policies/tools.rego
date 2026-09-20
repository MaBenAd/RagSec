package ragsec.tools

import rego.v1

default allow := false

allow if {
    input.action == "tool"
    input.tool == "document_summary"
    "tool" in input.actor.grants
    data.ragsec.data_access.allow with input.action as "read"
}

decision := {"allow": allow, "version": "ragsec-1"}
