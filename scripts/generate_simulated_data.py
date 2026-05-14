from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "examples"


PRIMARY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "github_search_issues",
        "description": "Search GitHub issues by repository, text, label, state, assignee, or milestone.",
        "domain": "engineering",
        "prompts": [
            "Find open GitHub issues tagged billing and summarize the blockers.",
            "Search GitHub for flaky test issues assigned to the platform team.",
            "Look up closed GitHub issues about OAuth regressions from last week.",
            "Find GitHub issues mentioning database migration failures.",
            "Search the repository issues for customer-reported login errors.",
        ],
    },
    {
        "name": "github_create_pr",
        "description": "Open a GitHub pull request with title, body, source branch, and target branch.",
        "domain": "engineering",
        "prompts": [
            "Create a pull request from release-notes into main.",
            "Open a PR for the hotfix branch and mention the incident ticket.",
            "Create a GitHub pull request for the docs cleanup branch.",
            "Open a pull request from feature/export-csv to develop.",
            "Create a draft PR for the refactor branch with a short summary.",
        ],
    },
    {
        "name": "linear_create_issue",
        "description": "Create a Linear issue with title, description, team, priority, and labels.",
        "domain": "project-management",
        "prompts": [
            "Create a Linear issue for improving checkout error handling.",
            "File a high priority Linear ticket for the broken onboarding email.",
            "Create a Linear bug for mobile users seeing blank invoices.",
            "Add a Linear issue for documenting the new API rate limits.",
            "Create a Linear task for the support dashboard pagination bug.",
        ],
    },
    {
        "name": "jira_transition_ticket",
        "description": "Move a Jira ticket to another workflow state with an optional comment.",
        "domain": "project-management",
        "prompts": [
            "Move Jira ticket OPS-142 to In Review with a deployment note.",
            "Transition DEV-883 to Done and add the QA approval comment.",
            "Put Jira issue SEC-19 back into Todo because the patch failed.",
            "Move the billing Jira ticket to Blocked and explain the dependency.",
            "Transition the release Jira task to Ready for QA.",
        ],
    },
    {
        "name": "slack_send_message",
        "description": "Send a Slack message to a channel or user, optionally with markdown formatting.",
        "domain": "communication",
        "prompts": [
            "Send the revenue summary to the marketing Slack channel.",
            "Message the on-call channel that the database migration finished.",
            "Post a Slack update to support about the delayed invoice fix.",
            "Send a formatted Slack note to sales with the demo account links.",
            "Notify the engineering Slack channel that the release is ready.",
        ],
    },
    {
        "name": "gmail_send_email",
        "description": "Send an email with recipients, subject, body, cc, bcc, and attachments.",
        "domain": "communication",
        "prompts": [
            "Email the customer a short update about their escalation.",
            "Send finance an email with the invoice reconciliation notes.",
            "Email the hiring panel the interview schedule for tomorrow.",
            "Send a follow-up email to the vendor about the signed contract.",
            "Email the beta users with the new feature announcement.",
        ],
    },
    {
        "name": "calendar_create_event",
        "description": "Create a calendar event with attendees, title, date, time, and location.",
        "domain": "calendar",
        "prompts": [
            "Schedule a meeting with the support team tomorrow afternoon.",
            "Create a calendar event for the release retrospective on Friday.",
            "Set up a customer kickoff call with Alex and Priya next Tuesday.",
            "Schedule the quarterly security review with the compliance team.",
            "Create a calendar hold for the deployment window tonight.",
        ],
    },
    {
        "name": "calendar_find_availability",
        "description": "Find open calendar slots across attendees and date ranges.",
        "domain": "calendar",
        "prompts": [
            "Find a free 30-minute slot for the product sync next week.",
            "Check when Sam and Morgan are both available tomorrow.",
            "Find availability for a customer call before Thursday.",
            "Look for an open hour on the leadership calendar this afternoon.",
            "Find a meeting slot for the data review with three attendees.",
        ],
    },
    {
        "name": "postgres_query",
        "description": "Run a read-only SQL query against Postgres for revenue, users, jobs, or events.",
        "domain": "data",
        "prompts": [
            "Run a Postgres query for yesterday's failed jobs.",
            "Check the database for revenue by plan over the last seven days.",
            "Query Postgres for users who churned after trial expiration.",
            "Fetch the top five accounts by invoice volume from the database.",
            "Run SQL to count API errors grouped by endpoint today.",
        ],
    },
    {
        "name": "bigquery_run_query",
        "description": "Run an analytical BigQuery SQL query for warehouse reports and dashboards.",
        "domain": "data",
        "prompts": [
            "Run a BigQuery report for weekly active teams by region.",
            "Query the warehouse for conversion rates by acquisition channel.",
            "Use BigQuery to calculate retention for the March cohort.",
            "Run the analytics query for support ticket volume by product area.",
            "Pull BigQuery results for usage growth across enterprise accounts.",
        ],
    },
    {
        "name": "stripe_create_checkout",
        "description": "Create a Stripe Checkout payment link for a product, price, customer, or plan.",
        "domain": "payments",
        "prompts": [
            "Create a Stripe checkout link for the annual plan.",
            "Generate a payment link for the customer upgrade invoice.",
            "Create a Stripe checkout session for three enterprise seats.",
            "Make a checkout link for the discounted beta subscription.",
            "Create a Stripe payment page for the onboarding package.",
        ],
    },
    {
        "name": "stripe_refund_payment",
        "description": "Refund a Stripe payment by charge, payment intent, amount, and reason.",
        "domain": "payments",
        "prompts": [
            "Refund the duplicate Stripe payment from yesterday.",
            "Issue a partial refund for the failed setup charge.",
            "Refund the customer's last card payment and mark the reason requested_by_customer.",
            "Create a Stripe refund for the cancelled annual subscription.",
            "Refund the overcharged invoice payment for Acme Corp.",
        ],
    },
    {
        "name": "hubspot_create_contact",
        "description": "Create or update a HubSpot contact with email, company, owner, and lifecycle stage.",
        "domain": "sales",
        "prompts": [
            "Create a HubSpot contact for the new trial lead.",
            "Add the webinar attendee to HubSpot with their company name.",
            "Update the HubSpot contact owner for the enterprise prospect.",
            "Create a contact record for the inbound demo request.",
            "Add the partner lead to HubSpot and set lifecycle stage to MQL.",
        ],
    },
    {
        "name": "salesforce_update_opportunity",
        "description": "Update a Salesforce opportunity amount, stage, close date, owner, or notes.",
        "domain": "sales",
        "prompts": [
            "Update the Salesforce opportunity stage to Contract Sent.",
            "Change the close date on the Acme opportunity in Salesforce.",
            "Add a note to the Salesforce deal after the procurement call.",
            "Update the opportunity amount for the expansion deal.",
            "Move the Salesforce opportunity to Closed Won.",
        ],
    },
    {
        "name": "web_search",
        "description": "Search the public web for current news, pricing, documentation, or references.",
        "domain": "research",
        "prompts": [
            "Search the web for current competitor pricing references.",
            "Find recent public documentation about OAuth device flow limits.",
            "Search online for examples of SOC 2 vendor questionnaires.",
            "Look up current pricing for hosted vector databases.",
            "Search the web for recent API reliability incidents from major providers.",
        ],
    },
    {
        "name": "pdf_extract_text",
        "description": "Extract text and tables from a PDF document for summarization or analysis.",
        "domain": "documents",
        "prompts": [
            "Extract text from the signed contract PDF and summarize renewal terms.",
            "Read the uploaded PDF invoice and pull out the due date.",
            "Extract the security questionnaire answers from the PDF.",
            "Pull the table of fees from the vendor agreement PDF.",
            "Extract text from the board deck PDF for a short summary.",
        ],
    },
    {
        "name": "notion_create_page",
        "description": "Create a Notion page in a workspace, database, or team wiki.",
        "domain": "documents",
        "prompts": [
            "Create a Notion page for the incident postmortem.",
            "Add a Notion spec page for the import workflow.",
            "Create a Notion note with the customer discovery summary.",
            "Write a Notion page for the release checklist.",
            "Create a Notion page in the team wiki for API pagination.",
        ],
    },
    {
        "name": "s3_upload_file",
        "description": "Upload a file to Amazon S3 with bucket, key, content type, and metadata.",
        "domain": "storage",
        "prompts": [
            "Upload the generated CSV report to the analytics S3 bucket.",
            "Put the exported invoices file into S3 under monthly-reports.",
            "Upload the backup archive to the operations bucket.",
            "Store the customer attachment in S3 with private access.",
            "Upload the compliance evidence ZIP to the audit bucket.",
        ],
    },
    {
        "name": "zendesk_create_ticket",
        "description": "Create a Zendesk support ticket with requester, subject, priority, and tags.",
        "domain": "support",
        "prompts": [
            "Create a Zendesk ticket for the customer's login problem.",
            "File a high priority Zendesk ticket for the payment failure.",
            "Create a support ticket about the missing invoice email.",
            "Open a Zendesk ticket for a workspace export request.",
            "Create a Zendesk case for the enterprise SSO setup question.",
        ],
    },
    {
        "name": "datadog_query_logs",
        "description": "Query Datadog logs and metrics by service, time range, status, and tags.",
        "domain": "observability",
        "prompts": [
            "Check Datadog logs for API 500 errors in the last hour.",
            "Query Datadog for latency spikes on the checkout service.",
            "Look up Datadog logs for failed login attempts this morning.",
            "Check service metrics in Datadog during the deployment window.",
            "Query Datadog for error rates grouped by region.",
        ],
    },
]


