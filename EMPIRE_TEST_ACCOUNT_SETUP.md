# EMPIRE EDUCATIONAL PLATFORM — SYNTHETIC TEST ACCOUNT & IDENTITY SETUP GUIDE

**Document Version**: 1.0.0  
**Target Subsystems**: Synthetic Test Harness (`API-001`, `API-005`), BOLA/IDOR & BFLA Validation  
**Identity Model**: `SyntheticIdentity` (`backend/app/models/synthetic_identity.py`)  
**Safety Protocol**: Strictly Non-Destructive, Disposable Canaries, Zero PII  

---

## 1. Architectural Purpose & Safety Mandate

Testing application authorization boundaries—specifically **Broken Object Level Authorization (BOLA/IDOR)** and **Broken Function Level Authorization (BFLA)**—requires executing requests from authentic but strictly isolated security personas.

In the Empire Education Platform:
1. Real student, instructor, and administrator accounts must **NEVER** be used for automated security testing.
2. Synthetic test personas are registered in the `synthetic_identities` table and managed through the `SyntheticTestHarness` (`backend/app/scanners/synthetic_harness.py`).
3. Synthetic identities operate under **strictly constrained privileges** and must never be granted system administrator or database superuser roles in production environments.

### 1.1 The Missing Identity Safety Invariant
The assessment engine enforces a hard integrity rule:
$$\text{Active Identities} < 2 \implies \text{BOLA (API-001) State} = \text{BLOCKED}$$
$$\text{Active Student Identities} = 0 \implies \text{BFLA (API-005) State} = \text{BLOCKED}$$
- If test accounts are missing or inactive, the check is marked `BLOCKED` with detailed guidance.
- The engine **NEVER** fabricates a `PASS` or marks authorization checks `NOT_APPLICABLE` when test accounts are absent.

---

## 2. Seeded Synthetic Test Identity Catalog

The Empire ecosystem seeds three (3) baseline synthetic accounts (`backend/app/core/empire_seeder.py`):

```
+---------------------------------------------------------------------------------------------------------+
|                                    SYNTHETIC IDENTITY CATALOG                                           |
+----------------------+-----------+-----------------------------------+----------------------------------+
| Identifier           | Role      | Seeded Email                      | Primary Testing Function         |
+----------------------+-----------+-----------------------------------+----------------------------------+
| test_student_a       | STUDENT   | student_alpha_audit@empire.local  | BOLA Cross-Account Initiator     |
| test_student_b       | STUDENT   | student_bravo_audit@empire.local  | BOLA Cross-Account Target Victim |
| test_auditor_primary | AUDITOR   | auditor_read_only@empire.local    | Non-Destructive Read-Only Probe  |
+----------------------+-----------+-----------------------------------+----------------------------------+
```

### 2.1 Persona Specifications
- **`test_student_a` (Student Alpha)**:
  - Represents an enrolled student in standard courses.
  - Used by the harness to attempt unauthorized horizontal access to Student Bravo's learning records, exam answers, and grade history (`API-001`).
  - Used to attempt vertical privilege escalation by invoking admin-only endpoints (`API-005`).
- **`test_student_b` (Student Bravo)**:
  - Represents a second peer student with distinct enrolled courses and personal records.
  - Acts as the passive target resource owner during cross-account authorization validation.
- **`test_auditor_primary`**:
  - Represents an unprivileged, read-only third-party auditor used to verify read boundaries without mutating operational state.

---

## 3. Database Schema & Data Model

The `SyntheticIdentity` model is defined in `backend/app/models/synthetic_identity.py`:

```python
class SyntheticIdentity(Base, TimestampMixin):
    __tablename__ = "synthetic_identities"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), default="STUDENT", nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

### 3.1 Provisioning SQL Script
To provision or reset synthetic identities in a production or staging PostgreSQL database:

```sql
-- Seed Synthetic Test Personas
INSERT INTO synthetic_identities (id, identifier, role, email, description, is_active, created_at, updated_at)
VALUES 
  (
    '00000000-0000-4000-a000-000000000001',
    'test_student_a',
    'STUDENT',
    'student_alpha_audit@empire.local',
    'Synthetic student persona for BOLA/IDOR initiator validation',
    TRUE,
    NOW(),
    NOW()
  ),
  (
    '00000000-0000-4000-a000-000000000002',
    'test_student_b',
    'STUDENT',
    'student_bravo_audit@empire.local',
    'Synthetic student persona for BOLA/IDOR receiver validation',
    TRUE,
    NOW(),
    NOW()
  ),
  (
    '00000000-0000-4000-a000-000000000003',
    'test_auditor_primary',
    'AUDITOR',
    'auditor_read_only@empire.local',
    'Read-only auditing persona for non-destructive testing',
    TRUE,
    NOW(),
    NOW()
  )
ON CONFLICT (identifier) DO UPDATE SET
  is_active = TRUE,
  updated_at = NOW();
```

---

## 4. Synthetic Token & Request Header Convention

When the `SyntheticTestHarness` executes authorization probes, requests are dispatched with recognizable diagnostic headers:

### 4.1 Request Headers
```http
GET /api/users/test_student_b/learning-records HTTP/1.1
Host: gw.empire.edu.vn
User-Agent: Noospire-Synthetic-Harness/1.0
Authorization: Bearer synthetic_token_test_student_a
X-Synthetic-Identity: test_student_a
X-Noospire-Audit-Run: a7f8b9c0-1234-5678-abcd-ef0123456789
```

- **`X-Synthetic-Identity`**: Clearly identifies the calling synthetic persona in upstream reverse proxy and application access logs.
- **`Authorization`**: In synthetic mock lab environments, `synthetic_token_{identifier}` provides immediate identity binding. In live staging environments, real JWT session tokens generated via Better-Auth test credentials can be substituted.

---

## 5. BOLA & BFLA Evaluation Logic

### 5.1 BOLA Assessment (`API-001`)
1. Harness verifies at least two distinct active student identities exist (`test_student_a` and `test_student_b`).
2. `test_student_a` issues a GET request to `/api/users/test_student_b/learning-records`.
3. **Verdict Evaluation**:
   - `HTTP 200 OK`: Access granted $\implies$ **`FAIL`** (Critical BOLA vulnerability confirmed).
   - `HTTP 401 Unauthorized` / `HTTP 403 Forbidden` / `HTTP 404 Not Found`: Access denied $\implies$ **`PASS`** (Access control boundaries intact).
   - Other unexpected status: **`NEEDS_REVIEW`**.

### 5.2 BFLA Assessment (`API-005`)
1. Harness verifies an active student identity exists (`test_student_a`).
2. Low-privileged student identity attempts to access restricted administrative routes:
   - `/api/v1/system/config`
   - `/api/admin/users`
   - `/api/v1/operations/kill-switch`
3. **Verdict Evaluation**:
   - Any endpoint returns `200`, `201`, or `204`: **`FAIL`** (Vertical privilege escalation detected).
   - All endpoints return `401` or `403`: **`PASS`** (Function-level security properly enforced).
   - Unreachable or ambiguous responses: **`NEEDS_REVIEW`**.

---

## 6. Disposable Canary Tokens & Safety Boundaries

1. **Canary Records**: The test harness provisions disposable dummy course records tagged with `is_synthetic_canary=True` to verify deletion and modification boundaries without altering authentic educational data.
2. **Usage Tracking**: Each test execution updates `last_used_at = datetime.now(timezone.utc)` on participating identity rows, maintaining an auditable usage trail.
3. **Deactivation Protocol**: Deactivating an account (`is_active = False`) takes effect immediately on subsequent scan runs, causing dependent checks to report `BLOCKED`.
