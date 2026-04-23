# Security policy

## Supported versions

Only the latest released version of tuimanji receives security fixes. Pin
to a specific version in production and update when advisories are posted
to the repository's [security advisories](https://github.com/alanbato/tuimanji/security/advisories).

## Threat model

Tuimanji is designed for **cooperating users sharing a single machine**
(pubnix boxes, lab servers, your own workstation). It is explicitly **not**
a trust boundary:

- Any user with read access to `$TUIMANJI_DB/tuimanji.db` can see every
  match's full state, including hidden-information games (Battleship ship
  placement, Crazy Eights hands). Set filesystem permissions on the DB
  directory to match your threat model.
- Any user with write access can submit moves as themselves or tamper with
  the database directly.
- Session slots use `flock(2)` for mutual exclusion, not authentication —
  they prevent accidental double-claim, not malicious impersonation.

If you need confidentiality or authenticated moves across mutually
distrustful users, tuimanji isn't the right tool — you'd want a real
network protocol and a server process, which is explicitly not the design.

## Reporting a vulnerability

For issues that don't fit the threat model above (arbitrary code execution
from a crafted `action`, path traversal via `TUIMANJI_DB`, SQL injection
through move input, etc.):

1. **Do not open a public issue.**
2. Email **alanvelasco.a@gmail.com** with:
   - A description of the issue
   - Steps to reproduce
   - The tuimanji version (`tuimanji --version`)
   - Your suggested severity
3. You should receive an acknowledgement within 7 days. A fix target
   follows after triage.

For issues that clearly fit the "shared machine, no trust boundary" model
described above, feel free to open a public issue or PR instead — they're
part of the design and documenting them helps users set expectations.