DISTRACTOR_DOMAINS = [
    "legacy",
    "admin",
    "finance",
    "warehouse",
    "experiments",
    "notifications",
    "content",
    "security",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate realistic synthetic Janitor eval data.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--cases-per-tool", type=int, default=5)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    tools, cases, logs = generate_dataset(cases_per_tool=args.cases_per_tool)
    write_dataset(output_dir, tools, cases, logs)
    print(f"wrote {len(tools)} tools, {len(cases)} eval cases, and {len(logs)} log rows to {output_dir}")
    return 0


def generate_dataset(cases_per_tool: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if cases_per_tool < 1:
        raise ValueError("cases_per_tool must be at least 1")

    tools = [_tool_payload(tool) for tool in PRIMARY_TOOLS]
    tools.extend(_distractor_tools())

    cases: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    case_number = 1

    for tool in PRIMARY_TOOLS:
        prompts = list(tool["prompts"])[:cases_per_tool]
        if len(prompts) < cases_per_tool:
            raise ValueError(f"{tool['name']} has fewer than {cases_per_tool} prompts")

        for prompt in prompts:
            case_id = f"sim-{case_number:03d}"
            expected_tool = str(tool["name"])
            cases.append(
                {
                    "id": case_id,
                    "prompt": prompt,
                    "expected_tools": [expected_tool],
                }
            )
            logs.append(
                {
                    "id": case_id,
                    "prompt": prompt,
                    "tool_calls": [{"function": {"name": expected_tool}}],
                    "success": True,
                    "source": "simulated-production",
                }
            )
            case_number += 1

    return tools, cases, logs


def write_dataset(
    output_dir: Path,
    tools: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "simulated_production_tools.json", tools)
    _write_json(
        output_dir / "simulated_production_evals.json",
        {
            "metadata": {
                "source": "scripts/generate_simulated_data.py",
                "cases": len(cases),
                "tools": len(tools),
                "note": "Synthetic production-like data for rehearsing eval and middleware flows.",
            },
            "cases": cases,
        },
    )
    (output_dir / "simulated_agent_logs.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in logs) + "\n",
        encoding="utf-8",
    )


def _tool_payload(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool["name"])
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(tool["description"]),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": f"Input text or structured request for {name}.",
                    }
                },
            },
        },
        "x-domain": str(tool["domain"]),
    }


def _distractor_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for domain in DISTRACTOR_DOMAINS:
        for index in range(10):
            name = f"{domain}_internal_{index:02d}"
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": (
                            f"Internal {domain} maintenance helper for archived workflows, "
                            "migration tasks, and low-level operator actions."
                        ),
                    },
                    "x-domain": domain,
                    "x-simulated-distractor": True,
                }
            )
    return tools


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
