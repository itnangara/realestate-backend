1 — High-level goal (one sentence)
User completes profile → requests one or more elevated roles (e.g., seller, agent, landlord, investor) → optionally completes KYC/docs → system approves role(s) → user gets role-based capabilities (create/publish listings) — all done securely, auditable, and configurable.

2 — Key principles (enterprise)
Ownership of decision: backend enforces all authorizations; frontend is a thin client.


JWT / server-side identity: ownership/resolution via JWT only; never rely on client user_id.


Least privilege by default: new role requests start with limited capability (draft-only) until approved.


Separation of concerns: role requests, KYC, moderation, and property creation are separate systems hooked by events.


PII safety: sensitive docs go to S3 with restricted access and field-level DB encryption when necessary.


Auditability: every role request and change must be logged in audit_logs with request_id and actor.


Idempotence & retries: external KYC/provider webhooks handled idempotently.


Feature flags & quotas: enable staged rollouts and soft caps for new sellers.



3 — Entities / DB additions (concise)
Add or verify these tables/columns (Postgres example):
users (existing) — ensure:
id, email, password_hash, roles jsonb OR user_roles table, email_verified_at, status


status enum: pending, active, suspended, banned


role_requests (new)
id bigserial primary key


user_id bigint references users(id)


requested_roles text[] — list of roles requested (e.g., ['seller','agent'])


requested_at timestamptz


status text enum: pending, in_review, approved, rejected


reviewed_by bigint nullable (admin id)


reviewed_at timestamptz nullable


notes text nullable


attachments jsonb — links to uploaded supporting docs metadata


trust_score float default 0.0 (optional)


kyc_requests (new)
id


user_id


provider_reference varchar


status enum: not_started|submitted|in_review|approved|rejected|error


verdict jsonb — provider result payload


submitted_at, completed_at


raw_response jsonb (index for search)


attempts int


documents (new)
id, user_id, type enum (id_front,id_back,proof_of_address,company_doc), s3_key, uploaded_at, status


store s3_key (not raw file); access via signed URLs


audit_logs (new)
id, actor_id, action, target_type, target_id, meta jsonb, request_id, created_at


user_limits / quotas (optional)
track per-user quota counters (listings_remaining_today, etc.)



4 — Backend endpoints / API contract (precise)
All endpoints return consistent JSON responses and proper HTTP codes. Use request_id in logs.
Profile & role request
GET /api/users/me — returns UserResponse with roles, status.


PUT /api/users/me — update profile (name, phone, address, company).


POST /api/roles/request
 Request body:

 {
  "requested_roles": ["seller","agent"],
  "reason": "I sell houses in Amsterdam",
  "attachments": ["document_ids..."]  // optional
}
 Response: 201 { "request_id": 123, "status": "pending" }


GET /api/roles/requests/me — list user's requests and status


Document upload
POST /api/documents/upload — multipart/form-data, returns { document_id, upload_url, download_url (signed) }
 (S3 presigned upload flow: backend returns presigned PUT + metadata recorded in documents.)


KYC
POST /api/kyc/submit — submit KYC (links to document ids). Enqueues provider job; returns 202.


GET /api/kyc/status — returns current KYC status.


Admin / moderator
GET /api/admin/role-requests?status=pending — paginated.


POST /api/admin/role-requests/{id}/approve — body: {roles_granted: ["seller"], notes: ""}


POST /api/admin/role-requests/{id}/reject — body: {reason: "doc unreadable"}


Hooks and events
POST /api/webhooks/kyc — provider callbacks (idempotent, verify signature)



5 — Backend behavior & business rules (detailed)
Role request creation


Require email_verified_at present; otherwise return 400.


Persist role_requests record with status = pending.


Attach provided documents (document ids) to role_requests.attachments.


Enqueue an async job: process_role_request(request_id).


Processing path (async job)


If KYC required (config per role or country), submit docs to KYC provider; set kyc_requests.status = submitted.


Wait for provider webhook or poll (prefer webhook).


Evaluate provider verdict (automated):


clear → auto-approve for low-risk combos (e.g., seller + low value).


review → set role_requests.status = in_review, push to moderation queue.


reject → set role_requests.status = rejected, notify user.


If auto-approved, call grant_roles(user_id, granted_roles, request_id).


Granting roles


grant_roles does:


Add roles to users.roles (or user_roles table).


