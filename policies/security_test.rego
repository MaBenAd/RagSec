package ragsec.tests

import rego.v1

request := {
    "policy_version": "ragsec-1", "action": "read", "tool": "document_summary",
    "actor": {"id": 1, "tenant": "alpha", "role": "member", "enabled": true, "access_version": 1,
              "grants": ["read", "cite", "download", "tool", "memory_read", "memory_write", "memory_delete"]},
    "resource": {"id": "doc", "tenant": "alpha", "owner": 2, "classification": "public",
                 "status": "indexed", "version": 1, "access_version": 1},
}

test_public_read if { data.ragsec.data_access.allow with input as request }
test_cross_tenant_denied if {
    not data.ragsec.data_access.allow with input as request with input.resource.tenant as "beta"
}
test_private_denied if {
    not data.ragsec.data_access.allow with input as request with input.resource.classification as "private"
}
test_private_owner_allowed if {
    data.ragsec.data_access.allow with input as request with input.resource.classification as "private" with input.resource.owner as 1
}
test_missing_context_denied if { not data.ragsec.data_access.allow with input as {} }
test_disabled_denied if { not data.ragsec.data_access.allow with input as request with input.actor.enabled as false }
test_unknown_version_denied if { not data.ragsec.data_access.allow with input as request with input.policy_version as "other" }
test_revoked_denied if { not data.ragsec.data_access.allow with input as request with input.resource.status as "revoked" }
test_unapproved_denied if { not data.ragsec.data_access.allow with input as request with input.resource.status as "approved" }
test_admin_not_private_reader if {
    not data.ragsec.data_access.allow with input as request with input.actor.role as "admin" with input.resource.classification as "private"
}
test_manage_admin if {
    data.ragsec.data_access.allow with input as request with input.action as "approve" with input.actor.role as "admin" with input.actor.grants as ["approve"]
}
test_manage_member_denied if {
    not data.ragsec.data_access.allow with input as request with input.action as "approve" with input.actor.grants as ["approve"]
}
test_tool_allowed if { data.ragsec.tools.allow with input as request with input.action as "tool" }
test_unknown_tool_denied if { not data.ragsec.tools.allow with input as request with input.action as "tool" with input.tool as "shell" }
test_tool_cross_tenant_denied if { not data.ragsec.tools.allow with input as request with input.action as "tool" with input.resource.tenant as "beta" }
test_memory_owner_allowed if {
    data.ragsec.memory.allow with input as request with input.action as "memory_read" with input.resource.classification as "private" with input.resource.status as "active" with input.resource.owner as 1
}
test_memory_other_denied if {
    not data.ragsec.memory.allow with input as request with input.action as "memory_read" with input.resource.classification as "private" with input.resource.status as "active"
}
