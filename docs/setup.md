# Setup

## What you need

| Use | Requirements |
| --- | --- |
| Offline demo | Git, Python 3.10+; no accounts or packages |
| Live discovery | Python and network access; a complete tracker export |
| Browser applications | A local agent with Chrome, Gmail, and Notion tools; Chrome and Simplify |
| Background email monitor | macOS, Python 3.11+ (3.12 recommended), Codex CLI with compatible connectors, Google Cloud CLI/project, monitor packages |

The browser workflow runs in a local agent session such as ChatGPT Work with Chrome. Installing the Codex CLI alone does not provide signed-in browser control. The optional monitor uses Codex's App Server and specific tool names; its preflight checks compatibility.

Appy is free under the MIT license. Your agent plan or API usage, TheirStack searches, and Google Cloud resources may cost money. Check those providers' pricing and set your own limits.

## Clone and try

```sh
git clone https://github.com/Cole-Godfrey/appy.git
cd appy
python3 scripts/demo.py
python3 -m unittest discover -v
python3 setup_workspace.py
```

Setup creates private working files from `templates/` and `.env.example`, plus `private/` and `tmp/`. Re-running it preserves existing files. It does not install software, connect accounts, or change system services.

## Add your profile

Edit `INFORMATION.md`. Fill in every fact you want the agent to use, remove unwanted optional fields, and answer eligibility and demographic preferences yourself. Put your resume at `private/resume.pdf`, or set its actual path in the profile.

Add exact target company names as bullets in `CAREER-FAIR-COMPANIES.md` if you want company searches. Leave the file empty otherwise. `QUESTIONS.md` and `NEXT-STEPS.md` start without application records.

These files are Git-ignored. Before publishing changes, run `git status --short` and `python3 scripts/check_public.py`. Do not force-add private files.

## Connect the browser and Gmail

In the ChatGPT desktop app, choose Work locally. Install the Chrome plugin from Plugins, then follow its extension setup. Enable the computer permissions it requests for your selected workflow. Open this checkout as the working project. [Official browser setup](https://developers.openai.com/training/walkthroughs/using-your-computer-and-browser).

Install [Simplify Copilot](https://simplify.jobs/copilot), sign in, and complete its profile with the same facts and resume. In its [autofill settings](https://help.simplify.jobs/articles/8686025-manage-autofill-settings-in-the-simplify-extension), disable unwanted demographic autofill and AI guesses for unknown answers. Review the actual employer form after autofill.

Install/connect the Gmail plugin in the same agent environment. Select the applicant's mailbox. In a new session, ask the agent to read your connected profile and confirm it matches INFORMATION.md. This connector reads verification codes; background notifications require the separate optional setup below.

## Connect Notion

Create the tracker and connect it using [docs/notion.md](notion.md). Set its data source in `.env`:

```dotenv
NOTION_TRACKER_ID=collection://YOUR-DATA-SOURCE-UUID
THEIRSTACK_API_KEY=
```

Use the real UUID returned by Notion MCP, not the page URL or the placeholder above. Leave TheirStack blank for public discovery. Ask the agent to fetch the schema, create one clearly labeled test row, read it back, and remove that test row before your first batch.

## First live run

Use the shortlist prompt in [docs/prompts.md](prompts.md). Have the agent export your complete tracker to `tmp/tracker.json` before discovery:

```sh
python3 discover_jobs.py --tracker tmp/tracker.json --theirstack-limit 0 > tmp/jobs.json
```

Inspect `warnings`, confirm a live posting's requirements, then try one application with review before submission. Confirm the employer receipt and Notion row. Increase batch size only after that path works with your accounts.

For paid discovery, set `THEIRSTACK_API_KEY` in `.env` and choose an explicit row cap. [Discovery reference](discovery.md).

## Optional: background replies

Install and sign into the [Codex CLI](https://learn.chatgpt.com/docs/codex/cli). If already installed, run `codex --version`; otherwise use the install instructions on that page. Start `codex` from this checkout and finish sign-in. Add the Gmail plugin through `/plugins`, connect it, and configure the Notion MCP server below. [Official CLI and plugin workflow](https://learn.chatgpt.com/docs/codex/cli).

```sh
codex mcp add notion --url https://mcp.notion.com/mcp
codex mcp login notion
codex mcp list
python3 setup_workspace.py --check
```

The monitor expects server `notion` with `notion-fetch` and `notion-update-page`, and Gmail tools `gmail.get_profile`, `gmail.search_emails`, and `gmail.read_email` on `codex_apps`. Other connector shapes need an adapter. Continue with the complete [Gmail monitor guide](gmail-monitor.md); do not start a service before its preflight passes.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `python3` missing or older than 3.10 | Install a supported Python from [python.org](https://www.python.org/downloads/) |
| No roles or source warnings | Check network access, year/feed availability, filters, and the warnings array |
| Duplicate candidates | Re-export every Notion row, including all pages; keep both URLs |
| Notion fetch fails | Reconnect the correct workspace, share the tracker, and verify the data source ID |
| Gmail code missing | Check connected account, sender, request timestamp, read mail, and Spam |
| Autofill is wrong or stalled | Review the Simplify profile, restart autofill, and verify each field |
| Background preflight fails | Check [monitor troubleshooting](gmail-monitor.md#troubleshooting); browser-session connections may differ from CLI connections |
