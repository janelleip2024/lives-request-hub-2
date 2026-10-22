# Lives Request Hub

A working prototype for the SMU DSA 2026 Data Case Competition (Lives Group, Modernizing Master Data Management).

It is one place where Lives Group staff (requestors, approvers, the MDM team) and external parties (customers and vendors) communicate about master data requests and purchase orders, replacing today's email threads.

## Run it

No build step and no install. Open `index.html` in a browser, or turn on GitHub Pages for the repo.

- Data is demo data and is saved in your browser only (localStorage). **Reset demo** restores it.
- Use **Viewing as** (top right) to switch between personas. The internal ones come from the case brief (Amy, Wei Jie, Priya, Marcus) plus invented approvers. Dr. Lee, Ms. Cruz and Hana are external.
- `app.html` is the same page without the `<html>/<head>` wrapper (used for the hosted Claude artifact). Edit `app.html`, then rebuild `index.html`:

```sh
{ printf '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n</head>\n<body>\n'; cat app.html; printf '\n</body>\n</html>\n'; } > index.html
```

## How each feature answers the brief's pain points

| Pain point (brief section 4) | What the hub does | Where to see it in the demo |
|---|---|---|
| No standard intake form; incomplete submissions bounce back and forth | One form per record type (Customer, Item, Vendor, Cost Center) with required fields set by MDM. Submit stays locked until every required field is filled, with a completeness meter. | Amy → New request |
| Duplicate customers, vendors and items | Live fuzzy duplicate check against SAP B1 records and open requests as you type. It handles abbreviations and legal suffixes ("Natl Univ Hosp" finds National University Hospital). A strong match blocks submission unless the requester explains the difference, and approvers see that reason. | New request → type "Natl University Hosp"; MDM-1039 shows an override reason |
| Requestors can't see status; approvers don't know a request is waiting | Every request shows a live approval timeline: who has it and for how long. Each approver gets a "Waiting on you" queue and a (simulated) Teams notification when it's their turn. | My work for any persona; All requests |
| A 5-step chain takes 2–3 weeks because nobody is nudged | Automatic reminder after 48h, plus a one-click "Nudge" button. The All requests view tracks average submit-to-SAP time against the 18-day email baseline. | MDM-1041 (waiting on Daniel over 48h) |
| No record of who approved what, or when | Append-only audit trail on every request: submissions, approvals, returns, rejections, field edits and every view of a restricted field. | Audit trail panel on any request |
| Bank details and credit terms travel by email | Fields marked Restricted are masked for everyone except Finance and MDM. Revealing one is logged. External parties never see them. | Open MDM-1042 as Marcus, then as Wei Jie |
| Adding a business unit, field or approval step needs IT | MDM edits forms and approval routes in a settings screen: add or remove fields, mark them required or restricted, add, reorder or remove approval steps. Changes are versioned, and requests already in flight keep their original route. | Priya → Forms & approvals |
| New staff (Marcus) don't know who to send requests to | Routing comes from the rules, so the form shows the exact approval route before submitting. Nobody has to know the process. | New request → Approval route panel |
| Customer purchase orders get mixed up with enquiries and pending MDM setup | A customer inbox auto-tags each inbound message as a purchase order or an enquiry (keyword rules in this prototype) and picks out products and quantities. It flags senders not yet in SAP B1, and "Start customer setup" pre-fills an MDM request linked to the order. | Marcus → Customer inbox → MSG-208 |
| Internal and external parties talk in scattered email | Each request has one conversation thread. Staff choose per message between an internal note and a reply shared with the customer or vendor. External parties get their own portal view with plain-language status and only the shared messages. | Switch to Hana → MDM-1039 |

## Suggested demo script (2–3 minutes)

1. **Amy**: start a Customer request, type "Natl University Hosp" and show the duplicate block. Switch to Item to show different required fields.
2. **Marcus → Customer inbox → MSG-208**: the PO is auto-tagged and the customer is flagged as not in SAP B1. Click Start customer setup and submit.
3. **Daniel**, then **Wei Jie**: approve from "Waiting on you". Wei Jie reveals the credit terms and the audit trail records it.
4. **Hana** (external): sees only the shared question on MDM-1039 and replies.
5. **Priya**: create the record in SAP B1. Then open Forms & approvals and add a "Cold-chain storage temp" field to Item.

## Not in this prototype (deliberately)

- Real SAP B1 integration. Records are mirrored and "Create in SAP B1" is simulated. In production this would be the SAP B1 Service Layer API or a DI API import file for the MDM team.
- Real Teams/Outlook notifications and sign-in. In production these would be Microsoft 365 (Entra ID sign-in, Teams adaptive cards).
- The regional business view and forecasting deliverable. It can be added as another tab that reads the purchase-order tags from the customer inbox.
- An AI classifier for inbound messages. Keyword rules stand in for it here.