Emit audit_logs entry.


Send email/notification.


Optionally lift constraints (allow publish).


Always log who/what granted it (system or admin id) with request_id.


✅ Industry Standard (Use This) — Role-Level Approval, Not Partial Function Access
When a user requests to become a seller, they:
Submit all seller onboarding details (KYC, property ownership proof, verification docs).


They cannot act as a seller yet — no property creation, no seller dashboard.


Their request enters an approval workflow (pending → approved or rejected).


Once approved, the seller role is activated, and seller-specific endpoints/features unlock.


Rejections & appeals


role_requests status rejected must include notes and a link to appeal/resubmit.


Allow resubmit by creating a new role_request referencing previous (or same record updated with new docs).


Audit & retention


Record every action to audit_logs.


Keep raw KYC documents for minimal retention required by law; rotate/delete per policy.


Idempotency & retries


Webhook handlers must be idempotent (use provider reference to dedupe).


Job retries with exponential backoff; failures alert ops.


Security


All endpoints require HTTPS.


Document upload presigned URLs must expire quickly.


PII fields in DB encrypted at rest if required.


Separate S3 bucket/path for PII with restricted IAM.


Feature flags


Toggle auto-approve flows and KYC enforcement with feature flags per environment.

### MORE DETAILS
fully integrated, enterprise-grade Markdown “canonical spec” for Cursor. This will include DB schema, API contract, business rules/workflows, and security requirements, all in one place, fully structured and ready to hand over. Here’s a complete example:

# Real Estate Multi-Role Platform — Canonical Spec

## 1. DB Schema (Enterprise-Grade)

