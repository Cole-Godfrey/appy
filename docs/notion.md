# Notion tracker

Create a database with these property names. The workflows use this schema; changing it requires updating the instructions too.

| Property | Type | Values / use |
| --- | --- | --- |
| Position | Title | Role title |
| Company | Text | Employer name |
| Status | Multi-select | Applied, OA, Interviewed, Offer, Accepted, Rejected |
| Next Action | Multi-select | Waiting, Prepare for OA, Prepare Interview, Decide |
| Application Date | Date | Confirmed submission date |
| URL | URL | Employer application URL |
| Reference URL | URL | Optional discovery/source URL |
| Resume Used | Files | Optional uploaded resume |

Keep receipts, recruiting evidence, compensation, requisition IDs, and resume filenames in the row's page body. A local resume path does not upload a file to Notion.

## Connection

Connect the [official Notion MCP](https://developers.notion.com/guides/mcp/get-started-with-mcp) to your agent and authorize access to this tracker. For Codex CLI:

```sh
codex mcp add notion --url https://mcp.notion.com/mcp
codex mcp login notion
```

Ask the agent to fetch the database, inspect its data sources, and return the selected data source's `collection://UUID` identifier. Store that value as `NOTION_TRACKER_ID` in `.env`. The database page ID and data source ID may differ.

Before writes, fetch the current schema and any enhanced Markdown specification exposed by the connector. Use the data source ID when creating rows. Verify a new test row by fetching it; remove it when the connection is confirmed. [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Export for deduplication

Ask the agent to export all rows through MCP, mapping the properties above to this shape:

```json
[
  {
    "company": "Example Company",
    "title": "Software Engineer Intern",
    "application_url": "https://example.com/jobs/123",
    "reference_url": null
  }
]
```

Save only the completed array to `tmp/tracker.json`. If the tracker has no rows, use `[]` after verifying that it is empty. The CLI validates the shape; it cannot prove the export is complete.

Follow the connector's pagination. If using SQL exports, use a stable order such as `ORDER BY createdTime, url LIMIT 100 OFFSET N`; continue through full pages even if a connector incorrectly reports no more rows. Reject failed or incomplete exports. Refresh between batches.

After a verified submission, set Status to Applied, Next Action to Waiting, and the confirmed date and URLs. Read the row back. Preserve later recruiting stages when handling routine receipts or older mail.
