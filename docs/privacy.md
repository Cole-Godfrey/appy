# Data handling

Personal files remain in your checkout or runtime directory unless you or the agent send them to a connected service. Appy does not run a shared server or add analytics. Local execution still sends data to your selected AI provider and the services used for the task.

| Recipient / storage | Information involved |
| --- | --- |
| AI agent provider | Prompts, relevant applicant facts, browser content, and selected email content used by a task |
| Employer / application platform | Form answers and uploaded documents when authorized |
| Simplify | Its connected profile, resume, and autofill activity under its own terms |
| Notion | Application records and relevant receipt/recruiting evidence |
| Gmail connector | Account profile, code messages, and recruiting messages read for a task |
| Google Cloud Pub/Sub | Mailbox notification metadata, including email address and history ID |
| Optional TheirStack | Search filters and API credentials for its requests |
| Local checkout | Private profile, documents, questions, pending actions, temporary exports |
| Local Appy runtime | OAuth token, Cloud config, message IDs/cursors, outcomes, retries, and operational logs |

The detector's direct Gmail OAuth scope is `gmail.metadata`; email bodies use the separately connected Gmail MCP tool. This separation does not reduce the permissions granted to that connector. Review its actual permission screen.

`.gitignore` and the publication check reduce accidental commits. They do not encrypt files, remove existing Git history, or replace reviewing what you publish. Store applicant documents under `private/`. Remove temporary exports after use. Before sharing screenshots, check names, addresses, tabs, account photos, document paths, and tracker contents.

To stop processing, stop/uninstall the monitor and disconnect its tools. Revoke Google OAuth access through your account, then remove local tokens/state and remote application evidence as appropriate. Uninstalling the service alone preserves data. See [monitor removal](gmail-monitor.md#remove-access).
