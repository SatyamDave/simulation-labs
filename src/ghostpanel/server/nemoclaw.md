# NemoClaw / NVIDIA OpenShell integration (optional stretch)

Status: **optional, zero hard dependency.** Ghostpanel supports routing Holo inference
through the NVIDIA OpenShell policy gateway managed by NemoClaw. If `NEMOCLAW_GATEWAY_URL`
is unset (the default), the swarm calls the Holo Models API directly and nothing below applies.

## How Ghostpanel wires it

- `Settings.nemoclaw_gateway_url` is read from `NEMOCLAW_GATEWAY_URL` (`server/config.py`).
- `Settings.holo_base_url` returns `NEMOCLAW_GATEWAY_URL` when set, else `HAI_BASE_URL`.
- The composition root (`server/swarm.py::_default_holo_factory`) builds the ONE shared
  `LiveHoloClient` with `settings.holo_base_url` — so setting the env var is the entire
  switch. Holo is OpenAI-compatible, and OpenShell fronts OpenAI-compatible endpoints,
  so no other code changes.

```bash
# .env — route swarm inference through the OpenShell gateway
NEMOCLAW_GATEWAY_URL=http://127.0.0.1:<gateway-port>/v1/
```

Per the NemoClaw docs, external inference providers are reached *through the OpenShell
gateway, not by direct sandbox egress*, and NemoClaw runs a **deny-by-default** network
policy: the sandbox reaches only explicitly allowed endpoints; anything else is intercepted
and surfaced for operator approval in the TUI (`openshell term`).

## Real policy schema (pulled live 2026-07-12, not fabricated)

Sources:
- https://docs.nvidia.com/nemoclaw/user-guide/openclaw/reference/network-policies.md
- https://docs.nvidia.com/nemoclaw/user-guide/openclaw/network-policy/customize-network-policy.md

The baseline policy lives in `nemoclaw-blueprint/policies/openclaw-sandbox.yaml`. Each
entry in the `network` section defines an endpoint group with fields:

- `endpoints` — host/port pairs the sandbox can reach
- `binaries` — executables allowed to use this endpoint
- `rules` — HTTP methods and paths that are permitted

Verbatim preset example from the docs (the NemoClaw-supported way to merge new entries
into a running policy is `nemoclaw <sandbox> policy-add` with a preset file under
`nemoclaw-blueprint/policies/presets/`):

```yaml
preset:
  name: influxdb
  description: "InfluxDB time-series database"
network_policies:
  influxdb:
    name: influxdb
    endpoints:
      - host: influxdb.internal.example.com
        port: 8086
        protocol: rest
        enforcement: enforce
        rules:
          - allow: { method: GET, path: "/**" }
          - allow: { method: POST, path: "/api/v2/write" }
    binaries:
      - { path: /usr/bin/curl }
```

Adapting that documented schema for Ghostpanel's Holo egress (host/paths are ours; the
structure is exactly the documented one above):

```yaml
preset:
  name: ghostpanel-holo
  description: "H Company Holo Models API for the Ghostpanel swarm"
network_policies:
  ghostpanel_holo:
    name: ghostpanel_holo
    endpoints:
      - host: api.hcompany.ai
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow: { method: POST, path: "/v1/**" }
    binaries:
      - { path: /usr/local/bin/python3 }
```

Apply with `nemoclaw <sandbox-name> policy-add`. Caveats from the docs worth repeating:

- `openshell policy set` **replaces** the live policy (no merge) — prefer `policy-add`.
- Dynamic single-endpoint add:
  `openshell policy update <sandbox> --add-endpoint api.hcompany.ai:443:read-only:rest:enforce`
- SSRF protection applies separately: requests resolving to loopback/private ranges can
  still be denied even when the host is allowlisted.
- On-device Nemotron inference needs a GPU — out of scope for the Mac demo; only the
  gateway routing above is supported.
