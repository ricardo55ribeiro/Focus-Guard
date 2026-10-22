# Security

Security fixes target the latest source on the default branch. Run the supported
Python version listed in README.md and install the pinned requirements.

## Reporting

Use the repository's **Security → Report a vulnerability** option when enabled.
Do not include credentials, browsing history, private URLs, or personal settings
in public issues. If private reporting is unavailable, open an issue requesting
a private contact channel without publishing exploit details.

Maintainers should enable GitHub private vulnerability reporting, Dependabot
alerts, and secret scanning/push protection when publishing. These are repository
settings and are not enabled by adding this file.

## Boundaries

FocusGuard is a voluntary focus aid, not a security boundary, parental-control
system, or tamper-resistant application. The current user can stop it or change
its settings. AI classification can be wrong or influenced by page titles.

The browser receiver binds only to IPv4 loopback, validates the Host and Origin,
requires JSON, limits request size, and does not grant cross-origin access to
websites. It has no pairing secret: local applications and other installed
extensions with loopback permission are trusted and can send requests. Do not
forward port 9001 or expose it through a reverse proxy. Port 9002 is used for
local single-instance activation. The AI client uses 127.0.0.1:11434 directly;
an independently configured Ollama server remains under the user's control.

Local session files contain sensitive activity and have no automatic expiry or
application-level encryption. See [the privacy policy](Privacy%20Policy.txt).

## Extension identity

The Firefox `browser_specific_settings.gecko.id` is the existing add-on's public
identifier. Its email-shaped value is intentionally retained for signed update
compatibility. It is not a credential or a reporting address. Changing it creates
a different extension identity and requires a separate signing/listing workflow.

## Source and release hygiene

Do not publish local settings, logs, caches, environment files, signing keys,
installer downloads, or old ZIPs. `.gitignore` protects new additions only; it
does not remove files or personal author emails from existing Git history.
Use a reviewed, clean export for the first public release when the private
history contains such data. Never copy the old `.git` directory into it.

The desktop installer downloads the official Ollama executable over HTTPS into
an isolated temporary directory. It does not ship the executable or model weights.

References: [GitHub history cleanup](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository),
[private reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).
