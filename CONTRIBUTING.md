# Contributing

Use Windows and Python 3.11 or newer. Create a virtual environment and install
`requirements.txt`. Keep dependencies pinned together; verify updates before
changing the resolved versions.

From the repository root:

```powershell
python -m unittest discover -s tests -v
node --test tests/extension.test.js
python -m compileall -q agent install.py tools tests
node --check extension/background.js
node --check extension/blocking.js
```

Security checks (development tools, not runtime dependencies):

```powershell
python -m pip install pip-audit detect-secrets bandit
python -m pip_audit -r requirements.txt --no-deps --disable-pip
detect-secrets scan --all-files agent extension tests tools README.md requirements.txt
python -m bandit -r agent install.py
```

Review scanner findings; a scan is not proof that a project is secure. Keep
security tests that verify rejected requests and successful extension traffic.
Exercise Windows startup, tray interactions, real browsers, and local Ollama
when changing those integrations. Automated tests mock AI responses and do not
download models or modify your startup registry entries.

Use synthetic URLs, titles, goals, and settings in tests and bug reports. Never
attach your real session logs, browser profile, `.env`, or settings file.

Changes to the add-on require a separate browser-store submission. Keep the
Firefox ID stable for updates. Preserve the project's GPL-3.0 license and
document any separately licensed dependencies or assets.
