-- =============================================================================
-- Unified AI for Enterprise Automation
-- MySQL Database Schema
-- Version: 1.0
-- =============================================================================
-- Naming conventions:
--   Tables     : snake_case, plural
--   PKs        : id (BIGINT UNSIGNED AUTO_INCREMENT)
--   FKs        : <table_singular>_id
--   Timestamps : created_at, updated_at (auto-managed)
--   Soft delete: deleted_at (NULL = active)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS enterprise_ai
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE enterprise_ai;

-- =============================================================================
-- 1. AUTHENTICATION & RBAC
-- =============================================================================

-- Roles catalogue (admin, hr_manager, support_agent, recruiter, employee, viewer)
CREATE TABLE roles (
    id          TINYINT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name        VARCHAR(50)         NOT NULL,
    description VARCHAR(255)        NULL,
    created_at  DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_roles_name (name)
) ENGINE=InnoDB;

-- Application users
CREATE TABLE users (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    role_id         TINYINT UNSIGNED    NOT NULL,
    full_name       VARCHAR(120)        NOT NULL,
    email           VARCHAR(255)        NOT NULL,
    hashed_password VARCHAR(255)        NOT NULL,
    is_active       TINYINT(1)          NOT NULL DEFAULT 1,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME            NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email),
    INDEX idx_users_role (role_id),
    CONSTRAINT fk_users_role
        FOREIGN KEY (role_id) REFERENCES roles (id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Refresh tokens for JWT rotation
CREATE TABLE refresh_tokens (
    id          BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED     NOT NULL,
    token_hash  VARCHAR(255)        NOT NULL,
    expires_at  DATETIME            NOT NULL,
    revoked     TINYINT(1)          NOT NULL DEFAULT 0,
    created_at  DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_rt_user (user_id),
    INDEX idx_rt_token (token_hash),
    CONSTRAINT fk_rt_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 2. EMPLOYEE MANAGEMENT
-- =============================================================================

CREATE TABLE departments (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100)    NOT NULL,
    description VARCHAR(255)    NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_departments_name (name)
) ENGINE=InnoDB;

CREATE TABLE employees (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED     NOT NULL,           -- links to login account
    department_id   INT UNSIGNED        NOT NULL,
    employee_code   VARCHAR(30)         NOT NULL,           -- e.g. EMP-0042
    job_title       VARCHAR(100)        NOT NULL,
    phone           VARCHAR(30)         NULL,
    hire_date       DATE                NOT NULL,
    employment_type ENUM('full_time','part_time','contract','intern')
                                        NOT NULL DEFAULT 'full_time',
    status          ENUM('active','inactive','on_leave','terminated')
                                        NOT NULL DEFAULT 'active',
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME            NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_employees_code (employee_code),
    UNIQUE KEY uq_employees_user (user_id),
    INDEX idx_employees_dept (department_id),
    INDEX idx_employees_status (status),
    CONSTRAINT fk_employees_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_employees_dept
        FOREIGN KEY (department_id) REFERENCES departments (id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- AI-generated performance insights per employee (one row per analysis run)
CREATE TABLE employee_ai_insights (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    employee_id     BIGINT UNSIGNED     NOT NULL,
    insight_type    VARCHAR(60)         NOT NULL,           -- e.g. 'performance_summary', 'risk_flag'
    content         TEXT                NOT NULL,
    ai_model        VARCHAR(60)         NOT NULL DEFAULT 'gemini',
    generated_at    DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_eai_employee (employee_id),
    CONSTRAINT fk_eai_employee
        FOREIGN KEY (employee_id) REFERENCES employees (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 3. CUSTOMER SUPPORT AI
-- =============================================================================

CREATE TABLE support_teams (
    id          SMALLINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    name        VARCHAR(100)        NOT NULL,
    code        VARCHAR(50)         NOT NULL,
    description VARCHAR(255)        NULL,
    is_active   TINYINT(1)          NOT NULL DEFAULT 1,
    created_at  DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_st_name (name),
    UNIQUE KEY uq_st_code (code)
) ENGINE=InnoDB;

CREATE TABLE support_categories (
    id              SMALLINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    name            VARCHAR(80)         NOT NULL,
    description     VARCHAR(255)        NULL,
    default_team_id SMALLINT UNSIGNED   NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sc_name (name),
    INDEX idx_sc_team (default_team_id),
    CONSTRAINT fk_sc_team
        FOREIGN KEY (default_team_id) REFERENCES support_teams (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE knowledge_documents (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    title           VARCHAR(255)        NOT NULL,
    category_id     SMALLINT UNSIGNED   NULL,
    doc_type        ENUM('faq','product_guide','billing_policy','troubleshooting','auth_procedure','general_policy')
                                        NOT NULL DEFAULT 'faq',
    content         LONGTEXT            NOT NULL,
    is_published    TINYINT(1)          NOT NULL DEFAULT 1,
    created_by      BIGINT UNSIGNED     NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_kd_category  (category_id),
    INDEX idx_kd_published (is_published),
    INDEX idx_kd_title     (title),
    CONSTRAINT fk_kd_category
        FOREIGN KEY (category_id) REFERENCES support_categories (id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_kd_creator
        FOREIGN KEY (created_by) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE knowledge_chunks (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    document_id     BIGINT UNSIGNED     NOT NULL,
    chunk_index     INT UNSIGNED        NOT NULL,
    chunk_text      TEXT                NOT NULL,
    keywords        VARCHAR(255)        NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_kc_doc (document_id),
    CONSTRAINT fk_kc_doc
        FOREIGN KEY (document_id) REFERENCES knowledge_documents (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE chat_sessions (
    id              VARCHAR(64)         NOT NULL,
    user_id         BIGINT UNSIGNED     NULL,
    customer_name   VARCHAR(120)        NULL,
    customer_email  VARCHAR(255)        NULL,
    status          ENUM('active','resolved','escalated')
                                        NOT NULL DEFAULT 'active',
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_cs_user   (user_id),
    INDEX idx_cs_status (status),
    INDEX idx_cs_email  (customer_email),
    CONSTRAINT fk_cs_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE chat_messages (
    id                  BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    session_id          VARCHAR(64)         NOT NULL,
    sender_type         ENUM('customer','ai','agent') NOT NULL,
    sender_id           BIGINT UNSIGNED     NULL,
    message             TEXT                NOT NULL,
    retrieved_context   TEXT                NULL,
    confidence_score    FLOAT               NULL,
    is_escalated        TINYINT(1)          NOT NULL DEFAULT 0,
    created_at          DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_cm_session (session_id),
    INDEX idx_cm_sender  (sender_id),
    CONSTRAINT fk_cm_session
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_cm_sender
        FOREIGN KEY (sender_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE support_tickets (
    id                  BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    session_id          VARCHAR(64)         NULL,
    category_id         SMALLINT UNSIGNED   NULL,
    team_id             SMALLINT UNSIGNED   NULL,
    submitted_by        BIGINT UNSIGNED     NOT NULL,           -- FK → users
    assigned_to         BIGINT UNSIGNED     NULL,               -- FK → users (support agent)
    customer_name       VARCHAR(120)        NULL,
    customer_email      VARCHAR(255)        NULL,
    subject             VARCHAR(255)        NOT NULL,
    description         TEXT                NOT NULL,
    priority            ENUM('low','medium','high','critical')
                                            NOT NULL DEFAULT 'medium',
    status              ENUM('open','assigned','in_progress','waiting_for_customer','resolved','closed','escalated')
                                            NOT NULL DEFAULT 'open',
    channel             ENUM('web','email','chat','api')
                                            NOT NULL DEFAULT 'chat',
    escalation_reason   VARCHAR(255)        NULL,
    ai_summary          TEXT                NULL,
    resolved_at         DATETIME            NULL,
    created_at          DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_st_status    (status),
    INDEX idx_st_priority  (priority),
    INDEX idx_st_submitter (submitted_by),
    INDEX idx_st_assignee  (assigned_to),
    INDEX idx_st_category  (category_id),
    INDEX idx_st_team      (team_id),
    INDEX idx_st_session   (session_id),
    CONSTRAINT fk_st_session
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_st_category
        FOREIGN KEY (category_id) REFERENCES support_categories (id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_st_team
        FOREIGN KEY (team_id) REFERENCES support_teams (id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_st_submitter
        FOREIGN KEY (submitted_by) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_st_assignee
        FOREIGN KEY (assigned_to) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- AI replies and human replies on a ticket thread
CREATE TABLE ticket_messages (
    id          BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    ticket_id   BIGINT UNSIGNED     NOT NULL,
    sender_id   BIGINT UNSIGNED     NULL,                   -- NULL = AI-generated
    message     TEXT                NOT NULL,
    is_ai       TINYINT(1)          NOT NULL DEFAULT 0,
    ai_model    VARCHAR(60)         NULL,
    created_at  DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_tm_ticket (ticket_id),
    CONSTRAINT fk_tm_ticket
        FOREIGN KEY (ticket_id) REFERENCES support_tickets (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_tm_sender
        FOREIGN KEY (sender_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- =============================================================================
-- 4. INCIDENT MANAGEMENT
-- =============================================================================

CREATE TABLE incidents (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    reported_by     BIGINT UNSIGNED     NOT NULL,
    assigned_to     BIGINT UNSIGNED     NULL,
    title           VARCHAR(255)        NOT NULL,
    description     TEXT                NOT NULL,
    severity        ENUM('low','medium','high','critical')
                                        NOT NULL DEFAULT 'medium',
    status          ENUM('open','investigating','resolved','closed')
                                        NOT NULL DEFAULT 'open',
    affected_system VARCHAR(120)        NULL,
    root_cause      TEXT                NULL,               -- filled after investigation
    resolved_at     DATETIME            NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_inc_status   (status),
    INDEX idx_inc_severity (severity),
    INDEX idx_inc_reporter (reported_by),
    INDEX idx_inc_assignee (assigned_to),
    CONSTRAINT fk_inc_reporter
        FOREIGN KEY (reported_by) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_inc_assignee
        FOREIGN KEY (assigned_to) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- Audit trail: every status change or comment on an incident
CREATE TABLE incident_timeline (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    incident_id     BIGINT UNSIGNED     NOT NULL,
    actor_id        BIGINT UNSIGNED     NULL,               -- NULL = AI action
    action          VARCHAR(80)         NOT NULL,           -- e.g. 'status_changed', 'comment_added'
    notes           TEXT                NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_it_incident (incident_id),
    CONSTRAINT fk_it_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_it_actor
        FOREIGN KEY (actor_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- AI triage suggestions per incident
CREATE TABLE incident_ai_triage (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    incident_id     BIGINT UNSIGNED     NOT NULL,
    suggested_severity  VARCHAR(20)     NOT NULL,
    suggested_owner VARCHAR(120)        NULL,
    reasoning       TEXT                NOT NULL,
    confidence      DECIMAL(5,2)        NULL,               -- 0.00 – 100.00
    ai_model        VARCHAR(60)         NOT NULL DEFAULT 'gemini',
    generated_at    DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_iat_incident (incident_id),
    CONSTRAINT fk_iat_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 5. RECRUITMENT AI
-- =============================================================================

CREATE TABLE job_postings (
    id              INT UNSIGNED        NOT NULL AUTO_INCREMENT,
    created_by      BIGINT UNSIGNED     NOT NULL,
    title           VARCHAR(150)        NOT NULL,
    department_id   INT UNSIGNED        NULL,
    description     TEXT                NOT NULL,
    requirements    TEXT                NULL,
    location        VARCHAR(100)        NULL,
    employment_type ENUM('full_time','part_time','contract','intern')
                                        NOT NULL DEFAULT 'full_time',
    status          ENUM('draft','active','closed','cancelled')
                                        NOT NULL DEFAULT 'draft',
    deadline        DATE                NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_jp_status (status),
    INDEX idx_jp_dept   (department_id),
    CONSTRAINT fk_jp_creator
        FOREIGN KEY (created_by) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_jp_dept
        FOREIGN KEY (department_id) REFERENCES departments (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE candidates (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    job_posting_id  INT UNSIGNED        NOT NULL,
    full_name       VARCHAR(120)        NOT NULL,
    email           VARCHAR(255)        NOT NULL,
    phone           VARCHAR(30)         NULL,
    resume_path     VARCHAR(512)        NULL,               -- file storage path/URL
    linkedin_url    VARCHAR(512)        NULL,
    status          ENUM('applied','screening','interview','offer','hired','rejected')
                                        NOT NULL DEFAULT 'applied',
    ai_score        DECIMAL(5,2)        NULL,               -- 0.00 – 100.00 match score
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_cand_job    (job_posting_id),
    INDEX idx_cand_status (status),
    INDEX idx_cand_score  (ai_score),
    CONSTRAINT fk_cand_job
        FOREIGN KEY (job_posting_id) REFERENCES job_postings (id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- AI screening analysis per candidate application
CREATE TABLE candidate_ai_screening (
    id                  BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    candidate_id        BIGINT UNSIGNED     NOT NULL,
    skills_extracted    JSON                NULL,           -- ["Python","FastAPI", ...]
    experience_years    TINYINT UNSIGNED    NULL,
    match_summary       TEXT                NULL,
    strengths           TEXT                NULL,
    weaknesses          TEXT                NULL,
    recommendation      ENUM('shortlist','reject','hold') NULL,
    embedding_vector_id VARCHAR(120)        NULL,           -- FAISS index reference
    ai_model            VARCHAR(60)         NOT NULL DEFAULT 'gemini',
    screened_at         DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_cas_candidate (candidate_id),
    CONSTRAINT fk_cas_candidate
        FOREIGN KEY (candidate_id) REFERENCES candidates (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================================
-- 6. MEETING INTELLIGENCE
-- =============================================================================

CREATE TABLE meetings (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    created_by      BIGINT UNSIGNED     NOT NULL,
    title           VARCHAR(255)        NOT NULL,
    scheduled_at    DATETIME            NULL,
    duration_sec    INT UNSIGNED        NULL,               -- actual recording length
    audio_path      VARCHAR(512)        NULL,               -- uploaded audio file
    status          ENUM('pending','transcribing','summarizing','completed','failed')
                                        NOT NULL DEFAULT 'pending',
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_meet_status  (status),
    INDEX idx_meet_creator (created_by),
    CONSTRAINT fk_meet_creator
        FOREIGN KEY (created_by) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Many-to-many: users who attended a meeting
CREATE TABLE meeting_participants (
    meeting_id  BIGINT UNSIGNED     NOT NULL,
    user_id     BIGINT UNSIGNED     NOT NULL,
    role        ENUM('organizer','attendee','guest')
                                    NOT NULL DEFAULT 'attendee',
    PRIMARY KEY (meeting_id, user_id),
    CONSTRAINT fk_mp_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_mp_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- Whisper transcription output
CREATE TABLE meeting_transcripts (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    meeting_id      BIGINT UNSIGNED     NOT NULL,
    full_text       LONGTEXT            NOT NULL,
    language        VARCHAR(10)         NOT NULL DEFAULT 'en',
    whisper_model   VARCHAR(30)         NOT NULL DEFAULT 'base',
    transcribed_at  DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_mt_meeting (meeting_id),           -- one transcript per meeting
    CONSTRAINT fk_mt_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- Gemini-generated summary and action items
CREATE TABLE meeting_summaries (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    meeting_id      BIGINT UNSIGNED     NOT NULL,
    summary_text    TEXT                NOT NULL,
    key_points      JSON                NULL,               -- ["point 1", "point 2", ...]
    sentiment       ENUM('positive','neutral','negative','mixed') NULL,
    ai_model        VARCHAR(60)         NOT NULL DEFAULT 'gemini',
    generated_at    DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ms_meeting (meeting_id),
    CONSTRAINT fk_ms_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- Individual action items extracted from a meeting
CREATE TABLE meeting_action_items (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    meeting_id      BIGINT UNSIGNED     NOT NULL,
    assigned_to     BIGINT UNSIGNED     NULL,
    description     TEXT                NOT NULL,
    due_date        DATE                NULL,
    is_completed    TINYINT(1)          NOT NULL DEFAULT 0,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_mai_meeting  (meeting_id),
    INDEX idx_mai_assignee (assigned_to),
    CONSTRAINT fk_mai_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings (id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_mai_assignee
        FOREIGN KEY (assigned_to) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- =============================================================================
-- 7. ANALYTICS (materialised aggregates — populated by analytics_service)
-- =============================================================================

-- Pre-computed daily KPI snapshots for fast dashboard reads
CREATE TABLE analytics_daily_snapshots (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE                NOT NULL,
    module          VARCHAR(60)         NOT NULL,           -- 'customer_support', 'incidents', etc.
    metric_key      VARCHAR(80)         NOT NULL,           -- 'tickets_opened', 'avg_resolution_time'
    metric_value    DECIMAL(14,4)       NOT NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ads_date_module_metric (snapshot_date, module, metric_key),
    INDEX idx_ads_module (module),
    INDEX idx_ads_date   (snapshot_date)
) ENGINE=InnoDB;

-- =============================================================================
-- 8. AI DECISION ENGINE — audit log
-- =============================================================================

-- Every call made through the central AI Decision Engine is logged here
CREATE TABLE ai_request_logs (
    id              BIGINT UNSIGNED     NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED     NULL,
    module          VARCHAR(60)         NOT NULL,
    action          VARCHAR(80)         NOT NULL,           -- e.g. 'screen_resume', 'triage_incident'
    prompt_tokens   INT UNSIGNED        NULL,
    completion_tokens INT UNSIGNED      NULL,
    latency_ms      INT UNSIGNED        NULL,
    status          ENUM('success','error','timeout')
                                        NOT NULL DEFAULT 'success',
    error_message   TEXT                NULL,
    created_at      DATETIME            NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_arl_user   (user_id),
    INDEX idx_arl_module (module),
    INDEX idx_arl_date   (created_at),
    CONSTRAINT fk_arl_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- =============================================================================
-- SEED: default roles
-- =============================================================================

INSERT INTO roles (name, description) VALUES
    ('admin',         'Full system access'),
    ('hr_manager',    'Employee and recruitment management'),
    ('support_agent', 'Customer support ticket handling'),
    ('recruiter',     'Recruitment pipeline management'),
    ('employee',      'Standard employee self-service access'),
    ('viewer',        'Read-only analytics access');
