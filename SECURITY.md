# Security

Please report a vulnerability privately through GitHub's "Report a vulnerability" button on
the Security tab of this repository (private vulnerability reporting), not in a public issue.

Useful to know when assessing a report: render code written by the agent runs inside the
container with network access and the `/work` volume mounted; that is by design, and the
container is the only sandbox. A path escape from a project directory, a way around the
bearer token in HTTP mode, or a way to read an API key through a tool would all be bugs.
