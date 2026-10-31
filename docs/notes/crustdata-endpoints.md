# Crustdata endpoint check (personal account), 2026-10-31

Source: Crustdata MCP `account_endpoints` (free), exec ids 5ff3ec6b-51fa-466c-a678-15446b359637 and 0b833045-5d6c-4d56-9590-0bd08d346ea1. api_version 2025-11-01.

| Path | Status | Notes |
|---|---|---|
| /company/search | enabled | supports `search` (natural language) or `filters`; ranked search limit max 100, no sorts |
| /company/enrich | enabled | |
| /company/search/autocomplete | enabled | |
| /job/search | enabled | POST https://api.crustdata.com/job/search |
| /person/search | enabled | |
| /person/search/autocomplete | enabled | |
| /person/enrich | enabled | effective rate limit 15 rpm; enabled fields include contact.business_emails, contact.business_emails.email, contact.business_emails.status, contact.personal_emails |
| /web/enrich/live | enabled | |
| /person/contact/enrich | DISABLED | all contact fields disabled; docs path POST https://api.crustdata.com/person/contact/enrich (1 cr business email, +0.5 verified) |
| /job/professional_network/search/live | disabled | |
| /batch/* (all) | disabled | |

Implication: on this key, business emails come from /person/enrich with fields ["contact.business_emails"], not /person/contact/enrich. The "verified" gate must use contact.business_emails.status. The hackathon-issued key must be re-checked at 0:00.
