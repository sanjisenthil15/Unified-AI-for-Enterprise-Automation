"""
backend/test_enterprise_customer_service_upgrade.py

Comprehensive Verification Suite for Enterprise Customer Service Platform Upgrade:
1. Conversational Routing Gate & 0 KB Retrieval for Greetings/Thanks/Capability queries
2. Enterprise Factual Queries & BM25 Knowledge Retrieval with Strict Domain Isolation
3. Multi-Turn Co-Reference Resolution
4. Service Status & Incident Diagnostics
5. AI-Assisted Guided Support Request Pre-Analysis & Duplicate Detection
6. Notification & Support Communication Center
"""

import sys
import os

# Ensure UTF-8 output encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.customer_support.intent import detect_intent, detect_query_intent
from modules.customer_support.service import (
    search_knowledge_base,
    get_service_statuses,
    get_active_incidents,
    analyze_support_request,
    list_notifications,
    mark_notification_read,
    get_notification_preferences,
    update_notification_preferences,
    send_chat_message,
    create_chat_session,
)
from modules.customer_support.schemas import (
    ChatMessageRequest,
    CreateChatSessionRequest,
    SupportRequestAnalysisRequest,
    NotificationPreferences,
)

def run_tests():
    passed = 0
    total = 0

    def check(name, condition, details=""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name} {f'- {details}' if details else ''}")
        else:
            print(f"  [FAIL] {name} {f'- {details}' if details else ''}")
            assert False, f"Test failure: {name} {details}"

    print("\n========================================================")
    print(" 1. TESTING CONVERSATIONAL ROUTING GATE (0 KB RETRIEVAL)")
    print("========================================================")

    conversational_samples = [
        ("Hi", "GREETING"),
        ("Hello", "GREETING"),
        ("Hey there, how are you doing today?", "GREETING"),
        ("Good morning", "GREETING"),
        ("Thanks for the help!", "THANKS"),
        ("Thank you very much", "THANKS"),
        ("Goodbye", "GOODBYE"),
        ("Bye for now", "GOODBYE"),
        ("What can you help me with?", "CAPABILITY"),
        ("What are your features?", "CAPABILITY"),
    ]

    for msg, expected_intent_type in conversational_samples:
        intent = detect_intent(msg)
        check(
            f"Detect intent: '{msg}'",
            intent.is_conversational is True,
            f"Detected Intent: {intent.intent_type}, is_conversational={intent.is_conversational}"
        )

        search_res = search_knowledge_base(db=None, query=msg, intent=intent)
        check(
            f"Strict 0 KB retrieval for '{msg}'",
            search_res.total_results == 0 and len(search_res.results) == 0,
            f"Total retrieved: {search_res.total_results}"
        )

    print("\n========================================================")
    print(" 2. TESTING ENTERPRISE FACTUAL QUERIES (BM25 RETRIEVAL)")
    print("========================================================")

    factual_samples = [
        ("What is your refund policy and timeframe?", "REFUND", "Subscriptions & Billing"),
        ("How do I reset my account password?", "PASSWORD", "Account & Security"),
        ("I am getting an internal server 500 error when calling the API", "TECHNICAL_API", "API & Integrations"),
        ("I recharged ₹999 for my subscription but the payment failed", "RECHARGE", "Subscriptions & Billing"),
    ]

    for query, expected_intent, expected_cat in factual_samples:
        intent = detect_intent(query)
        check(
            f"Factual query intent: '{query[:30]}...'",
            intent.is_conversational is False,
            f"Detected Intent: {intent.intent_type}, Domain: {intent.detected_category or 'General'}"
        )

        search_res = search_knowledge_base(db=None, query=query, intent=intent, limit=3)
        check(
            f"BM25 retrieval for factual query: '{query[:30]}...'",
            search_res.total_results > 0,
            f"Found {search_res.total_results} chunks. Top chunk title: {search_res.results[0].document_title if search_res.results else 'None'}"
        )

        # Ensure strict domain boundary (e.g. ₹999 recharge should not map to Frontend/Cache)
        if "recharge" in query.lower():
            top_title = search_res.results[0].document_title if search_res.results else ""
            check(
                "₹999 recharge matches Billing/Subscription KB doc",
                "Subscription" in top_title or "Billing" in top_title or "Refund" in top_title,
                f"Top doc: {top_title}"
            )

    print("\n========================================================")
    print(" 3. TESTING MULTI-TURN CO-REFERENCE RESOLUTION")
    print("========================================================")

    history = [
        {"role": "user", "content": "I tried to recharge ₹999 for my quarterly subscription"},
        {"role": "assistant", "content": "I understand you attempted a ₹999 recharge. Could you provide the transaction ID or details of what happened?"},
    ]

    follow_up_msg = "The money was deducted from my account but the plan is still inactive"
    intent_turn_2 = detect_intent(follow_up_msg, history=history)

    check(
        "Follow-up co-reference retains recharge/subscription context",
        intent_turn_2.intent_type in ("RECHARGE", "BILLING_PAYMENT", "SUBSCRIPTION") or intent_turn_2.detected_category in ("Subscriptions & Invoicing", "Subscriptions & Billing", "Billing & Payments"),
        f"Resolved Intent: {intent_turn_2.intent_type}, Category: {intent_turn_2.detected_category}"
    )

    search_turn_2 = search_knowledge_base(db=None, query=follow_up_msg, intent=intent_turn_2)
    check(
        "Multi-turn follow-up retrieves relevant billing KB",
        search_turn_2.total_results > 0,
        f"Retrieved: {search_turn_2.total_results} documents"
    )

    print("\n========================================================")
    print(" 4. TESTING SERVICE STATUS & INCIDENT DIAGNOSTICS")
    print("========================================================")

    status_overview = get_service_statuses(db=None)
    check(
        "Service status overview has operational telemetry",
        len(status_overview.services) >= 5 and "Operational" in status_overview.overall_status or "Degraded" in status_overview.overall_status,
        f"Overall: {status_overview.overall_status}, Services: {len(status_overview.services)}"
    )

    incidents = get_active_incidents(db=None)
    check(
        "Incident center returns active/past incidents",
        len(incidents) >= 1 or len(status_overview.past_incidents) >= 1,
        f"Active incidents: {len(incidents)}, Past: {len(status_overview.past_incidents)}"
    )

    status_query = "Is the system or payment gateway down right now?"
    intent_status = detect_intent(status_query)
    check(
        "Service status query intent",
        intent_status.intent_type == "SERVICE_STATUS",
        f"Intent: {intent_status.intent_type}, Type: {intent_status.suggested_response_type}"
    )

    print("\n========================================================")
    print(" 5. TESTING AI-ASSISTED GUIDED SUPPORT REQUEST CENTER")
    print("========================================================")

    analysis_req = SupportRequestAnalysisRequest(
        subject="Recharge ₹999 deducted but subscription is inactive",
        description="I made a ₹999 payment via UPI. The money was debited from my bank but my Pro account is still inactive after 3 hours.",
        area="Billing & Invoicing"
    )
    analysis_res = analyze_support_request(db=None, payload=analysis_req)

    check(
        "AI pre-submission analysis classifies domain and priority",
        analysis_res.suggested_priority in ("HIGH", "CRITICAL", "high", "critical", "medium") and analysis_res.recommended_team is not None,
        f"Category: {analysis_res.detected_category}, Priority: {analysis_res.suggested_priority}, Team: {analysis_res.recommended_team}"
    )

    check(
        "AI suggests relevant self-service KB solution",
        analysis_res.relevant_knowledge_title is not None,
        f"Suggested Doc: {analysis_res.relevant_knowledge_title}"
    )

    print("\n========================================================")
    print(" 6. TESTING NOTIFICATIONS & COMMUNICATION CENTER")
    print("========================================================")

    notifs_res = list_notifications(db=None)
    check(
        "Notifications feed returns enterprise notifications",
        len(notifs_res.notifications) >= 1 and notifs_res.unread_count >= 0,
        f"Total: {len(notifs_res.notifications)}, Unread: {notifs_res.unread_count}"
    )

    if notifs_res.notifications:
        first_id = notifs_res.notifications[0].id
        marked = mark_notification_read(db=None, notification_id=first_id)
        check(
            f"Mark notification #{first_id} as read",
            marked.get("status") == "success",
            f"Status: {marked.get('status')}"
        )

    prefs = get_notification_preferences(db=None)
    check(
        "Fetch notification preferences",
        prefs.ticket_updates is True,
        f"Email: {prefs.email_notifications}, SLA: {prefs.sla_alerts}"
    )

    updated_prefs = update_notification_preferences(db=None, payload=NotificationPreferences(
        ticket_updates=True,
        sla_alerts=True,
        incident_alerts=True,
        email_notifications=False,
        agent_replies=True,
    ))
    check(
        "Update notification preferences",
        updated_prefs.email_notifications is False,
        f"Updated email_notifications: {updated_prefs.email_notifications}"
    )

    print("\n========================================================")
    print(" 7. TESTING CHATBOT END-TO-END MESSAGE WORKFLOW")
    print("========================================================")

    sess = create_chat_session(db=None, payload=CreateChatSessionRequest(customer_name="Vishwa Test"))

    # Turn 1: Conversational Greeting
    resp_greeting = send_chat_message(db=None, payload=ChatMessageRequest(
        session_id=sess.id,
        message="Hello! Good afternoon!"
    ))
    check(
        "Conversational Greeting -> 0 citations & CONVERSATIONAL type",
        resp_greeting.response_type == "CONVERSATIONAL" and len(resp_greeting.citations) == 0,
        f"Type: {resp_greeting.response_type}, Citations: {len(resp_greeting.citations)}, Answer: {resp_greeting.answer[:50]}..."
    )

    # Turn 2: Factual Policy Query
    resp_policy = send_chat_message(db=None, payload=ChatMessageRequest(
        session_id=sess.id,
        message="What is your policy regarding refunds?"
    ))
    check(
        "Factual refund query -> Grounded sources retrieved",
        len(resp_policy.citations) > 0,
        f"Citations retrieved: {len(resp_policy.citations)}, Answer: {resp_policy.answer[:60]}..."
    )

    # Turn 3: Service status query
    resp_status = send_chat_message(db=None, payload=ChatMessageRequest(
        session_id=sess.id,
        message="Is the payment gateway operational right now?"
    ))
    check(
        "Service status chatbot query -> SERVICE_STATUS response type",
        resp_status.response_type == "SERVICE_STATUS",
        f"Type: {resp_status.response_type}, Answer: {resp_status.answer[:60]}..."
    )

    print("\n========================================================")
    print(f" ALL TESTS COMPLETED: {passed}/{total} PASSED")
    print("========================================================\n")
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)