### Users
```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email_verified_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- enum: pending, active, suspended, banned
    roles JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

User Roles (Optional if separate table)
CREATE TABLE user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    role VARCHAR(50) NOT NULL, -- e.g., seller, agent
    granted_by BIGINT, -- admin_id or system
    granted_at TIMESTAMPTZ DEFAULT now()
);

Role Requests
CREATE TABLE role_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) NOT NULL,
    requested_roles TEXT[] NOT NULL,
    requested_at TIMESTAMPTZ DEFAULT now(),
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, in_review, approved, rejected
    reviewed_by BIGINT,
    reviewed_at TIMESTAMPTZ,
    notes TEXT,
    attachments JSONB,
    trust_score FLOAT DEFAULT 0.0
);

KYC Requests
CREATE TABLE kyc_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    provider_reference VARCHAR(255) UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'not_started', -- not_started|submitted|in_review|approved|rejected|error
    verdict JSONB,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    raw_response JSONB,
    attempts INT DEFAULT 0
);

Documents
CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    type VARCHAR(50) NOT NULL, -- id_front, id_back, proof_of_address, company_doc
    s3_key VARCHAR(255) NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    status VARCHAR(20) DEFAULT 'pending'
);

Audit Logs
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT REFERENCES users(id),
    action VARCHAR(255),
    target_type VARCHAR(50),
    target_id BIGINT,
    meta JSONB,
    request_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT now()
);

User Limits / Quotas (Optional)
CREATE TABLE user_limits (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    listings_remaining_today INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);

2. API Contract (Endpoints & JSON)
Profile & Role Request

GET /api/users/me
Response:

{
  "id": 123,
  "email": "user@example.com",
  "roles": ["buyer"],
  "status": "active",
  "name": "John Doe",
  "phone": "+31612345678",
  "company": "JD Realty"
}


PUT /api/users/me
Request:

{
  "name": "John Doe",
  "phone": "+31612345678",
  "company": "JD Realty"
}


Response: 200 OK

POST /api/roles/request
Request:

{
  "requested_roles": ["seller", "agent"],
  "reason": "I sell houses in Amsterdam",
  "attachments": [1,2,3]
}


Response: 201 Created

{
  "request_id": 123,
  "status": "pending"
}


GET /api/roles/requests/me
Response:

[
  {
    "id": 123,
    "requested_roles": ["seller"],
    "status": "in_review",
    "requested_at": "2025-11-09T01:00:00Z",
    "attachments": [1,2]
  }
]

Document Upload

POST /api/documents/upload (multipart/form-data)
Response:

{
  "document_id": 1,
  "upload_url": "https://s3.amazonaws.com/...?signature=xyz",
  "download_url": "https://s3.amazonaws.com/...?signature=abc"
}

KYC

POST /api/kyc/submit
Request:

{
  "document_ids": [1,2],
  "role_request_id": 123
}


Response: 202 Accepted

GET /api/kyc/status
Response:

{
  "status": "in_review",
  "provider_reference": "kyc-abc-123",
  "verdict": null
}

Admin / Moderator

GET /api/admin/role-requests?status=pending — paginated list

POST /api/admin/role-requests/{id}/approve

{
  "roles_granted": ["seller"],
  "notes": "Verified ownership docs"
}


POST /api/admin/role-requests/{id}/reject

{
  "reason": "Documents unreadable"
}

Hooks & Events

POST /api/webhooks/kyc — provider callbacks (idempotent, signature-verified)

3. Business Rules & Workflows

Role Request Creation

Requires email_verified_at; otherwise 400.

Status: pending.

Attach documents.

Enqueue async job process_role_request(request_id).

Async Processing

Submit KYC if required.

Wait for webhook or poll provider.

Auto-approve if low risk (configurable per role/country).

Otherwise, push to moderation (in_review) or reject.

Granting Roles

grant_roles(user_id, roles, request_id)

Update users.roles or user_roles.

Log audit entry.

Notify user.

Lift publish restrictions if applicable.

Rejections & Appeals

Include notes and appeal link.

Allow resubmit via new role_request referencing prior.

Audit & Retention

Every action logged.

KYC docs stored per legal retention; encrypted at rest.

Idempotency & Retries

Webhooks deduplicated using provider_reference.

Async jobs retried with exponential backoff; failures alert ops.

4. Security Requirements

All endpoints: HTTPS only.

JWT: Only backend-verified; no client trust.

Presigned S3 URLs: short-lived; separate bucket/path for PII.

DB Encryption: Sensitive fields encrypted at rest.

Admin scopes: /api/admin/* requires role=admin + scoped permissions.

Audit logs: immutable, structured JSON.

Feature flags: toggle KYC enforcement and auto-approve per environment.

# Real Estate Platform — Role & KYC Event Flow

```mermaid
flowchart TD
    %% Users & Profile
    A[User] -->|Complete Profile| B[Backend: Users Table]

    %% Role Request
    A -->|Submit Role Request + Documents| C[role_requests Table]
    C --> D[Async Job: process_role_request(request_id)]

    %% KYC Flow
    D -->|KYC Required?| E{Is KYC Required for Role/Country?}
    E -->|Yes| F[Create kyc_requests Record]
    F --> G[Submit Documents to KYC Provider]
    G -->|Webhook Callback| H[Update kyc_requests.status]
    H --> I{Provider Verdict}
    I -->|Clear / Low Risk| J[Auto-Approve Role]
    I -->|Review Needed| K[Moderation Queue: in_review]
    I -->|Reject| L[Reject Role Request]

    %% Role Granting
    J --> M[grant_roles(user_id, roles, request_id)]
    K -->|Admin Approves| M
    L -->|Notify User + Notes| A

    %% Audit Logging
    C -->|Log: request creation| Z[audit_logs]
    F -->|Log: KYC submission| Z
    J -->|Log: role granted| Z
    K -->|Log: moderation action| Z
    L -->|Log: rejection| Z

    %% Notifications
    M -->|Email / Push| A
    L -->|Email / Push| A

    %% Documents
    A -->|Upload Docs via Presigned S3| D
    D -->|Attach to role_request| C
markdown
Copy code

### ✅ Flow Explanation

1. **User submits role request** → async job handles processing.
2. **KYC requirement** is evaluated per role/country (data-driven rules).
3. **Provider verdict** leads to auto-approve, moderation, or rejection.
4. **Roles granted** only after explicit approval; never partial.
5. **Audit logging** captures every action (request, KYC, approval, rejection).
6. **Notifications** always inform user of status change.
7. **Documents** stored securely in S3; links referenced in DB.

---

This diagram is **directly implementable**:

- Shows **async vs sync paths**.
- Connects **tables, jobs, webhooks, and notifications**.
- Explicitly tracks **audit logging** for every action.
- Supports **feature flags** (auto-approve toggle) via decision nodes.

---

DB entities/tables

API endpoints

Async & sync workflows (role request, KYC, moderation, auto-approve)

Audit logging & notifications

