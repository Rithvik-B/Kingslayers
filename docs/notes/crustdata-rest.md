# Crustdata REST: exact request and response field names (P2 smoke test)

2026-10-31, Dinesh (P2). Source: docs.crustdata.com (API reference pages, `person-docs/contact/enrich.mdx`)
plus one tiny real call per endpoint through the Crustdata MCP on 2026-10-31 (request ids below). The app's
REST client (`app/crustdata.py`) and the REST smoke test (`scripts/smoke_crustdata.py`) follow this file.
Nothing here is guessed; every field name was seen in a real response or in the docs.

## Common to all four endpoints

- Base URL `https://api.crustdata.com`, all `POST`, JSON body.
- Headers: `Authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01` (required, the only
  accepted value), `Content-Type: application/json`.
- **Credits are not in the body.** The response header `X-Credits-Used` is a decimal string (e.g. `1.06`).
  `X-Request-Id` identifies the call for `account_usage_event`.
- Filters: one condition `{"field", "type", "value"}` or a group `{"op": "and"|"or", "conditions": [...]}`.
  Operators (`type`): `=`, `!=`, `<`, `>`, `=<`, `=>` (note the order: not `<=`/`>=`), `in`, `not_in`,
  `is_null`, `is_not_null`, `(.)` (fuzzy, typo-tolerant text), `[.]` (exact token).
- `fields` is a whitelist: the response carries only the groups or dotted paths listed. The id field is
  always included. Each premium group costs extra per result when filtered on or returned.
- Rate limits (default): `/company/search`, `/job/search`, `/person/search` 30 rpm; `/person/enrich` 15 rpm.
- `/person/contact/enrich` is disabled on the personal key (see `crustdata-endpoints.md`). Business emails
  come from `/person/enrich` with `fields: ["contact.business_emails"]`.

## POST /company/search (request id 9c33d4a7-5c45-4cf4-b5dc-2783a6f69ec3)

Request we use (natural-language ranked search plus hard filters):
```json
{"search": {"query": "<icp.nl_query>", "mode": "hybrid"},
 "filters": {"op": "and", "conditions": [
   {"field": "locations.country", "type": "=", "value": "India"},
   {"field": "headcount.total", "type": "=>", "value": 200}]},
 "fields": ["crustdata_company_id", "basic_info.name", "basic_info.primary_domain", "basic_info.employee_count_range",
            "taxonomy.professional_network_industry", "taxonomy.professional_network_industries",
            "headcount.total", "headcount.growth_percent", "locations.country", "locations.headquarters", "metadata"],
 "limit": 2}
```
- With `search`, `limit` is at most 100, and `sorts`/`cursor` are rejected. Results come back relevance-ordered.
- `basic_info.industries` is a **filter alias only**; asking for it in `fields` is a 400. The returned name is
  `taxonomy.professional_network_industries`.
- Filter `locations.country` accepts the full name (`India`) or ISO alpha-3 (`IND`).

Response: `{"companies": [...], "next_cursor": str|null, "total_count": null}` (`total_count` is always null
for ranked search). Per company:
```json
{"crustdata_company_id": 44625,
 "metadata": {"growth_calculation_date": "2026-10-27T23:08:48+00:00", "updated_at": "2026-10-30T00:23:30Z", "indexed_at": "..."},
 "basic_info": {"name": "ITCONS e-Solutions Limited", "primary_domain": "itconsinc.com", "employee_count_range": "1001-5000"},
 "headcount": {"total": 417, "growth_percent": {"1m": 0.97, "3m": 1.21, "6m": 1.21, "12m": 7.20}},
 "locations": {"country": "IND", "headquarters": "Noida Sector 27, ..., Uttar Pradesh, India"},
 "taxonomy": {"professional_network_industry": "Staffing and Recruiting",
              "professional_network_industries": ["Staffing and Recruiting", "Administrative and Support Services"]}}
```
- **`locations.country` is returned as ISO alpha-3 (`IND`)** even when filtered with `India`. The scorer
  normalizes both forms.
