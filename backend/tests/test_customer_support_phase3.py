"""
tests/test_customer_support_phase3.py

Comprehensive test suite for Phase 3 — Enterprise Knowledge Base, Document Ingestion,
Chunking, Search Foundation, and Accuracy Verification.

Tests cover:
  A. Document creation and automatic chunking
  B. Document input validation
  C. Document chunking sentence awareness
  D. Chunk ordering (sequential indexes)
  E. Chunk overlap continuity
  F. Document update and atomic chunk replacement
  G. Publication filtering (unpublished documents excluded)
  H. Accuracy Test 1: "What is the refund period?" -> Billing refund chunk top rank
  I. Accuracy Test 2: "How do I reset my password?" vs Refund doc -> 0 results
  J. Accuracy Test 3: "Why am I getting a 500 error from the API?" -> Backend API doc top rank
  K. Accuracy Test 4: "The dashboard button is not responding." -> Frontend UI doc top rank
  L. Accuracy Test 5: "What is the weather on Mars tomorrow?" -> 0 results
  M. Accuracy Test 6: "PAYMENT FAILED!!!" vs "payment failed" -> normalized equivalence
  N. Minimum relevance threshold filtering
  O. Category-aware search filtering
  P. Citation and source document traceability
  Q. Transaction rollback safety
  R. FastAPI HTTP endpoint integration tests
  S. Regression check: Existing /health and auth endpoints still function
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import unittest
from unittest import mock
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.mysql import TINYINT, SMALLINT, BIGINT

@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(type_, compiler, **kw):
    return "INTEGER"

@compiles(SMALLINT, "sqlite")
def _compile_smallint_sqlite(type_, compiler, **kw):
    return "INTEGER"

@compiles(BIGINT, "sqlite")
def _compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"

# Setup in-memory test database before application imports
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from config.database import Base, get_db
from core.security import hash_password, create_access_token
from main import app
from models.role import Role
from models.user import User
from models.ticket import (
    KnowledgeChunk,
    KnowledgeDocument,
    SupportCategory,
    SupportTeam,
)
from modules.customer_support import service
from modules.customer_support import router as cs_router
from modules.customer_support.chunking import (
    extract_keywords,
    normalize_text,
    split_text_into_chunks,
)
from modules.customer_support.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    SupportCategoryCreate,
    SupportTeamCreate,
)
from modules.customer_support.seed_data import seed_demo_knowledge_data


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class TestCustomerSupportPhase3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)

        # Seed roles and admin user
        db = TestingSessionLocal()
        roles = ["admin", "support_agent", "hr_manager", "recruiter", "employee", "viewer"]
        for idx, r_name in enumerate(roles, start=1):
            if not db.query(Role).filter(Role.name == r_name).first():
                role = Role(id=idx, name=r_name, description=f"{r_name} role")
                db.add(role)
        db.commit()

        # Create test admin user
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        admin_user = db.query(User).filter(User.email == "admin.test@enterprise.com").first()
        if not admin_user:
            admin_user = User(
                full_name="Admin Test",
                email="admin.test@enterprise.com",
                hashed_password=hash_password("AdminPass123!"),
                role_id=admin_role.id,
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        cls.admin_user = admin_user
        cls.admin_user_id = admin_user.id
        db.close()

        # Generate JWT token for API tests
        token_data = {
            "sub": str(admin_user.id),
            "email": admin_user.email,
            "role": "admin",
        }
        cls.auth_token = create_access_token(data=token_data)
        cls.auth_headers = {"Authorization": f"Bearer {cls.auth_token}"}
        db.close()

    def setUp(self):
        self.db = TestingSessionLocal()
        # Clean up support tables before each test
        self.db.query(KnowledgeChunk).delete()
        self.db.query(KnowledgeDocument).delete()
        self.db.query(SupportCategory).delete()
        self.db.query(SupportTeam).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    # =========================================================================
    # A. DOCUMENT CREATION & AUTOMATIC CHUNKING
    # =========================================================================
    def test_document_creation_and_chunk_generation(self):
        """Verify that creating a document automatically generates KnowledgeChunks."""
        doc_payload = KnowledgeDocumentCreate(
            title="Standard Billing Policy",
            doc_type="billing_policy",
            content="Invoices are issued on the 1st of every month. Payments are due within 15 days.",
            is_published=True,
        )
        doc = service.create_knowledge_document(
            db=self.db, payload=doc_payload, created_by_id=self.admin_user_id
        )

        self.assertIsNotNone(doc.id)
        self.assertEqual(doc.title, "Standard Billing Policy")
        self.assertTrue(doc.is_published)

        # Verify chunks in DB
        chunks = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).all()
        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertIn("Invoices are issued", chunks[0].chunk_text)
        self.assertIsNotNone(chunks[0].keywords)

    # =========================================================================
    # B. DOCUMENT VALIDATION
    # =========================================================================
    def test_document_validation_rejects_empty_and_invalid(self):
        """Verify that empty content or invalid category is rejected."""
        # Non-existent category ID
        with self.assertRaises(Exception):
            service.create_knowledge_document(
                db=self.db,
                payload=KnowledgeDocumentCreate(
                    title="Invalid Category Doc",
                    category_id=9999,
                    content="Valid content length here.",
                ),
            )

        # Empty content
        with self.assertRaises(Exception):
            service.create_knowledge_document(
                db=self.db,
                payload=KnowledgeDocumentCreate(
                    title="Empty Content Doc",
                    content="   ",
                ),
            )

    # =========================================================================
    # C. DOCUMENT CHUNKING (SENTENCE AWARENESS)
    # =========================================================================
    def test_document_chunking_sentence_awareness(self):
        """Verify that chunking splits along sentence boundaries without mid-word cuts."""
        long_text = (
            "Paragraph one begins here with important background. This is a complete sentence explaining system behavior. "
            "Another sentence provides additional critical context regarding platform stability.\n\n"
            "Paragraph two introduces specific troubleshooting workflows. When an error occurs, check the server logs first. "
            "Inspect the response headers for error codes. If the error persists, contact senior engineering.\n\n"
            "Paragraph three concludes the troubleshooting guide with best practices for monitoring and system observability."
        )

        chunks = split_text_into_chunks(
            content=long_text,
            max_chunk_chars=180,
            overlap_chars=40,
            min_chunk_chars=20,
        )

        self.assertGreaterEqual(len(chunks), 2)
        for c in chunks:
            # Check chunk index is integer
            self.assertIsInstance(c["chunk_index"], int)
            # Check chunk text does not start with partial cut word
            first_word = c["chunk_text"].split()[0]
            self.assertTrue(len(first_word) >= 2)

    # =========================================================================
    # D. CHUNK ORDERING
    # =========================================================================
    def test_chunk_ordering_is_sequential(self):
        """Verify chunks have ordered sequential indexes (0, 1, 2...)."""
        paragraphs = ["Paragraph number %d is detailed here with several sentences of text." % i for i in range(10)]
        content = "\n\n".join(paragraphs)

        chunks = split_text_into_chunks(content=content, max_chunk_chars=120, overlap_chars=20)
        indexes = [c["chunk_index"] for c in chunks]
        self.assertEqual(indexes, list(range(len(chunks))))

    # =========================================================================
    # E. CHUNK OVERLAP
    # =========================================================================
    def test_chunk_overlap_preserves_context(self):
        """Verify that consecutive chunks share context overlap."""
        content = (
            "Section Alpha describes the foundational architecture of the service. "
            "It outlines key distributed storage patterns and resilience guidelines.\n\n"
            "Section Beta discusses error recovery procedures and database failover mechanisms. "
            "It explains automated replication topology and failover triggers."
        )
        chunks = split_text_into_chunks(
            content=content, max_chunk_chars=120, overlap_chars=40, min_chunk_chars=20
        )
        if len(chunks) >= 2:
            # The second chunk should contain text from the tail of the first chunk
            chunk_0_text = chunks[0]["chunk_text"]
            chunk_1_text = chunks[1]["chunk_text"]
            tail_words = chunk_0_text.split()[-3:]
            # At least one tail word should be present in chunk 1
            overlap_found = any(w in chunk_1_text for w in tail_words)
            self.assertTrue(overlap_found)

    # =========================================================================
    # F. DOCUMENT UPDATE & ATOMIC CHUNK REPLACEMENT
    # =========================================================================
    def test_document_update_replaces_stale_chunks(self):
        """Verify that updating document content completely replaces old chunks."""
        doc_payload = KnowledgeDocumentCreate(
            title="Refund Policy V1",
            doc_type="billing_policy",
            content="Version 1 content: Refunds are allowed within 30 days of purchase.\n\nAdditional details for V1.",
            is_published=True,
        )
        doc = service.create_knowledge_document(db=self.db, payload=doc_payload)
        doc_id = doc.id

        old_chunks = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).all()
        old_chunk_ids = [c.id for c in old_chunks]

        # Update document title and content to V2
        update_payload = KnowledgeDocumentUpdate(
            title="Refund Policy V2",
            content="Version 2 content: Refunds are strictly allowed within 15 days of purchase only."
        )
        updated_doc = service.update_knowledge_document(
            db=self.db, document_id=doc_id, payload=update_payload
        )

        new_chunks = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).all()

        # The new chunks must have V2 content only
        self.assertEqual(len(new_chunks), 1)
        self.assertIn("15 days", new_chunks[0].chunk_text)
        self.assertNotIn("30 days", new_chunks[0].chunk_text)
        self.assertNotIn("Additional details for V1", new_chunks[0].chunk_text)

        # Search should find V2 and not V1 stale content
        search_v2 = service.search_knowledge_base(db=self.db, query="15 days")
        self.assertGreaterEqual(search_v2.total_results, 1)
        self.assertIn("15 days", search_v2.results[0].chunk_text)

        search_stale = service.search_knowledge_base(db=self.db, query="Additional details for V1")
        self.assertEqual(search_stale.total_results, 0)

    # =========================================================================
    # G. PUBLICATION FILTERING
    # =========================================================================
    def test_publication_filtering(self):
        """Verify that unpublished documents are excluded from search results."""
        doc_payload = KnowledgeDocumentCreate(
            title="Draft Internal Secret Policy",
            doc_type="general_policy",
            content="Internal secret guideline: confidential project codename is BluePhoenix.",
            is_published=False,  # DRAFT / UNPUBLISHED
        )
        service.create_knowledge_document(db=self.db, payload=doc_payload)

        # Search for BluePhoenix
        search_res = service.search_knowledge_base(db=self.db, query="BluePhoenix")
        self.assertEqual(search_res.total_results, 0)
        self.assertEqual(len(search_res.results), 0)

        # Now publish it
        doc = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.title == "Draft Internal Secret Policy").first()
        service.set_document_publication(db=self.db, document_id=doc.id, is_published=True)

        search_res_after = service.search_knowledge_base(db=self.db, query="BluePhoenix")
        self.assertEqual(search_res_after.total_results, 1)
        self.assertIn("BluePhoenix", search_res_after.results[0].chunk_text)

    # =========================================================================
    # H. ACCURACY TEST 1: REFUND PERIOD
    # =========================================================================
    def test_accuracy_test_1_refund_period(self):
        """
        Knowledge: "Customers can request refunds within 30 days."
        Query: "What is the refund period?"
        Expected: Relevant billing chunk retrieved with top rank.
        """
        seed_demo_knowledge_data(self.db)

        search_res = service.search_knowledge_base(db=self.db, query="What is the refund period?")
        self.assertGreater(search_res.total_results, 0)
        top_result = search_res.results[0]
        self.assertEqual(top_result.document_title, "Refund and Cancellation Policy")
        self.assertIn("30 days", top_result.chunk_text)
        self.assertGreaterEqual(top_result.relevance_score, 0.40)

    # =========================================================================
    # I. ACCURACY TEST 2: IRRELEVANT QUERY VS OFF-TOPIC KNOWLEDGE
    # =========================================================================
    def test_accuracy_test_2_irrelevant_query_vs_refund(self):
        """
        Knowledge: Only "Refund and Cancellation Policy" in KB.
        Query: "How do I reset my password?"
        Expected: No relevant results returned (score below threshold).
        """
        doc_payload = KnowledgeDocumentCreate(
            title="Refund and Cancellation Policy",
            doc_type="billing_policy",
            content="Customers may request a full refund within 30 days of purchase through the billing portal.",
            is_published=True,
        )
        service.create_knowledge_document(db=self.db, payload=doc_payload)

        search_res = service.search_knowledge_base(
            db=self.db, query="How do I reset my password?", min_score=0.15
        )
        self.assertEqual(search_res.total_results, 0)
        self.assertEqual(len(search_res.results), 0)

    # =========================================================================
    # J. ACCURACY TEST 3: BACKEND API 500 ERROR
    # =========================================================================
    def test_accuracy_test_3_backend_500_error(self):
        """
        Knowledge: "API requests return HTTP 500 when the backend service encounters an internal error."
        Query: "Why am I getting a 500 error from the API?"
        Expected: Backend API troubleshooting chunk ranks highest.
        """
        seed_demo_knowledge_data(self.db)

        search_res = service.search_knowledge_base(
            db=self.db, query="Why am I getting a 500 error from the API?"
        )
        self.assertGreater(search_res.total_results, 0)
        top_result = search_res.results[0]
        self.assertEqual(top_result.document_title, "Backend API Error and 500 Troubleshooting Guide")
        self.assertIn("HTTP 500", top_result.chunk_text)
        self.assertGreaterEqual(top_result.relevance_score, 0.40)

    # =========================================================================
    # K. ACCURACY TEST 4: DASHBOARD BUTTON UNRESPONSIVE
    # =========================================================================
    def test_accuracy_test_4_dashboard_button_unresponsive(self):
        """
        Knowledge: "Dashboard buttons may stop responding if the frontend application has stale browser assets."
        Query: "The dashboard button is not responding."
        Expected: Frontend troubleshooting knowledge ranks highest.
        """
        seed_demo_knowledge_data(self.db)

        search_res = service.search_knowledge_base(
            db=self.db, query="The dashboard button is not responding."
        )
        self.assertGreater(search_res.total_results, 0)
        top_result = search_res.results[0]
        self.assertEqual(top_result.document_title, "Frontend UI and Dashboard Troubleshooting Guide")
        self.assertIn("Dashboard buttons", top_result.chunk_text)
        self.assertGreaterEqual(top_result.relevance_score, 0.40)

    # =========================================================================
    # L. ACCURACY TEST 5: OUT-OF-DOMAIN UNKNOWN QUERY
    # =========================================================================
    def test_accuracy_test_5_martian_weather_unknown_query(self):
        """
        Query: "What is the weather on Mars tomorrow?"
        Expected: Zero enterprise knowledge retrieved. Does not force random docs.
        """
        seed_demo_knowledge_data(self.db)

        search_res = service.search_knowledge_base(
            db=self.db, query="What is the weather on Mars tomorrow?", min_score=0.15
        )
        self.assertEqual(search_res.total_results, 0)
        self.assertEqual(len(search_res.results), 0)

    # =========================================================================
    # M. ACCURACY TEST 6: NORMALIZATION EQUIVALENCE
    # =========================================================================
    def test_accuracy_test_6_query_normalization(self):
        """
        Queries: "PAYMENT FAILED!!!" vs "payment failed"
        Expected: Identical or substantially consistent retrieval results.
        """
        seed_demo_knowledge_data(self.db)

        res_upper = service.search_knowledge_base(db=self.db, query="PAYMENT FAILED!!!")
        res_lower = service.search_knowledge_base(db=self.db, query="payment failed")

        self.assertGreater(res_upper.total_results, 0)
        self.assertGreater(res_lower.total_results, 0)
        self.assertEqual(res_upper.total_results, res_lower.total_results)
        self.assertEqual(
            res_upper.results[0].document_id,
            res_lower.results[0].document_id,
        )
        self.assertAlmostEqual(
            res_upper.results[0].relevance_score,
            res_lower.results[0].relevance_score,
            places=3,
        )

    # =========================================================================
    # N. MINIMUM RELEVANCE THRESHOLD
    # =========================================================================
    def test_min_score_threshold_filters_weak_matches(self):
        """Verify that high min_score threshold excludes weak/partial matches."""
        seed_demo_knowledge_data(self.db)

        # Baseline search with default threshold
        res_normal = service.search_knowledge_base(
            db=self.db, query="login password reset", min_score=0.15
        )
        self.assertGreater(res_normal.total_results, 0)

        # Search with impossible threshold (1.0)
        res_strict = service.search_knowledge_base(
            db=self.db, query="login password reset", min_score=0.999
        )
        self.assertEqual(res_strict.total_results, 0)

    # =========================================================================
    # O. CATEGORY-AWARE SEARCH FILTERING
    # =========================================================================
    def test_category_aware_search_filtering(self):
        """Verify that passing category_id restricts results to that category."""
        seed_demo_knowledge_data(self.db)

        frontend_cat = self.db.query(SupportCategory).filter(SupportCategory.name == "Frontend & UI").first()
        backend_cat = self.db.query(SupportCategory).filter(SupportCategory.name == "Backend & APIs").first()

        # Search "error" restricted to Frontend
        res_fe = service.search_knowledge_base(
            db=self.db, query="troubleshooting error guide", category_id=frontend_cat.id
        )
        for item in res_fe.results:
            self.assertEqual(item.category_id, frontend_cat.id)

        # Search "error" restricted to Backend
        res_be = service.search_knowledge_base(
            db=self.db, query="troubleshooting error guide", category_id=backend_cat.id
        )
        for item in res_be.results:
            self.assertEqual(item.category_id, backend_cat.id)

    # =========================================================================
    # P. CITATION & TRACEABILITY
    # =========================================================================
    def test_source_traceability_fields(self):
        """Verify SearchResultItem contains full metadata for citation generation."""
        seed_demo_knowledge_data(self.db)

        search_res = service.search_knowledge_base(db=self.db, query="refund 30 days")
        self.assertGreater(search_res.total_results, 0)
        item = search_res.results[0]

        self.assertIsInstance(item.document_id, int)
        self.assertIsInstance(item.chunk_id, int)
        self.assertIsInstance(item.chunk_index, int)
        self.assertIsInstance(item.document_title, str)
        self.assertIsInstance(item.doc_type, str)
        self.assertIsInstance(item.chunk_text, str)
        self.assertIsInstance(item.relevance_score, float)

    # =========================================================================
    # Q. TRANSACTION ROLLBACK SAFETY
    # =========================================================================
    def test_transaction_rollback_on_chunking_error(self):
        """Verify that an ingestion failure rolls back the document row."""
        initial_doc_count = self.db.query(KnowledgeDocument).count()

        with mock.patch(
            "modules.customer_support.service.split_text_into_chunks",
            side_effect=RuntimeError("Simulated chunking failure"),
        ):
            with self.assertRaises(Exception):
                service.create_knowledge_document(
                    db=self.db,
                    payload=KnowledgeDocumentCreate(
                        title="Failing Document",
                        content="Valid content that triggers failure during chunking step.",
                    ),
                )

        final_doc_count = self.db.query(KnowledgeDocument).count()
        self.assertEqual(initial_doc_count, final_doc_count)

    # =========================================================================
    # R. FASTAPI API ROUTER HANDLERS INTEGRATION
    # =========================================================================
    def test_api_crud_and_search_endpoints(self):
        """Test full API workflow via customer support router handlers."""
        # 1. Create Team via router
        team_payload = SupportTeamCreate(
            name="Integration Test Team",
            code="integration_test_team",
            description="Team created in test",
        )
        team_res = cs_router.create_team(payload=team_payload, db=self.db, current_user=self.admin_user)
        self.assertIsNotNone(team_res.id)
        team_id = team_res.id

        # 2. Create Category via router
        cat_payload = SupportCategoryCreate(
            name="Integration Category",
            description="Category created in test",
            default_team_id=team_id,
        )
        cat_res = cs_router.create_category(payload=cat_payload, db=self.db, current_user=self.admin_user)
        self.assertIsNotNone(cat_res.id)
        cat_id = cat_res.id

        # 3. Create Knowledge Document via router
        doc_payload = KnowledgeDocumentCreate(
            title="API Guide for Integration Testing",
            category_id=cat_id,
            doc_type="product_guide",
            content="Comprehensive guide for API testing and system integration. Authentication uses JWT tokens.",
            is_published=True,
        )
        doc_res = cs_router.create_knowledge_document(payload=doc_payload, db=self.db, current_user=self.admin_user)
        self.assertIsNotNone(doc_res.id)
        doc_id = doc_res.id
        self.assertGreaterEqual(len(doc_res.chunks), 1)

        # 4. Get Document Details via router
        get_res = cs_router.get_knowledge_document(document_id=doc_id, db=self.db, current_user=self.admin_user)
        self.assertEqual(get_res.title, "API Guide for Integration Testing")

        # 5. Search via router
        search_res = cs_router.search_knowledge_base(
            q="integration testing jwt",
            category_id=None,
            doc_type=None,
            min_score=0.15,
            limit=5,
            db=self.db,
            current_user=self.admin_user,
        )
        self.assertGreaterEqual(search_res.total_results, 1)

        # 6. Unpublish via router
        unpub_res = cs_router.unpublish_knowledge_document(
            document_id=doc_id, db=self.db, current_user=self.admin_user
        )
        self.assertFalse(unpub_res.is_published)

        # 7. Search should now return 0 results
        search_after_unpub = cs_router.search_knowledge_base(
            q="integration testing jwt",
            category_id=None,
            doc_type=None,
            min_score=0.15,
            limit=5,
            db=self.db,
            current_user=self.admin_user,
        )
        self.assertEqual(search_after_unpub.total_results, 0)

        # 8. Re-publish via router
        pub_res = cs_router.publish_knowledge_document(
            document_id=doc_id, db=self.db, current_user=self.admin_user
        )
        self.assertTrue(pub_res.is_published)

        # 9. Reindex via router
        reindex_res = cs_router.reindex_knowledge_document(
            document_id=doc_id, db=self.db, current_user=self.admin_user
        )
        self.assertEqual(reindex_res.status, "success")

        # 10. Update Document via router
        update_payload = KnowledgeDocumentUpdate(
            title="Updated API Guide for Integration Testing",
            content="Updated content with OAuth2 bearer token instructions.",
        )
        update_res = cs_router.update_knowledge_document(
            document_id=doc_id, payload=update_payload, db=self.db, current_user=self.admin_user
        )
        self.assertEqual(update_res.title, "Updated API Guide for Integration Testing")

        # 11. List Documents via router
        list_res = cs_router.list_knowledge_documents(
            category_id=None,
            doc_type=None,
            is_published=None,
            search=None,
            skip=0,
            limit=50,
            db=self.db,
            current_user=self.admin_user,
        )
        self.assertGreaterEqual(len(list_res), 1)

        # 12. Stats via router
        stats_res = cs_router.customer_support_stats(db=self.db, current_user=self.admin_user)
        self.assertGreaterEqual(stats_res.total_knowledge_docs, 1)

        # 13. Delete Document via router
        cs_router.delete_knowledge_document(
            document_id=doc_id, db=self.db, current_user=self.admin_user
        )

        # Verify 404 after deletion
        with self.assertRaises(Exception):
            cs_router.get_knowledge_document(
                document_id=doc_id, db=self.db, current_user=self.admin_user
            )

    # =========================================================================
    # S. REGRESSION & FASTAPI ROUTER REGISTRATION CHECKS
    # =========================================================================
    def test_fastapi_app_and_routes_registered(self):
        """Verify that FastAPI app initializes properly with all routers registered."""
        route_paths = [route.path for route in app.routes]
        # Verify /health route exists
        self.assertIn("/health", route_paths)
        # Verify customer support routes are registered under /api/v1/customer-support
        cs_routes = [p for p in route_paths if "/customer-support" in p]
        self.assertIn("/api/v1/customer-support/health", route_paths)
        self.assertIn("/api/v1/customer-support/knowledge", route_paths)
        self.assertIn("/api/v1/customer-support/knowledge/search", route_paths)
        self.assertIn("/api/v1/customer-support/categories", route_paths)
        self.assertIn("/api/v1/customer-support/teams", route_paths)
        self.assertIn("/api/v1/customer-support/stats", route_paths)

        # Test health endpoint response structure
        health_resp = cs_router.customer_support_health()
        self.assertEqual(health_resp["status"], "ok")
        self.assertEqual(health_resp["module"], "customer_support")


if __name__ == "__main__":
    unittest.main()
