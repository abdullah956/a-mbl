# Screen flows — all roles and core error states

Low-fidelity flows (roadmap §17 W1–2 deliverable, recorded post-hoc: the
implemented screens in `mobile/src/app/` are the source of truth; this maps
them). Every network step has loading, empty, error-with-retry, and timeout
states via the shared `Loading` / `EmptyState` / `ErrorNotice` components.

## Entry and authentication (all roles)

```mermaid
flowchart TD
    Boot[index: boot redirect] -->|no server saved| Connect[connect: server address + health check]
    Connect -->|Connected| Welcome
    Boot -->|no session| Welcome[auth/welcome]
    Boot -->|status pending_guardian| Pending[pending: show link code]
    Boot -->|active session| Tabs[(tabs)]
    Welcome --> Age[auth/age: month/year chips]
    Age -->|under 13| Blocked[blocked screen - nothing saved]
    Age -->|13+| Register[auth/register]
    Welcome --> Login[auth/login]
    Register -->|13-17| Pending
    Register -->|18+| Tabs
    Login -->|pending| Pending
    Login -->|active| Tabs
    Pending -->|guardian approved, re-check /v1/me| Tabs
```

Error states: unreachable server (connect screen banner + troubleshooting),
wrong credentials (field errors), expired/reused refresh token (silent
sign-out to welcome), rate limiting (429 message).

## User: analyze → case → share (§7.2–7.4)

```mermaid
flowchart TD
    Analyze[tabs/analyze] -->|type text| Result[inline result card]
    Analyze -->|scan screenshot, only when server confirms OCR| OCR[pick image -> normalize -> /v1/ocr]
    OCR -->|review + correct text| Result
    Result -->|safe| Discarded[nothing saved]
    Discarded -->|"Keep for human review anyway" §6.3| Case
    Result -->|caution/high/critical| Case[case/id]
    Case --> Reveal[deliberate Reveal of masked or withheld text]
    Case --> Context[edit platform/sender, request review]
    Case --> Review[add human review]
    Case --> Evidence[attach/view encrypted screenshot]
    Case --> Share[named confirmation -> share with organization]
    Share --> Revoke[unshare: access removed immediately]
```

Error states: OCR unavailable (503 banner) or unconfirmed (connection
warning), image too large/wrong type (413/422 field message), camera
permission denied (inline message with gallery fallback), upload timeout
(30 s, retryable).

## Guardian (§7.1, §8.3)

```mermaid
flowchart TD
    GProfile[tabs/profile] --> Enter[enter link code]
    Enter --> Preview[preview: WHO the code belongs to]
    Preview -->|approve| Linked[link active, teen activated]
    Preview -->|not now| GProfile
    GAlerts[tabs/alerts] -->|focus, foreground, 60s poll, pull| List[content-free alert list]
    List -->|tap| GCase[case/id - access re-checked]
    GMail[optional email: severity + category, no content - only when SMTP is configured] -.->|open the app| GAlerts
    GHome[tabs/index: linked-user summary + charts: per week, by weekday, repeat senders] --> Reports[reports: filters, trend, PDF]
```

Error states: invalid/expired/consumed code (404 message), non-guardian
account (403), already linked (409).

## School administrator (§8.4)

```mermaid
flowchart TD
    AHome[tabs/index: org summary + charts] --> AReports[reports: date filters, weekly trend, alias grouping, PDF download/share]
    ACases[tabs/cases: explicitly shared cases] --> ACase[case/id review]
    AProfile[tabs/profile] --> Members[members: list / add by email / remove]
    Members -->|add non-admin email| Err409[409 - only admin accounts]
    Members -->|remove| Revoked[access + alerts revoked immediately]
```

## Privacy (§7.5)

```mermaid
flowchart TD
    Profile --> Export[export data -> native share]
    Profile --> Delete[password re-entry -> confirm]
    Delete -->|wrong password| E401[401 message]
    Delete -->|evidence unlink fails| E503[503 - retry shortly, rows kept]
    Delete -->|ok| Gone[rows cascade, files removed, audit rows de-identified]
```