- `headcount.growth_percent.12m` is the 12-month headcount growth in percent (our `headcount_growth_12m`).
- Other groups available: `revenue`, `funding`, `hiring`, `followers`, `software_reviews`, `social_profiles`,
  `locations.state`, `locations.all_office_addresses`. There is no city field; `locations.headquarters` is a
  free-text address.
- Cost observed: 1.06 credits for 2 results with `headcount` and `taxonomy` groups (about 0.53 per result).
  Base 0.03, plus `headcount` 0.2, `taxonomy` 0.1 per result. `funding`/`hiring` would add 0.2 each.

## POST /job/search (request id 738d42cb-ed37-4990-b60c-2b96074f4541)

Request we use (per company, title keywords):
```json
{"filters": {"op": "and", "conditions": [
   {"field": "company.basic_info.company_id", "type": "=", "value": 44625},
   {"op": "or", "conditions": [{"field": "job_details.title", "type": "(.)", "value": "recruiter"},
                               {"field": "job_details.title", "type": "(.)", "value": "talent acquisition"}]}]},
 "fields": ["crustdata_job_id", "job_details.title", "job_details.url", "job_details.category",
            "company.basic_info.crustdata_company_id", "company.basic_info.name", "location.country", "location.city",
            "metadata.date_added"],
 "sorts": [{"field": "metadata.date_added", "order": "desc"}],
 "limit": 10}
```
- Filter on the company by **`company.basic_info.company_id`** (the Crustdata company id). It is returned as
  `company.basic_info.crustdata_company_id`.
- `job_details.title` with `(.)` is typo-tolerant fuzzy matching; `[.]` guarantees the literal word.
- `job_details.category` is coarse (most roles sit in "Others"); scope by title.
- Date posted is `metadata.date_added` (filterable with `=>`, sortable).

Response: `{"job_listings": [...], "next_cursor": str|null, "total_count": int}`. Per job:
```json
{"crustdata_job_id": 5481038498001263,
 "job_details": {"title": "Sr. Recruitment Executive", "url": "https://in.indeed.com/viewjob?jk=e452c0b4f0c90975"},
 "company": {"basic_info": {"crustdata_company_id": 44625}},
 "location": {"country": "India"},
 "metadata": {"date_added": "2026-02-19T16:13:21"}}
```
- `job_details.url` is a real posting URL: use it as the evidence `source_url`.
- Cost: 0.03 per result (0.06 for 2). A zero-result call costs 0.

## POST /person/search (request id 0784bce4-f54b-4a4d-84d4-e23eefcf2925)

Request we use (per company, title list):
```json
{"filters": {"op": "and", "conditions": [
   {"field": "experience.employment_details.current.company_id", "type": "=", "value": 44625},
   {"op": "or", "conditions": [{"field": "experience.employment_details.current.title", "type": "(.)", "value": "head of talent acquisition"},
                               {"field": "experience.employment_details.current.title", "type": "(.)", "value": "VP people"}]}]},
 "fields": ["crustdata_person_id", "basic_profile.name", "basic_profile.headline", "basic_profile.current_title",
            "basic_profile.location", "contact.has_business_email",
            "social_handles.professional_network_identifier.profile_url", "experience.employment_details.current"],
 "limit": 5}
```
- Filter on the company by **`experience.employment_details.current.company_id`** (alias; returned as
  `experience.employment_details.current[].crustdata_company_id`). Filtering by
  `...current.company_website_domain = "infosys.com"` also matched Infosys Consulting staff, so use the id.
- `contact.has_business_email` (bool) is returned at no extra cost: **skip `person_enrich` when it is false**
  (saves 2 credits and a 4.2 s rate-limit slot per person).
- Without `fields`, `experience` and `education` are returned and billed (0.23 per result). With the list
  above, 2 results cost 0.46.

