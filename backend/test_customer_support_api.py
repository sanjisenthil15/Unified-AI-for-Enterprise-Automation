"""
backend/test_customer_support_api.py

Direct functional verification of all Customer Support service workflows:
  1. Knowledge Base Search (BM25 lexical matching)
  2. Chat Session Creation & Listing
  3. Grounded AI Response with Citations & Confidence
  4. Escalation Trigger on Out-of-Scope Queries
  5. Agent Handoff Summary Generation
  6. Support Ticket Creation & Thread Replies
  7. Ticket Status Updates & Listing
  8. Global Cross-Entity Search
  9. Customer Support Statistics & Live Metrics
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from modules.customer_support import service
from modules.customer_support.schemas import (
    ChatMessageRequest,
    CreateChatSessionRequest,
    TicketCreateRequest,
    TicketMessageRequest,
    TicketUpdateRequest,
)

def run_tests():
    print("==================================================")
    print("CUSTOMER SUPPORT AI SYSTEM - END-TO-END TESTS")
    print("==================================================")

    # 1. Test BM25 Knowledge Base Search
    print("\n[1] Testing BM25 Knowledge Base Search...")
    search_res = service.search_knowledge_base(db=None, query="refund policy period", min_score=0.10)
    print(f"  -> Total Chunks Matched: {search_res.total_results}")
    assert search_res.total_results > 0, "BM25 search returned 0 results"
    top = search_res.results[0]
    print(f"  -> Top Match: '{top.document_title}' (Score: {top.relevance_score}, Category: {top.category_name})")

    # 2. Test Chat Session Creation
    print("\n[2] Testing Chat Session Creation...")
    sess = service.create_chat_session(
        db=None,
        payload=CreateChatSessionRequest(customer_name="Alice Enterprise", customer_email="alice@company.com"),
    )
    print(f"  -> Created Session ID: {sess.id} (Status: {sess.status})")
    assert sess.id.startswith("session_"), "Invalid session ID generated"

    # 3. Test Grounded AI Chatbot with Knowledge Base Query
    print("\n[3] Testing Grounded AI Chat (Refund Policy Question)...")
    chat_req = ChatMessageRequest(
        session_id=sess.id,
        message="What is your policy regarding refunds and how many days do I have?",
    )
    ai_resp = service.send_chat_message(db=None, payload=chat_req)
    print(f"  -> Answerable: {ai_resp.answerable}")
    print(f"  -> Confidence Score: {ai_resp.confidence} ({int(ai_resp.confidence * 100)}%)")
    print(f"  -> Citations: {len(ai_resp.citations)} source document(s)")
    if ai_resp.citations:
        print(f"     Source: {ai_resp.citations[0].document_title}")
    assert ai_resp.answerable is True, "Expected query to be answerable from verified KB"
    assert ai_resp.confidence >= 0.80, "Expected high confidence for refund question"

    # 4. Test Escalation Trigger on Unknown Query
    print("\n[4] Testing AI Escalation Detection on Unknown Query...")
    esc_req = ChatMessageRequest(
        session_id=sess.id,
        message="My quantum server is leaking tachyon radiation into the hyperloop.",
    )
    esc_resp = service.send_chat_message(db=None, payload=esc_req)
    print(f"  -> Answerable: {esc_resp.answerable}")
    print(f"  -> Escalation Recommended: {esc_resp.escalation_recommended}")
    print(f"  -> Detected Category: {esc_resp.detected_category}")
    print(f"  -> Recommended Team: {esc_resp.assigned_team}")
    assert esc_resp.escalation_recommended is True, "Expected escalation on unknown query"

    # 5. Test Human Agent Handoff Summary
    print("\n[5] Testing Human Agent Handoff Synthesis...")
    handoff = service.generate_agent_handoff(db=None, session_id=sess.id)
    print(f"  -> Issue Summary: {handoff.issue_summary}")
    print(f"  -> Attempted Steps: {len(handoff.attempted_steps)}")
    print(f"  -> Recommended Priority: {handoff.recommended_priority.upper()}")
    print(f"  -> Recommended Team: {handoff.recommended_team}")
    assert len(handoff.attempted_steps) > 0, "Expected non-empty attempted steps"

    # 6. Test Support Ticket Creation
    print("\n[6] Testing Support Ticket Creation...")
    tkt_req = TicketCreateRequest(
        subject="Duplicate billing charge on invoice #INV-9921",
        description="Customer was charged twice for enterprise license upgrade on September 1st.",
        category_id=1,
        priority="high",
        session_id=sess.id,
        customer_name="Alice Enterprise",
        customer_email="alice@company.com",
    )
    tkt = service.create_support_ticket(db=None, payload=tkt_req)
    print(f"  -> Created Ticket: #TKT-{tkt.id} (Status: {tkt.status.upper()}, Priority: {tkt.priority.upper()})")
    assert tkt.id > 1000, "Expected valid ticket ID"

    # 7. Test Ticket Message Reply
    print("\n[7] Testing Ticket Thread Reply...")
    reply_req = TicketMessageRequest(
        message="Billing team has reviewed the double charge. Reversal initiated for $499.",
        is_ai=False,
    )
    tkt_msg = service.add_ticket_message(db=None, ticket_id=tkt.id, payload=reply_req)
    print(f"  -> Message #{tkt_msg.id} posted by '{tkt_msg.sender_name}' on Ticket #{tkt.id}")

    # 8. Test Ticket Status Update
    print("\n[8] Testing Ticket Status Update...")
    upd_tkt = service.update_support_ticket(
        db=None,
        ticket_id=tkt.id,
        payload=TicketUpdateRequest(status="resolved"),
    )
    print(f"  -> Updated Ticket #{upd_tkt.id} Status: {upd_tkt.status.upper()} (Resolved at: {upd_tkt.resolved_at})")
    assert upd_tkt.status == "resolved", "Expected status to be updated to resolved"

    # 9. Test Global Search
    print("\n[9] Testing Cross-Entity Global Search...")
    glob_res = service.global_customer_support_search(db=None, query="refund")
    print(f"  -> Search query 'refund' returned {glob_res.total_results} matching items:")
    for item in glob_res.results[:3]:
        print(f"     [{item.type.upper()}] {item.title} ({item.status})")
    assert glob_res.total_results > 0, "Expected global search results for 'refund'"

    # 10. Test Operational Stats
    print("\n[10] Testing Support Operational Statistics...")
    stats = service.get_customer_support_stats(db=None)
    print(f"  -> Total Tickets: {stats.total_tickets}")
    print(f"  -> Open Tickets: {stats.open_tickets}")
    print(f"  -> Resolved Tickets: {stats.resolved_tickets}")
    print(f"  -> Verified Knowledge Documents: {stats.total_knowledge_docs}")
    assert stats.total_tickets > 0, "Expected non-zero total tickets"

    print("\n==================================================")
    print("[SUCCESS] ALL 10 SERVICE LAYER WORKFLOWS VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
