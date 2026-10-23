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
| Forecasts are rolling 6–12 month averages compiled by hand, missing seasonality, cross-sell and drop-off | **Regional view** tab: units and growth for Products A/B/C × 5 countries, a calendar-aware forecast backtested against today's averages, a drop-off call list and a cross-sell call list. | Any staff persona → Regional view |
| Duplicate records distort the regional picture | The same matcher as the request form merges duplicate customer records before analysis. A **Before / After cleanup** switch on the drop-off call list shows 18 alerts shrink to 10: the 8 removed customers never left, they were ordering under a second record. | Regional view → Call list → Before cleanup, then After cleanup |
| Nobody knows when a request will finish, or who is holding it up | Every open request shows an **expected date in SAP B1**, worked out from how long each approver usually takes (demo history), and flags a **bottleneck** when someone is past their usual time. The new request form shows the expected date before you submit. | MDM-1041 (Daniel is the bottleneck); New request → Approval route |
| Slow setup costs sales, not just admin time | **Stuck orders counter**: purchase orders from customers not yet in SAP B1, valued from the quantities in the PO. Approvers see "SGD 16.8k of orders are waiting on this" on the linked setup request. | All requests (top); MSG-208 → Start customer setup → approve as Daniel |
| A duplicate looks harmless at intake | The duplicate warning shows the existing customer's **order history** (12-month value, products, customer since) and says what a second record would split. SAP B1 records shows 12-month orders per customer. | New request → type "Natl University Hosp" |
| Approvers don't see requests; staff fall back to email | **Teams card** (simulated): every time a request reaches someone, a Teams-style card pops up with the key facts and Approve / Ask for info / Open in hub. Restricted fields are never put on the card. Approving from the card moves the request on and the next card appears, ending with "Live in SAP B1" sent to the requester. | Any request → Nudge, or submit a new one |
| How does a record actually reach SAP B1? | **SAP B1 handoff**: when MDM creates a record, the hub builds the SAP B1 Service Layer request (`POST /b1s/v1/BusinessPartners`, `Items` or `ProfitCenters`) with the approval trail attached, downloadable as JSON or as a CSV for SAP's Data Transfer Workbench. Codes SAP B1 needs (payment terms, item group, bank) are listed as lookups. Only Finance and MDM can download it. | Any request "In SAP B1" (e.g. MDM-1036) |
| Requestors write free-text emails | **Start from an email**: paste the email and the form fills itself, marking which fields came from the email and what is still missing. Three example emails are pre-extracted (as an LLM would return them); other text uses simple pattern rules so it works offline with no API key. | New request → Start from an email → "Sales: new hospital lab account" |
| Names miss some duplicates | **Tax-ID check**: an exact tax or registration number match is flagged even when names differ (catches "NUH" for National University Hospital). | New request → Customer → tax no. 201801141754 |
| "How fast would it really be?" | **Amy: email vs hub**: the brief's day-in-the-life played side by side. Email: 18 days and still not in SAP B1. Hub: about 6 days, timed with each approver's usual response. | Amy: email vs hub → Play |
| Is the business case real? | **Business case calculator** in the Regional view: sliders for conversion, win-back, margin, setup days, request volume, minutes saved, staff cost, build and running cost. Net value and payback update live. | Regional view → Business case |
| Customer purchase orders get mixed up with enquiries and pending MDM setup | A customer inbox auto-tags each inbound message as a purchase order or an enquiry (keyword rules in this prototype) and picks out products and quantities. It flags senders not yet in SAP B1, and "Start customer setup" pre-fills an MDM request linked to the order. | Marcus → Customer inbox → MSG-208 |
| Internal and external parties talk in scattered email | Each request has one conversation thread. Staff choose per message between an internal note and a reply shared with the customer or vendor. External parties get their own portal view with plain-language status and only the shared messages. | Switch to Hana → MDM-1039 |

## Suggested demo script (2–3 minutes)

Aim for one surprise roughly every 30 seconds.

0. **Open on "Amy: email vs hub"** and press Play (about 8 seconds): 18 days by email vs 6 in the hub.

