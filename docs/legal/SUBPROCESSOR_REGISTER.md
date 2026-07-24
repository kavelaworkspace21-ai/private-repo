# Subprocessor Register — LegalServer.AI

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23
Third parties that process data to deliver the service. Used only to provide the service; never for
model training on your data.

| Subprocessor | Purpose | Data exposed | Region | Notes |
|---|---|---|---|---|
| Amazon Web Services (EC2, Aurora PostgreSQL, S3-compatible storage) | Hosting, database, file storage | All tenant data at rest/in transit | India (us-east-1 currently — **review region for DPDP: [MISSING]**) | Cloud infrastructure |
| AI model provider (currently Google Gemini via OpenAI-compatible API) | Generate research answers / drafts on request | The prompt content you submit + retrieved corpus text | **[provider region: MISSING]** | No training on submitted data; provider-agnostic config |
| Indian Kanoon API | Live case-law search (when used) | The search query | India | Read-only |
| eCourts (authorised official API) | Hearing import (inert unless configured) | CNR/case identifiers | India | Read-only, off by default |
| Email provider (SMTP) | Transactional email (reset/invite) when configured | Email address | **[MISSING]** | Off unless configured |
| Payment gateway | Billing (when enabled) | Payment metadata | **[MISSING]** | Not yet enabled |

**[Finalise contracts, DPAs and regions before real client data — MISSING / TO BE POPULATED.]**

_Draft execution artifact; requires DPDP-reviewer confirmation._
