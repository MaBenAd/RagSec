package system.authz

import rego.v1

default allow := false

allow if {
    input.identity == opa.runtime().env.RAGSEC_OPA_TOKEN
    input.identity != ""
    input.method == "POST"
    input.path in [["v1", "data", "ragsec", "data_access", "decision"],
                   ["v1", "data", "ragsec", "tools", "decision"],
                   ["v1", "data", "ragsec", "memory", "decision"]]
}