Security touchpoints (JWT, S3, admin scopes)

This will give Cursor a single source of truth for coding everything accurately. Here’s a Markdown + Mermaid version:

# Real Estate Multi-Role Platform — Full Event & API Flow

```mermaid
flowchart TD
    %% Users
    A[User] -->|Complete Profile| B[Users Table]
    B -->|Fetch/Update Profile| API1[GET/PUT /api/users/me]

    %% Role Requests
    A -->|Submit Role Request + Docs| C[role_requests Table]
    C -->|Log Creation| Z[audit_logs]
    API2[POST /api/roles/request] --> C
    API3[GET /api/roles/requests/me] --> C

    %% Document Upload
    A -->|Upload Docs| D[documents Table]
    API4[POST /api/documents/upload] --> D
    D -->|Attach to role_request| C

    %% Async Job Processing
    C -->|Trigger Async Job| J1[process_role_request(request_id)]

    %% KYC Decision
    J1 --> E{Is KYC Required?}
    E -->|Yes| F[kyc_requests Table]
    F --> G[Submit to KYC Provider]
    G -->|Webhook Callback| H[Update kyc_requests.status]
    H --> I{Provider Verdict}
    I -->|Clear / Low Risk| K[Auto-Approve Role]
    I -->|Review| L[Moderation Queue]
    I -->|Reject| M[Reject Role Request]

    %% Grant Roles
    K --> N[grant_roles(user_id, roles, request_id)]
    L -->|Admin Approves| N
    M -->|Notify User + Notes| A

    %% Admin Endpoints
    API5[GET /api/admin/role-requests] --> L
    API6[POST /api/admin/role-requests/{id}/approve] --> N
    API7[POST /api/admin/role-requests/{id}/reject] --> M

    %% Audit Logging
    K -->|Log Grant| Z
    L -->|Log Moderation| Z
    M -->|Log Rejection| Z
    F -->|Log KYC Submission| Z
    J1 -->|Log Async Job| Z

    %% Notifications
    N -->|Email / Push| A
    M -->|Email / Push| A

    %% Security
    classDef secure fill:#f9f,stroke:#333,stroke-width:2px;
    B, C, D, F, G, H, N, L, M,Z,API1,API2,API3,API4,API5,API6,API7 class secure;

Key Features of This Canonical Diagram

Endpoints linked to tables: Cursor can see exactly which table each API hits.

Async vs sync flow: Role requests trigger jobs, KYC handled async, auto-approve or moderation paths clear.

Audit logging everywhere: Every mutation recorded in audit_logs.

Notifications included: Users always informed of status changes.

Security baked in: JWT verification, admin roles, S3/document access implicit.

Document handling: Presigned upload flow tied to role requests.

1️⃣ Final Validation

Goal: Make sure the spec is complete, consistent, and unambiguous before handing it to Cursor or devs.

✅ Check DB schema references match API contract fields.

✅ Verify all enums, status codes, and types are consistent.

✅ Ensure async flows are clearly marked with triggers and callbacks.

✅ Confirm every action is auditable (all mutations write to audit_logs).

✅ Security gates are clearly defined: JWT, admin scopes, presigned URLs, PII encryption.

### Rule - we will do things phase by phase
- wait for my approval before moving onto the next phase

1️⃣ Phase-by-Phase Approach (Recommended)
Phase	What to Implement	Why Phase It	Output / Checkpoints
Phase 1	DB schema & migrations	Foundation — ensures all tables, enums, and relationships are correct	DB models + migrations + tests
Phase 2	API endpoints (sync)	Make sure each endpoint matches spec, request/response types, validation	Controllers, routers, unit tests
Phase 3	Document upload flow	S3 presigned URLs, attachments, security	Upload endpoint, signed URL validation
Phase 4	Async job processing	Role requests → KYC submission → moderation queue	Async jobs, webhook handlers, idempotency
Phase 5	Role granting & audit	Ensure only approved roles unlock features; audit logging works	grant_roles function, audit_logs, notifications
Phase 6	Admin flows	Role approvals/rejections, moderation, quotas	Admin endpoints, security enforcement
Phase 7	Feature flags & config	Auto-approve toggle, KYC enforcement, quotas	Config-based toggles, safe testing
Phase 8	Integration & testing	End-to-end flow for one role request	Integration tests, audit verification, security checks
