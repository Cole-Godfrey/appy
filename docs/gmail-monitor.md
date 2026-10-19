# Optional Gmail monitor

This macOS service listens for Gmail notifications, queues message IDs, and asks a local Codex agent to update Notion. It can be skipped entirely for manual application sessions.

Complete [setup](setup.md), including CLI Gmail and Notion connections, first. The browser agent's connections are not automatically CLI connections. This integration uses experimental App Server endpoints and connector-specific names; `--check` must pass before installation. [App Server documentation](https://learn.chatgpt.com/docs/app-server).

## Cloud project

Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install). Create or select your own Google Cloud project, configure billing if Google requires it, and set a budget alert. You need permission to enable APIs, create Pub/Sub resources, and change the topic's IAM policy. Runtime credentials need Pub/Sub subscriber access and quota-project access.

Use your project ID below; no shared Appy Cloud project exists.

```sh
export APPY_PROJECT="your-project-id"
gcloud auth login
gcloud config set project "$APPY_PROJECT"
gcloud services enable gmail.googleapis.com pubsub.googleapis.com
gcloud pubsub topics create application-email-updates
gcloud pubsub subscriptions create application-email-monitor \
  --topic=application-email-updates
gcloud pubsub topics add-iam-policy-binding application-email-updates \
  --member=serviceAccount:gmail-api-push@system.gserviceaccount.com \
  --role=roles/pubsub.publisher
gcloud auth application-default login
gcloud auth application-default set-quota-project "$APPY_PROJECT"
```

The default subscription above is a pull subscription. The process opens an outgoing StreamingPull connection; it needs no public webhook. Gmail must have publisher rights on the topic. [Google's watch setup](https://developers.google.com/workspace/gmail/api/guides/push) and [local Pub/Sub authentication](https://docs.cloud.google.com/pubsub/docs/authentication).

## Gmail authorization

In [Google Cloud Console](https://console.cloud.google.com/), select your project and open Google Auth Platform:

1. Configure branding, audience, and a support contact you control. Add `https://www.googleapis.com/auth/gmail.metadata` to data access.
2. For an External app in Testing, add your Gmail account as a test user. Testing refresh tokens can expire after seven days for these scopes. Follow Google's publication/verification requirements for your audience; switching publishing status alone does not complete verification. [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
3. Create an OAuth client with application type Desktop app. Download the JSON outside the checkout, such as your Downloads folder. Use a client from the same project as the topic.
4. If Google requests public information pages, provide pages for your own deployment that accurately describe its data use. Do not claim this repository hosts a shared OAuth service. Use [data handling](privacy.md) as a description of Appy's behavior.

Install Python 3.12, then create the runtime environment and authorize the applicant's mailbox. Discovery and the shortlist still support Python 3.10; the Cloud packages need a Python version their maintainers support.

```sh
python3.12 -m venv "$HOME/Library/Application Support/Appy/venv"
"$HOME/Library/Application Support/Appy/venv/bin/python" -m pip install \
  -r requirements-monitor.txt
"$HOME/Library/Application Support/Appy/venv/bin/python" gmail_monitor_setup.py \
  --project "$APPY_PROJECT" --client /absolute/path/to/desktop-client.json
```

The script checks the client project and signed-in Gmail address against INFORMATION.md. It writes `gmail-token.json` and `pubsub.json` under `~/Library/Application Support/Appy/` with mode 600. Google Cloud application-default credentials are separate from this Gmail token. Neither belongs in Git.

## Preflight and start

```sh
"$HOME/Library/Application Support/Appy/venv/bin/python" email_monitor.py --check
python3 monitor_service.py install
python3 monitor_service.py status
```

Preflight verifies Gmail, the pull subscription, the configured Notion tracker, and required tool availability. It does not run an email-processing agent turn. Installation repeats the checks before creating `org.appy.email-monitor` in your user's LaunchAgents. It starts at login and restarts after failure.

Keep the Mac logged in, awake, and online for continuous delivery. After sleep or disconnection, history recovery catches missed arrivals. Watches renew daily; an hourly history check covers dropped notifications. Fresh installations use the first initialized state timestamp as their cutoff and do not process the old inbox. Use the manual catch-up prompt for older mail.

To run in the foreground instead of installing a service:

```sh
"$HOME/Library/Application Support/Appy/venv/bin/python" email_monitor.py
```

## Operations

```sh
python3 monitor_service.py status
python3 monitor_service.py stop
python3 monitor_service.py uninstall
```

`stop` unloads the job; a later login may load its existing plist again. `uninstall` also removes the plist. Both preserve tokens and operational state. To restart, use `install` again.

State, logs, and queue counts live under `~/Library/Application Support/Appy/`. Logs rotate. The SQLite queue stores IDs, cursors, outcomes, and retry state; message bodies are read through Gmail MCP. Relevant evidence is saved in Notion. App Server threads are requested as ephemeral; provider/account data settings still apply.

If Notion fails, Gmail capture continues. Pending work survives restarts and retries after another newly captured email. Idle history checks, duplicate notifications, and watch renewals do not cause processing retries. After reconnecting, either wait for a new arrival or perform a user-requested catch-up in the interactive agent.

## Troubleshooting

| Failure | Check |
| --- | --- |
| Gmail account mismatch | INFORMATION.md, Gmail connector account, and OAuth mailbox must match |
| `Notion MCP unavailable` | Server name must be `notion`; reconnect with `codex mcp login notion` |
| Notion tracker unavailable | Use the data source UUID, grant access, and check `.env` |
| Gmail tool or RPC failure | Verify `codex_apps` exposes the three names in [setup](setup.md); connector changes may require code updates |
| Watch denied | Gmail API enabled, matching OAuth project, and Gmail publisher IAM on the topic |
| Subscription denied | ADC login, selected quota project, Pub/Sub subscriber permission, and a pull subscription |
| Token stopped refreshing | Re-authorize the Gmail client; check Testing token expiration |
| Service starts then exits | Read `monitor.log` and `service.stderr.log` locally; do not post raw account logs |

## Remove access

Uninstall the service, revoke the OAuth app at [Google Account connections](https://myaccount.google.com/connections), and disconnect the agent's Gmail/Notion connectors. Gmail watches expire unless renewed; your own Cloud topic/subscription remain until you remove them. Delete the Appy runtime directory only when you intend to discard its tokens and pending queue. Review Cloud resources separately to stop any charges.