1. **Marcus → New request → Start from an email**, pick "Sales: new hospital lab account", Fill the form. Fields light up as filled from the email, and the duplicate check fires on the tax ID: this customer already exists and ordered SGD 30.7k last year. (Alternative: as Amy, type "Natl University Hosp".) The duplicate block shows the existing customer ordered SGD 94.6k last year, and why a second record would hurt. Point at the expected finish date in the route panel. Switch to Item to show different required fields.
2. **Marcus → Customer inbox → MSG-208**: the PO is auto-tagged and the customer is flagged as not in SAP B1. Click Start customer setup and submit.
3. **All requests**: the red "SGD 16.8k stuck" banner. Open MDM-1041 to show the bottleneck warning on Daniel.
4. **Teams**: submit the Bangkok setup from MSG-208 and approve it straight from the Teams cards (Daniel, Wei Jie, Grace, Priya), one click each. The card says "SGD 16.8k of customer orders waiting on this".
5. **Hana** (external): sees only the shared question on MDM-1039 and replies.
6. **Priya**: open the created request. The SAP B1 handoff panel shows the Service Layer payload; download it. The stuck banner on All requests has cleared. Then open Forms & approvals and add a "Cold-chain storage temp" field to Item.
7. **Regional view**: point at Malaysia (red) and Vietnam B (+70%). Click Malaysia × Product A and hover Feb '26: the 6-month average expected 914 units during Chinese New Year, the model 618, actual 515. Then go to the drop-off call list, click **Before cleanup** (18 accounts, SGD 1.97M "at risk"), then **After cleanup**: 8 alerts cross out because those customers never left. Finish on the business case sliders: drag cross-sell conversion and watch payback move.

## Regional view and the analytics pipeline

The brief ships no data, so `analytics/` builds a simulated history and analyses it. Everything in the Regional view tab comes from there.

| File | What it does |
|---|---|
| `analytics/generate_data.py` | 168 customer accounts saved as 198 SAP B1 records (30 planted duplicates), monthly orders Jan 2023 – Sep 2026 for Products A/B/C in 5 countries, with CNY/Tet, Raya, Songkran, Holy Week and budget-cycle effects, a Malaysian drop-off, Vietnamese Product B growth, plus monthly purchase orders vs enquiries vs MDM setup requests. Writes `analytics/data/*.csv`. `ground_truth.json` records what was planted, used only to score the results. |
| `analytics/analyze.py` | Duplicate matching (same name algorithm as the request form, plus an exact tax-ID pass; 30 of 30 planted duplicates found, 0 wrong merges), growth, forecast backtest (6- and 12-month average vs Holt-Winters vs a gradient-boosted model with each country's calendar), drop-off and cross-sell lists computed before and after merging duplicates. Writes `analytics/regional.json`. |
| `analytics/build.py` | Runs both, then injects `regional.json` into `app.html` and rebuilds `index.html`. |

```sh
pip install pandas numpy scikit-learn statsmodels
python3 analytics/build.py            # full refresh, about 40 seconds
python3 analytics/build.py --inject   # after editing app.html: re-inject data and rebuild index.html
```

Edit `app.html`, then run `--inject` (it replaces the index.html one-liner above). Don't edit the `REGIONAL_DATA` line by hand.

Definitions used in the view:
- **Growth**: units ordered Oct 2025 – Sep 2026 vs the same 12 months a year earlier. Same-month comparison cancels holidays and budget cycles.
- **Forecast miss**: units missed as a share of units ordered (WAPE), over 12 one-month-ahead forecasts (Oct 2025 – Sep 2026) for each of 15 country-product series, each made only with earlier data.
- **Drop-off**: last 3 months' average below half the account's monthly average a year earlier (accounts buying at least SGD 1.5k a month).
- **Cross-sell gap**: at least half of similar customers (same segment, buying everything this account buys) also buy the missing product.

## Not in this prototype (deliberately)

- Real SAP B1 integration. Records are mirrored and "Create in SAP B1" is simulated. In production this would be the SAP B1 Service Layer API or a DI API import file for the MDM team.
- Real Teams/Outlook notifications and sign-in. In production these would be Microsoft 365 (Entra ID sign-in, Teams adaptive cards).
- An AI classifier for inbound messages. Keyword rules stand in for it here.
- A live LLM for email intake. Three examples are pre-extracted; production would call an LLM inside Microsoft 365 (e.g. Azure OpenAI) and return the same field JSON. No API key ships in the page.
- Real Teams cards and Service Layer posting. Both are simulated in the browser; production uses Power Automate (adaptive cards in Teams, HTTP action to the Service Layer).
- A live SAP B1 feed for the regional view. In production, order history would be exported nightly (Service Layer or a saved query) to SharePoint and the Python job run monthly, with results in this tab or Power BI.
