# Security

Report credential exposure, unintended submissions, prompt-injection paths, or private data leaks through [GitHub's private vulnerability reporting](https://github.com/Cole-Godfrey/appy/security/advisories/new). Include a minimal reproduction with synthetic data. Do not publish live tokens, applicant information, or mailbox content in an issue.

Only the current `main` branch receives fixes. No response time is promised. For an accidentally exposed credential, revoke it at its provider and remove the affected public data; deleting a file from the latest commit does not erase history.

The workflow relies on model behavior and third-party connectors. Review scopes, start with one reviewed application, and limit the agent's authorization to the task you want performed. See [data handling](docs/privacy.md).