Response: `{"profiles": [...], "next_cursor": str|null, "total_count": 763, "total_count_relation": null, "remarks": []}`.
Per profile:
```json
{"crustdata_person_id": 1088153,
 "basic_profile": {"name": "Samuel L", "headline": "Senior Talent Aquisition Specialist | Infosys",
                   "current_title": "Senior Talent Acquisition Specialist",
                   "location": {"city": "Bengaluru", "state": "Karnataka", "country": "India", "continent": "Asia", "raw": "...", "full_location": "..."}},
 "contact": {"has_business_email": true},
 "social_handles": {"professional_network_identifier": {"profile_url": "https://www.linkedin.com/in/samuel-l-8458b51b3"}},
 "experience": {"employment_details": {"current": [{"title": "Senior Talent Acquisition Specialist", "name": "Infosys",
     "crustdata_company_id": 2199, "seniority_level": "Senior", "function_category": "Human Resources",
     "start_date": "2022-05-01T00:00:00", "end_date": null, "is_default": true, "business_email_verified": false,
     "company_website": "https://www.infosys.com", "company_headcount_latest": 373698, "...": "..."}]}}}
```
- `social_handles.professional_network_identifier.profile_url` is the LinkedIn URL that `person_enrich` takes.
- `seniority_level` values seen: `Senior`, `Entry Level` (closed set; use `person_autocomplete` to list).

## POST /person/enrich (request id 488c67ac-fdab-4bf3-adea-5260327eb238)

Request:
```json
{"professional_network_profile_urls": ["https://www.linkedin.com/in/samuel-l-8458b51b3"],
 "fields": ["crustdata_person_id", "basic_profile.name", "basic_profile.current_title", "contact.business_emails",
            "social_handles.professional_network_identifier.profile_url"]}
```
- Body accepts only `professional_network_profile_urls` (max 25), `fields`, `preview`. Extra keys are rejected
  (there is no `verified` flag here; that exists only on the disabled `/person/contact/enrich`).
- Rate limit 15 rpm: the client spaces calls 4.2 s apart.
- Cost: 2 credits per matched person (base 1 + business email 1). `not_found` and `redacted` are not billed.

Response is a **top-level array**, one entry per submitted URL:
```json
[{"matched_on": "https://www.linkedin.com/in/samuel-l-8458b51b3",
  "match_type": "professional_network_profile_url",
  "match_status": "matched",
  "matches": [{"confidence_score": 1,
               "person_data": {"crustdata_person_id": 1088153,
                               "basic_profile": {"name": "Samuel L", "current_title": "...", "first_name": "Samuel", "last_name": "L", "...": "..."},
                               "contact": {"business_emails": [{"crustdata_company_id": 11981, "email": "samuel.l@infosysbpm.com",
                                                                 "last_updated": null, "status": "unknown"}]},
                               "social_handles": {"professional_network_identifier": {"profile_url": "..."}}}}]}]
```
- `match_status` is `matched` | `not_found` | `redacted`. Read the email from
  `matches[0].person_data.contact.business_emails[]`.
- **Business-email `status` values (docs `person-docs/contact/enrich.mdx`, "Email status"):**

  | status | meaning |
  |---|---|
  | `deliverable` | mailbox confirmed to exist and accept mail; lowest bounce risk |
  | `catch_all` | domain accepts any address; this mailbox can't be confirmed |
  | `invalid` | confirmed not to exist; will bounce |
  | `unknown` | deliverability couldn't be determined |

  The PLAN default `ACCEPTED_EMAIL_STATUSES=verified,valid` matches nothing. **Set
  `ACCEPTED_EMAIL_STATUSES=deliverable,catch_all`** (strict alternative: `deliverable` only; in the live call
  above the only email was `unknown`, so strict mode will leave more contacts UNREACHABLE).
- When a person has a business email, `contact.business_emails[].crustdata_company_id` says which employer
  it belongs to; the client prefers an email whose company id matches the target company.

## Credit budget for one discovery run (limit 20, 3× search window = 60)

| Step | Calls | Credits |
|---|---|---|
| company_search, 60 results with headcount + taxonomy | 1 | ~32 |
| job_search, 60 companies × ≤10 jobs | 60 | ≤18 |
| person_search, 20 companies × ≤5 people (fields above) | 20 | ~23 |
| person_enrich, ≤20 people | ≤20 | ≤40 (≈84 s at 15 rpm) |
| **Total** | | **≈113**, under `CREDIT_CEILING_PER_RUN=150` |

With `DISCOVERY_COMPANY_LIMIT=5` (15 companies searched) a run costs about 30 credits.
