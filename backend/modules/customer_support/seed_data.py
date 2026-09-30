"""
modules/customer_support/seed_data.py

Sample development & test dataset for Customer Support Knowledge Base.

ALL DATA CONTAINED HEREIN IS STRICTLY FOR DEMO / TESTING PURPOSES.
Do NOT represent fake policies as real company policies.
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from models.ticket import KnowledgeDocument, SupportCategory, SupportTeam
from modules.customer_support import service
from modules.customer_support.schemas import (
    KnowledgeDocumentCreate,
    SupportCategoryCreate,
    SupportTeamCreate,
)


DEMO_TEAMS: List[Dict[str, str]] = [
    {
        "name": "Billing & Finance Support Team",
        "code": "billing_finance",
        "description": "Handles payment issues, invoices, refunds, duplicate charges, and subscription billing.",
    },
    {
        "name": "Frontend & UI Support Team",
        "code": "frontend_ui",
        "description": "Resolves user interface defects, rendering bugs, browser compatibility, and cache issues.",
    },
    {
        "name": "Backend & API Support Team",
        "code": "backend_api",
        "description": "Investigates REST API errors (500, 404, 401), rate limits, timeouts, and backend failures.",
    },
    {
        "name": "Account & Security Support Team",
        "code": "auth_security",
        "description": "Manages customer authentication, 2FA/MFA, password resets, locked accounts, and session security.",
    },
    {
        "name": "Subscription & Invoicing Team",
        "code": "subscription_billing",
        "description": "Manages plan upgrades, downgrades, renewals, payment methods, invoice downloads, and license reconciliations.",
    },
    {
        "name": "General Customer Support Team",
        "code": "general_support",
        "description": "First-line support for enterprise policies, SLA response times, support hours, and ticket triage.",
    },
    {
        "name": "Account & Profile Operations Team",
        "code": "profile_management",
        "description": "Assists with company profile updates, contact details, user permissions, and account lifecycle.",
    },
    {
        "name": "Product & Solutions Specialist Team",
        "code": "product_specialists",
        "description": "Guides product feature onboarding, configuration, plan capabilities, and enterprise service tiers.",
    },
    {
        "name": "Orders & Service Operations Team",
        "code": "order_services",
        "description": "Tracks customer service requests, issue tracking, ticket escalation workflows, and order resolutions.",
    },
]

DEMO_CATEGORIES: List[Dict[str, str]] = [
    {
        "name": "Billing & Payments",
        "description": "Refund periods, payment cancellations, double charges, pending payments, payment methods, and receipts.",
        "team_code": "billing_finance",
    },
    {
        "name": "Account & Security",
        "description": "Password resets, two-factor authentication (2FA), locked accounts, session management, and unauthorized access.",
        "team_code": "auth_security",
    },
    {
        "name": "Technical Support",
        "description": "API 500/404/401 errors, timeout troubleshooting, request failures, slow performance, and technical escalation.",
        "team_code": "backend_api",
    },
    {
        "name": "Subscriptions & Invoicing",
        "description": "Plan upgrades, downgrades, cancellations, renewals, inactive licenses, and invoice receipt downloads.",
        "team_code": "subscription_billing",
    },
    {
        "name": "UI & Troubleshooting",
        "description": "Unresponsive buttons, browser cache clearing, hard refresh, browser compatibility, and unexpected logout.",
        "team_code": "frontend_ui",
    },
    {
        "name": "General Support & SLA",
        "description": "Support operating hours, critical & high priority SLAs, ticket tracking, and human agent handoff.",
        "team_code": "general_support",
    },
    {
        "name": "Account & Profile Management",
        "description": "Profile info updates, contact info, company details, notification preferences, and account deactivation.",
        "team_code": "profile_management",
    },
    {
        "name": "Products & Services",
        "description": "Available product catalog, plan feature inclusions, product setup, feature requests, and configuration.",
        "team_code": "product_specialists",
    },
    {
        "name": "Orders, Requests & Service Issues",
        "description": "Service request creation, request status tracking, issue reporting, request updates, and specialist escalation.",
        "team_code": "order_services",
    },
]

DEMO_DOCUMENTS: List[Dict[str, object]] = [
    {
        "title": "Refund and Cancellation Policy",
        "category_name": "Billing & Payments",
        "doc_type": "billing_policy",
        "content": (
            "Enterprise Refund, Payment & Cancellation Policy\n\n"
            "1. Refund Eligibility Period:\n"
            "Customers may request a full refund within 30 days of their initial purchase, plan recharge, or subscription renewal. "
            "To qualify for a refund, the account must be in good standing and the request submitted via the customer support portal.\n\n"
            "2. How to Request a Refund:\n"
            "Navigate to Account Settings > Billing & Payments, select the specific invoice, recharge receipt, or transaction, and click 'Request Refund'. "
            "Our Finance & Billing team evaluates claims and processes eligible refunds within 3-5 business days.\n\n"
            "3. Payment Cancellations, Failed Recharges & Pending Transactions:\n"
            "Payments that show as 'Pending' in your bank statement typically clear or void automatically within 24-48 hours. "
            "If a payment was charged twice or deducted for an unactivated recharge due to a network retry, the duplicate or uncredited charge is automatically detected and reversed within 3 business days.\n\n"
            "4. Updating Billing Information & Receipts:\n"
            "Update billing details, credit card numbers, and billing addresses directly under Account Settings > Payment Methods. "
            "Payment receipts, recharge summaries, and itemized invoices can be viewed and downloaded at any time from the Invoicing tab."
        ),
        "is_published": True,
    },
    {
        "title": "Customer Account Login & Password Reset Procedures",
        "category_name": "Account & Security",
        "doc_type": "auth_procedure",
        "content": (
            "Customer Account Security, 2FA, and Password Recovery Procedures\n\n"
            "1. Password Reset & Modification:\n"
            "To reset your forgotten password, click 'Forgot Password' on the login portal screen. Enter your registered email address. "
            "A secure password reset link will be sent to your inbox within 2 minutes (the link expires after 15 minutes). "
            "To change your existing password while logged in, go to Account Settings > Security > Change Password.\n\n"
            "2. Two-Factor Authentication (2FA / MFA):\n"
            "Enable 2FA under Account Settings > Security > Two-Factor Authentication using Google Authenticator, Duo, or Authy. "
            "Download and safely store your 10 emergency backup recovery codes during setup.\n\n"
            "3. Account Lockout & Recovery:\n"
            "For protection against brute-force attacks, accounts lock automatically for 30 minutes after 5 consecutive failed attempts. "
            "You can wait for the 30-minute lockout timer to expire or contact your security admin for immediate account unlocking.\n\n"
            "4. Managing Active Sessions & Device Security:\n"
            "Under Account Settings > Security > Active Sessions, view all currently logged-in devices with IP addresses. "
            "Click 'Sign Out from All Other Devices' to invalidate all remote sessions immediately if you suspect unauthorized access."
        ),
        "is_published": True,
    },
    {
        "title": "Backend API Error and 500 Troubleshooting Guide",
        "category_name": "Technical Support",
        "doc_type": "troubleshooting",
        "content": (
            "Backend API Error Codes, HTTP 500, 404, 401 & Rate Limit Guide\n\n"
            "1. HTTP 500 Internal Server Error:\n"
            "An HTTP 500 Internal Server Error occurs when the backend encounters an unhandled exception or database connection timeout. "
            "Inspect the response JSON for the unique 'Request ID' (e.g., 'req_abc123') and review server logs for the stack trace.\n\n"
            "2. HTTP 404 Not Found & 401 Unauthorized:\n"
            "HTTP 404 indicates an incorrect endpoint URL, missing resource ID, or deprecated API path. "
            "HTTP 401 occurs when the Authorization header is missing, malformed, or contains an expired Bearer token.\n\n"
            "3. Troubleshooting API Timeouts & Failed Requests:\n"
            "Check network latency, verify firewall rules, and inspect whether your request body matches the OpenAPI schema. "
            "Enterprise rate limits allow 1,000 requests per minute per API key (exceeding this yields HTTP 429).\n\n"
            "4. Technical Escalation:\n"
            "If API outages persist across multiple endpoints, check the system status at /health and escalate a Critical priority ticket to our Backend & API Engineering team."
        ),
        "is_published": True,
    },
    {
        "title": "Subscription Activation & Invoicing Management Policy",
        "category_name": "Subscriptions & Invoicing",
        "doc_type": "billing_policy",
        "content": (
            "Enterprise Subscription Lifecycle, Plan Recharge, Data Scheme Activation & Invoicing Policy\n\n"
            "1. Managing Your Subscription, Data Schemes & Plan Recharges:\n"
            "You can recharge or upgrade your data scheme or plan tier at any time under Account Settings > Subscriptions. "
            "Plan recharges (e.g., standard, 999 tier, or custom enterprise data packs) and upgrades apply instantly upon payment gateway confirmation. "
            "Downgrades and cancellations take effect at the end of the current billing cycle.\n\n"
            "2. Recharge Done / Payment Deducted but Data Scheme Inactive:\n"
            "When a payment or recharge (such as a 999 pack) is deducted from your bank or card, payment webhooks automatically sync and activate the data scheme within 15 minutes of bank settlement. "
            "If your data scheme, subscription, or service remains inactive after 30 minutes, submit a High-Priority billing ticket with your Transaction ID for manual reconciliation and instant plan activation by our Subscription & Invoicing Team.\n\n"
            "3. Invoices and Payment Methods:\n"
            "View and download all past itemized invoices in PDF format under Account Settings > Billing > Invoices. "
            "Update credit cards, bank debit accounts, or corporate billing contacts anytime.\n\n"
            "4. Subscription Reactivation:\n"
            "Canceled, expired, or inactive subscriptions and data schemes can be reactivated with 1-click from the Billing Dashboard, restoring all workspace data and user seats."
        ),
        "is_published": True,
    },
    {
        "title": "Frontend UI and Dashboard Troubleshooting Guide",
        "category_name": "UI & Troubleshooting",
        "doc_type": "troubleshooting",
        "content": (
            "Frontend UI, Browser Cache, and Dashboard Troubleshooting Guide\n\n"
            "1. Unresponsive Buttons & Interface Freezes:\n"
            "Dashboard buttons or UI elements may become unresponsive if stale JavaScript assets are cached after a platform update. "
            "Perform a hard refresh: Press Ctrl + F5 (Windows/Linux) or Cmd + Shift + R (macOS).\n\n"
            "2. Clearing Browser Cache and Cookies:\n"
            "In Chrome/Edge: Press Ctrl + Shift + Delete, select 'Cached images and files', and clear data. "
            "In Firefox: Go to Settings > Privacy & Security > Cookies and Site Data > Clear Data. "
            "In Safari: Choose Safari > Settings > Advanced > Show Develop Menu > Empty Caches.\n\n"
            "3. Supported Browsers:\n"
            "Officially supported browsers: Google Chrome 110+, Mozilla Firefox 110+, Microsoft Edge 110+, and Apple Safari 16+. "
            "Disable conflicting ad-blockers or script-blocking extensions if web sockets are interrupted.\n\n"
            "4. Unexpected Logouts & Rendering Glitches:\n"
            "Unexpected session termination usually indicates an expired session token or local storage conflict. Clear local storage and log in again."
        ),
        "is_published": True,
    },
    {
        "title": "General Customer Support SLA & Operating Hours",
        "category_name": "General Support & SLA",
        "doc_type": "general_policy",
        "content": (
            "General Customer Support Service Level Agreement (SLA) & Operating Hours\n\n"
            "1. Support Operating Hours:\n"
            "Standard support hours: Monday to Friday, 9:00 AM - 6:00 PM EST. Critical system incidents receive 24/7 coverage.\n\n"
            "2. Priority SLA Targets:\n"
            "- Critical (System Outage / Data Integrity Risk): Initial response within 1 hour, 24/7 dedicated engineering triage.\n"
            "- High (Major Feature Impairment / Payment Blocker): Initial response within 4 hours during business hours.\n"
            "- Medium (Standard Inquiry / Minor UI Bug): Initial response within 24 hours (1 business day).\n"
            "- Low (General Inquiries / Feedback): Initial response within 48 hours (2 business days).\n\n"
            "3. Support Channels & Escalation:\n"
            "Submit tickets directly through the Customer Support portal, use AI Chat with verified knowledge retrieval, or click 'Talk to Human Agent' for immediate live specialist handoff."
        ),
        "is_published": True,
    },
    {
        "title": "Account Profile, Contact Details & Organization Settings",
        "category_name": "Account & Profile Management",
        "doc_type": "account_management",
        "content": (
            "Account Profile, Contact Details, Permissions and Organization Management\n\n"
            "1. Updating Personal Profile & Contact Information:\n"
            "To update your name, email address, phone number, or job title, navigate to Account Settings > Profile. "
            "Email changes require confirming a verification link sent to both your existing and new email addresses.\n\n"
            "2. Company Information & Organization Settings:\n"
            "Organization administrators can modify company name, business address, tax ID, and billing contact details under Account Settings > Organization.\n\n"
            "3. Notification Preferences:\n"
            "Customize email, SMS, and in-app alert preferences under Account Settings > Notifications for ticket updates, billing notices, and system announcements.\n\n"
            "4. User Permissions & Account Lifecycle:\n"
            "Manage user roles (Admin, Member, Viewer) under Team Management. "
            "To deactivate or delete an account, navigate to Account Settings > Privacy & Deactivation. Deactivated accounts can be reactivated within 90 days by contacting support."
        ),
        "is_published": True,
    },
    {
        "title": "Enterprise Products, Feature Tiers & Service Configurations",
        "category_name": "Products & Services",
        "doc_type": "product_guide",
        "content": (
            "Enterprise Products, Feature Capabilities & Service Configuration Guide\n\n"
            "1. Product Overview & Service Catalog:\n"
            "Unified AI Enterprise 2.0 provides modules for Recruitment Automation, Customer Support AI Assistant, "
            "Employee Management, Incident Management, and Executive Analytics.\n\n"
            "2. Plan Features and Capabilities:\n"
            "- Starter Tier: Core support triage, ticketing, and basic knowledge search.\n"
            "- Professional Tier: AI Grounded Assistant, BM25 retrieval, custom knowledge chunking, and SLA tracking.\n"
            "- Enterprise Tier: Full multi-turn Gemini AI reasoning, custom integrations, unlimited seats, 24/7 SLA, and dedicated engineering handoff.\n\n"
            "3. Product Setup & Configuration:\n"
            "Configure new modules via the Admin Console > Integrations. Enable webhooks, API tokens, and custom role-based access rules.\n\n"
            "4. Requesting Features & Reporting Product Issues:\n"
            "Submit feature requests or report broken features through the Support Portal under 'Products & Services' or directly to your dedicated account manager."
        ),
        "is_published": True,
    },
    {
        "title": "Service Requests, Support Tickets & Issue Tracking Lifecycle",
        "category_name": "Orders, Requests & Service Issues",
        "doc_type": "service_operations",
        "content": (
            "Enterprise Service Requests, Issue Reporting & Ticket Lifecycle Guide\n\n"
            "1. Creating a Service Request or Reporting an Issue:\n"
            "Create a request by clicking 'Create Ticket' in the Customer Support portal, asking the AI Assistant to generate a ticket, or emailing support@enterprise.ai. "
            "Include your customer email, detailed description, priority level, and any error logs or screenshots.\n\n"
            "2. Tracking Request Status & Lifecycle:\n"
            "Track all active requests in the 'My Tickets' dashboard. Ticket statuses progress through: Open → In Progress → Escalated → Resolved → Closed.\n\n"
            "3. Updating & Canceling Requests:\n"
            "Add messages, attach diagnostic files, or cancel open requests directly from the Ticket Detail view.\n\n"
            "4. Escalating Unresolved Service Requests:\n"
            "If an urgent issue is approaching SLA threshold or requires tier-2 engineering review, click 'Escalate Ticket' to assign it to specialized support teams immediately."
        ),
        "is_published": True,
    },
]


def seed_demo_knowledge_data(db: Session, author_id: Optional[int] = None) -> Dict[str, int]:
    """
    Safely seeds demo support teams, categories, and knowledge documents across all 9 topics.
    Idempotent: skips already existing records.
    """
    stats = {"teams": 0, "categories": 0, "documents": 0, "chunks": 0}

    # 1. Seed Teams
    team_map: Dict[str, SupportTeam] = {}
    for t_data in DEMO_TEAMS:
        existing = db.query(SupportTeam).filter(SupportTeam.code == t_data["code"]).first()
        if not existing:
            team = SupportTeam(
                name=t_data["name"],
                code=t_data["code"],
                description=t_data["description"],
                is_active=True,
            )
            db.add(team)
            db.flush()
            team_map[t_data["code"]] = team
            stats["teams"] += 1
        else:
            team_map[t_data["code"]] = existing

    # 2. Seed Categories
    category_map: Dict[str, SupportCategory] = {}
    for c_data in DEMO_CATEGORIES:
        existing = db.query(SupportCategory).filter(SupportCategory.name == c_data["name"]).first()
        if not existing:
            team = team_map.get(c_data["team_code"])
            category = SupportCategory(
                name=c_data["name"],
                description=c_data["description"],
                default_team_id=team.id if team else None,
            )
            db.add(category)
            db.flush()
            category_map[c_data["name"]] = category
            stats["categories"] += 1
        else:
            category_map[c_data["name"]] = existing

    db.commit()

    # 3. Seed Documents & Chunks
    for d_data in DEMO_DOCUMENTS:
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.title == d_data["title"]).first()
        if not existing:
            cat = category_map.get(d_data["category_name"])
            create_payload = KnowledgeDocumentCreate(
                title=d_data["title"],
                category_id=cat.id if cat else None,
                doc_type=d_data["doc_type"],
                content=d_data["content"],
                is_published=d_data["is_published"],
            )
            doc = service.create_knowledge_document(
                db=db,
                payload=create_payload,
                created_by_id=author_id,
            )
            stats["documents"] += 1
            stats["chunks"] += len(doc.chunks)

    return stats

