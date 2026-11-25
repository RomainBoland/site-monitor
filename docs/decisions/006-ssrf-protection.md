# 006 — SSRF protection: allow only public IPs, checked at registration and before each check

- Status: accepted
- Date: 2026-11-25

## Context

The service fetches URLs chosen by users, from inside the server's network. Without protection, an attacker could register URLs that reach things only the server can reach (Server-Side Request Forgery):

- the cloud metadata service (`169.254.169.254`), which can return credentials (the Capital One breach, 2019);
- services bound to localhost (admin panels, debug ports, databases);
- other containers or hosts on the private network (Prometheus, Grafana in the final architecture).

Even though the checker only reports up/down, status code and response time, this is enough for **blind SSRF**: mapping the internal network from timing and status codes.

Hostname text cannot be trusted: `127.0.0.1` can be written as `2130706433`, `0x7f000001`, `127.1`, `localhost.`, `[::ffff:127.0.0.1]`, or hidden behind any domain name. DNS answers can also change after registration (DNS rebinding), and a public site can redirect to an internal address.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| 1. Check only at registration | Simplest; instant 422 feedback | Bypassed by changing DNS later or by redirects |
| **2. One check function, used at registration and before every check; no automatic redirects** | Closes the "DNS changed later" hole; one tested function used twice | A small window remains between our DNS lookup and the HTTP client's own lookup |
| 3. Option 2 + connect to the exact IP that was checked (custom transport) | Closes the remaining window | Fiddly (TLS/SNI, client internals); hard to defend as a junior |

## Decision

Option 2, in `site_monitor/ssrf.py`, with the standard library only (`socket`, `ipaddress`, `urllib.parse`):

- Resolve the host with `socket.getaddrinfo` (IPv4 and IPv6), and judge the **resolved IPs**, never the hostname text.
- **Allowlist**: an IP passes only if `is_global` is true and it is not multicast (Python 3.13 reports multicast as global). Verified on Python 3.13.18 to reject loopback, private, link-local/metadata, carrier-grade NAT, reserved and documentation ranges, `0.0.0.0`, IPv6 loopback/link-local/unique-local and IPv4-mapped IPv6 such as `::ffff:127.0.0.1`.
- Reject if **any** resolved IP is not public, because the HTTP client may connect to any of them.
- Reject hostnames that do not resolve: we cannot prove they are safe.
- `POST /targets` returns `422` with the reason. Step 7 must call `check_url_is_public` before every check and must not follow redirects automatically.

## Consequences

- Tests never use the network: `resolve_host` is replaced by a fake DNS table in `tests/conftest.py`. The fake resolves IP literals to themselves, like the real one, so tests fail for the right reason (their assertions check the error message). Disabling the IP check makes 25 tests fail.
- A site that is temporarily unresolvable cannot be registered.
- **Known gaps:**
  - the time-of-check/time-of-use window between our lookup and the HTTP client's lookup (option 3 would close it);
  - NAT64 addresses (`64:ff9b::/96`) embedding a private IPv4 are reported as global by Python. They are only reachable on networks with a NAT64 gateway, which the target VPS does not have.
- Defense in depth for later (step 10 or deployment): an egress firewall rule blocking the container's outgoing traffic to private ranges.

## I would choose differently if...

- the service were public and multi-tenant, or ran on a cloud with a sensitive metadata service: option 3 plus a network-level egress block;
- users had to monitor internal services on purpose (an intranet monitor): then an explicit allowlist of permitted internal hosts would replace the blanket "public only" rule.
