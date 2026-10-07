import os, sys, json, uuid, io
os.environ.update(SECRET_KEY="test-secret-key-123456", SUPABASE_URL="https://x.supabase.co",
                  SUPABASE_SECRET_KEY="k", SITE_URL="http://localhost", SESSION_COOKIE_SECURE="false")
sys.path.insert(0, ".")
import app as A

# ---------------- fake DB ----------------
DB = {}
def _m(r, f): return all(str(r.get(k)) == str(v) for k, v in (f or {}).items())
def f_select(t, filters=None, select="*", order=None, limit=None):
    rows = [dict(r) for r in DB.get(t, []) if _m(r, filters)]
    if order:
        col, _, d = order.partition(".")
        rows.sort(key=lambda r: (r.get(col) is None, str(r.get(col) if r.get(col) is not None else "")), reverse=(d == "desc"))
    return rows[: (limit or 10**6)]
def f_insert(t, p, returning="representation"):
    row = json.loads(json.dumps(p, default=str)); row.setdefault("id", str(uuid.uuid4()))   # DB assigns ids like Supabase
    DB.setdefault(t, []).append(row); return dict(row), None
def f_update(t, f, p):
    hit = []
    for r in DB.get(t, []):
        if _m(r, f): r.update(json.loads(json.dumps(p, default=str))); hit.append(dict(r))
    return hit, None
def f_delete(t, f): DB[t] = [r for r in DB.get(t, []) if not _m(r, f)]; return True, None
def f_first(t, f): rows = f_select(t, f, limit=1); return rows[0] if rows else None
A.db_select, A.db_insert, A.db_update, A.db_delete, A.first_row = f_select, f_insert, f_update, f_delete, f_first

NOTES, ACCT = [], []
A._b2bv4_notify = lambda uid, title, body, link="/b2b": NOTES.append((str(uid), title, body, link))
A._b2bv4_event = lambda *a, **k: None
A._r_audit = lambda *a, **k: None
A._post_simple_accounting_entry = lambda *a, **k: ACCT.append((a, k)) or "tx1"
A.upload_storage = lambda f, folder="x", public=False, max_mb=None, allowed=None: ({"url": "https://cdn.example.com/logo.png", "path": "p"}, None)
_real_get = A.requests.get
A.requests.get = lambda url, **kw: (_ for _ in ()).throw(A.requests.exceptions.ConnectionError("offline"))

# ---------------- people ----------------
def user(i, **kw): return dict({"id": "u-" + i, "full_name": i, "email": i + "@t.com", "role": "student", "is_admin": False, "is_active": True}, **kw)
U1, U2, U3, ADM = user("owner1"), user("owner2"), user("investor"), user("admin", is_admin=True, role="admin")
WHO = {"u": U1}
A.current_user = lambda: WHO["u"]
B1, B2, B3 = "b1-" + uuid.uuid4().hex[:8], "b2-" + uuid.uuid4().hex[:8], "b3-" + uuid.uuid4().hex[:8]
DB["koja_businesses"] = [
    {"id": B1, "owner_id": U1["id"], "name": "Zambezi Steel", "category": "Industrial", "location": "Kitwe", "phone": "0977", "business_number": "KJ-BIZ-2026-AAAA1111", "created_at": "2026-01-01"},
    {"id": B2, "owner_id": U2["id"], "name": "Copperbelt Foods", "category": "Food", "location": "Ndola", "phone": "0966", "business_number": "KJ-BIZ-2026-BBBB2222", "created_at": "2026-01-02"},
    {"id": B3, "owner_id": U1["id"], "name": "Owner1 Side Biz", "category": "Misc", "location": "Lusaka", "phone": "0955", "business_number": "KJ-BIZ-2026-CCCC3333", "created_at": "2026-01-03"}]

A.app.config["TESTING"] = True; A.app.config["PROPAGATE_EXCEPTIONS"] = False
c = A.app.test_client()
with c.session_transaction() as s: s["_csrf_token"] = "tok"
H = {"X-CSRF-Token": "tok"}
res = []
def ok(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, ("" if cond else "   " + str(extra)[:300])); res.append(bool(cond)); return cond
def post(url, data=None, **kw): d = dict(data or {}); d["_csrf_token"] = "tok"; return c.post(url, data=d, **kw)
def postj(url, body=None): return c.post(url, json=body or {}, headers=H)
def as_(u): WHO["u"] = u

# =============== industries & directory ===============
r = c.get("/industries"); ok("industries hub lists all 10", r.status_code == 200 and all(n.encode() in r.data for n in ["Manufacturing", "Mining", "Agriculture", "Construction", "Energy", "Transport", "Technology", "Finance", "Healthcare", "Media"]))
DB["koja_business_directory"] = [{"id": "L1", "public_name": "Legacy Co", "description": "old listing", "location": "Lusaka", "category": "Retail", "active": True, "updated_at": "2025-01-01"}]
r = c.get("/business-directory"); ok("directory still shows legacy listings", r.status_code == 200 and b"Legacy Co" in r.data)
as_(U1); r = c.get(f"/business/{B1}/hub"); ok("hub renders (all linked endpoints resolve)", r.status_code == 200 and b"Business Hub" in r.data and b"Fundraising" in r.data, r.status_code)
as_(U2); ok("hub is owner-only", c.get(f"/business/{B1}/hub").status_code == 404)
as_(U1); r = c.get(f"/business/{B1}"); ok("dashboard has Business Hub button", r.status_code == 200 and b"Business Hub" in r.data, r.status_code)

# =============== profile ===============
ok("publish without enough info refused", (post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "publish": "on"}), not DB.get("koja_business_profiles"))[1])
ok("bad website rejected", (post(f"/business/{B1}/profile", {"public_name": "Z", "website": "javascript:alert(1)"}), not DB.get("koja_business_profiles"))[1])
DESC = "We make structural steel and fabricate beams for mines. <script>alert(1)</script> Quality assured."
post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "tagline": "Steel for Africa", "industry": "manufacturing", "location": "Kitwe", "country": "Zambia", "description": DESC,
     "website": "zambezisteel.example.com", "contact_email": "info@zs.example.com", "show_catalogue": "on", "accepts_rfq": "on", "publish": "on", "year_founded": "1999", "employee_range": "51-200"})
p1 = (DB.get("koja_business_profiles") or [{}])[0]
ok("profile published with slug + https website", p1.get("status") == "published" and p1.get("slug") == "zambezi-steel" and p1.get("website", "").startswith("https://"), p1)
as_(U2)
post(f"/business/{B2}/profile", {"public_name": "Copperbelt Foods", "industry": "agriculture", "location": "Ndola", "description": "Food processing and distribution across the Copperbelt region.", "accepts_rfq": "on", "publish": "on"})
p2 = DB["koja_business_profiles"][1]
ok("second company published", p2["status"] == "published")
as_(None)
r = c.get("/companies/zambezi-steel"); ok("anonymous can view public profile", r.status_code == 200 and b"Zambezi Steel" in r.data)
ok("XSS in description is escaped", b"<script>alert(1)</script>" not in r.data and b"&lt;script&gt;" in r.data)
p1["status"] = "draft"; ok("draft hidden from public", c.get("/companies/zambezi-steel").status_code == 404)
as_(U1); ok("draft visible to owner as preview", c.get("/companies/zambezi-steel").status_code == 200); p1["status"] = "published"

# =============== directory search / filters / verified ===============
as_(None)
r = c.get("/business-directory?industry=manufacturing"); ok("industry filter includes match", b"Zambezi Steel" in r.data and b"Copperbelt Foods" not in r.data)
r = c.get("/business-directory?industry=mining"); ok("industry filter excludes others", b"Zambezi Steel" not in r.data)
r = c.get("/business-directory?q=beams"); ok("text search finds description match", b"Zambezi Steel" in r.data)
r = c.get("/business-directory?location=ndola"); ok("location filter", b"Copperbelt Foods" in r.data and b"Zambezi Steel" not in r.data)
r = c.get("/business-directory?verified=1"); ok("verified filter empty before verification", b"Zambezi Steel" not in r.data)
DB["koja_business_verifications_v2"] = [{"business_id": B1, "status": "approved"}]
r = c.get("/business-directory?verified=1"); ok("verified filter shows verified company", b"Zambezi Steel" in r.data and b"Verified" in r.data)
r = c.get("/industries/manufacturing"); ok("industry page lists company", r.status_code == 200 and b"Zambezi Steel" in r.data); ok("unknown industry 404", c.get("/industries/nope").status_code == 404)

# =============== compare + catalogue privacy ===============
DB["koja_business_products"] = [{"id": "p1", "business_id": B1, "name": "Steel Beam 6m", "sku": "SB6", "selling_price": 100, "cost_price": 37.37, "stock": 50, "product_type": "physical", "delivery_available": True, "created_at": "2026-01-01"},
                                {"id": "p2", "business_id": B1, "name": "Digital Catalogue", "sku": "DC", "selling_price": 5, "cost_price": 0, "stock": 0, "product_type": "digital", "created_at": "2026-01-02"},
                                {"id": "px", "business_id": B2, "name": "Maize Meal 25kg", "sku": "MM", "selling_price": 250, "cost_price": 180, "stock": 20, "product_type": "physical", "created_at": "2026-01-01"}]
r = c.get("/companies/zambezi-steel"); ok("catalogue shown when enabled; cost price never exposed", b"Steel Beam 6m" in r.data and b"37.37" not in r.data)
r = c.get("/companies/copperbelt-foods"); ok("catalogue hidden when not enabled", b"Maize Meal" not in r.data)
r = c.get("/compare?s=zambezi-steel,copperbelt-foods"); ok("compare shows both companies", r.status_code == 200 and b"Zambezi Steel" in r.data and b"Copperbelt Foods" in r.data and b"Not shared" in r.data)
r = c.get("/compare?s=zambezi-steel"); ok("compare needs 2+", b"at least two" in r.data)
p2["status"] = "draft"; r = c.get("/compare?s=zambezi-steel,copperbelt-foods"); ok("compare ignores unpublished", b"Copperbelt Foods" not in r.data); p2["status"] = "published"

# =============== services & pricing ===============
as_(U1)
post(f"/business/{B1}/services", {"action": "add", "name": "Site Installation", "pricing_model": "hourly", "price": "350", "currency": "zmw", "description": "Crane + crew"})
post(f"/business/{B1}/services", {"action": "add", "name": "Custom Design", "pricing_model": "quote"})
svc = DB["koja_business_services"]; ok("services added (currency normalised)", len(svc) == 2 and svc[0]["currency"] == "ZMW")
post(f"/business/{B1}/services", {"action": "toggle", "id": svc[1]["id"]})
r = c.get("/companies/zambezi-steel"); ok("hidden service not public; active one is", b"Site Installation" in r.data and b"Custom Design" not in r.data)
as_(U2); post(f"/business/{B1}/services", {"action": "delete", "id": svc[0]["id"]}); ok("non-owner cannot delete services", len(DB["koja_business_services"]) == 2)
as_(U1)
post(f"/business/{B1}/pricing", {"action": "add", "product_id": "p1", "min_qty": "1", "unit_price": "90"}); n0 = len(DB.get("koja_business_price_tiers", []))
post(f"/business/{B1}/pricing", {"action": "add", "product_id": "p1", "min_qty": "10", "unit_price": "150"})
ok("tier rejected: min qty <2, price above base", n0 == 0 and not DB.get("koja_business_price_tiers"))
post(f"/business/{B1}/pricing", {"action": "add", "product_id": "px", "min_qty": "10", "unit_price": "10"}); ok("tier rejected for another business's product", not DB.get("koja_business_price_tiers"))
post(f"/business/{B1}/pricing", {"action": "add", "product_id": "p1", "min_qty": "10", "unit_price": "80", "label": "Wholesale"})
post(f"/business/{B1}/pricing", {"action": "add", "product_id": "p1", "min_qty": "50", "unit_price": "70"})
tiers = DB["koja_business_price_tiers"]; prod = DB["koja_business_products"][0]
ok("tier picks: 5->100, 10->80, 49->80, 50->70", [A._bh_unit_price(prod, q, tiers) for q in (5, 10, 49, 50)] == [100.0, 80.0, 80.0, 70.0])
r = c.get("/companies/zambezi-steel"); ok("public page shows volume pricing", b"Wholesale" in r.data)

# =============== inventory ===============
post(f"/business/{B1}/inventory", {"product_id": "p1", "mode": "add", "qty": "5", "reason": "received"}); ok("stock add", DB["koja_business_products"][0]["stock"] == 55)
post(f"/business/{B1}/inventory", {"product_id": "p1", "mode": "remove", "qty": "5", "reason": "damaged"}); ok("stock remove", DB["koja_business_products"][0]["stock"] == 50)
post(f"/business/{B1}/inventory", {"product_id": "p1", "mode": "remove", "qty": "999", "reason": "damaged"}); ok("cannot remove below zero", DB["koja_business_products"][0]["stock"] == 50)
post(f"/business/{B1}/inventory", {"product_id": "p1", "mode": "set", "qty": "40", "reason": "correction"}); ok("stock take (set to 40)", DB["koja_business_products"][0]["stock"] == 40)
mv = DB["koja_business_stock_movements"]; ok("movement log is signed and typed", [m["quantity"] for m in mv] == [5, -5, -10] and mv[2]["movement_type"] == "adjustment_correction", mv)
as_(U2); post(f"/business/{B1}/inventory", {"product_id": "p1", "mode": "add", "qty": "100", "reason": "received"}); ok("non-owner cannot adjust stock", DB["koja_business_products"][0]["stock"] == 40); as_(U1)
r = c.get(f"/business/{B1}/inventory?low=50"); ok("inventory page + low-stock flag", r.status_code == 200 and b"Low" in r.data)
# race: first read is stale, compare-and-set must fail and retry, never overwrite
stale = {"n": 0}; real_first = A.first_row
def racy(t, f):
    row = real_first(t, f)
    if t == "koja_business_products" and f.get("id") == "p1" and stale["n"] == 0:
        stale["n"] = 1; row = dict(row, stock=row["stock"] + 7)      # stale read
    return row
A.first_row = racy; DB["koja_business_products"][0]["stock"] = 40
new, err = A._bh_stock_apply(B1, "p1", -3, "pos_sale", "race"); A.first_row = real_first
ok("stock CAS: stale read retried, no lost update", err is None and new == 37 and DB["koja_business_products"][0]["stock"] == 37, (new, err))

# =============== POS ===============
DB["koja_business_products"][0]["stock"] = 40
def checkout(items, **kw): return postj(f"/business/{B1}/pos/checkout", dict({"items": items, "payment_method": "cash"}, **kw))
r = checkout([{"kind": "product", "id": "p1", "qty": 12, "price": 0.01}], tendered="1000", customer_name="Mr Banda"); j = r.get_json()
ok("POS sale: server prices (tier 80) not client price", r.status_code == 200 and j["total"] == 960.0 and j["change"] == 40.0, j)
ok("stock reduced + movement logged", DB["koja_business_products"][0]["stock"] == 28 and DB["koja_business_stock_movements"][-1]["movement_type"] == "pos_sale")
rc = DB["koja_business_pos_receipts"][0]; ok("receipt stored with lines", rc["total"] == 960.0 and rc["lines"][0]["unit_price"] == 80.0 and rc["status"] == "completed" and rc["customer_name"] == "Mr Banda")
sale = DB["koja_business_sales"][0]; ok("sale ledger row + items for BI", sale["total_amount"] == 960.0 and sale["receipt_number"] == rc["receipt_number"] and DB["koja_business_sale_items"][0]["cost_price"] == 37.37)
ok("accounting posted once with total", len(ACCT) == 1 and ACCT[0][0][2] == 960.0 and ACCT[0][0][1] == "sale", ACCT)
r = c.get(j["receipt_url"]); ok("receipt page renders", r.status_code == 200 and rc["receipt_number"].encode() in r.data and b"960.00" in r.data)
as_(U2); ok("receipt is owner-only", c.get(j["receipt_url"]).status_code == 404); as_(U1)
r = checkout([{"kind": "product", "id": "p1", "qty": 99}]); ok("oversell refused (409), stock untouched", r.status_code == 409 and DB["koja_business_products"][0]["stock"] == 28, r.get_json())
ok("failed sale receipt marked void, no sale row, no accounting", DB["koja_business_pos_receipts"][-1]["status"] == "void" and len(DB["koja_business_sales"]) == 1 and len(ACCT) == 1)
DB["koja_business_products"].append({"id": "p3", "business_id": B1, "name": "Bolts", "selling_price": 2, "cost_price": 1, "stock": 3, "product_type": "physical"})
r = checkout([{"kind": "product", "id": "p1", "qty": 5}, {"kind": "product", "id": "p3", "qty": 10}])
ok("multi-line failure rolls back the first line", r.status_code == 409 and DB["koja_business_products"][0]["stock"] == 28 and DB["koja_business_stock_movements"][-1]["movement_type"] == "pos_void", (r.get_json(), DB["koja_business_products"][0]["stock"]))
r = checkout([{"kind": "product", "id": "px", "qty": 1}]); ok("cannot sell another business's product", r.status_code == 400)
r = checkout([{"kind": "product", "id": "p3", "qty": 1}], discount="9999"); ok("discount capped at subtotal -> free sale ok", r.status_code == 200 and r.get_json()["total"] == 0.0)
r = checkout([{"kind": "product", "id": "p1", "qty": 1}], tendered="10"); ok("cash tendered below total refused", r.status_code == 400)
r = checkout([{"kind": "service", "id": DB["koja_business_services"][1]["id"], "qty": 1}]); ok("quote-only service cannot be sold at POS", r.status_code == 400)
r = checkout([{"kind": "service", "id": DB["koja_business_services"][0]["id"], "qty": 3}], payment_method="mobile_money"); ok("fixed/hourly service sells without stock (3 x 350)", r.status_code == 200 and r.get_json()["total"] == 1050.0, r.get_json())
r = checkout([]); ok("empty cart refused", r.status_code == 400); r = checkout([{"kind": "product", "id": "p1", "qty": -2}]); ok("negative qty refused", r.status_code == 400)
DB["koja_business_products"].append({"id": "p4", "business_id": B1, "name": "Widget", "selling_price": 19.99, "cost_price": 5, "stock": 100, "product_type": "physical"})
r = checkout([{"kind": "product", "id": "p4", "qty": 3}]); ok("decimal-safe money (19.99 x 3 = 59.97)", r.get_json()["total"] == 59.97, r.get_json())
as_(U2); ok("non-owner cannot checkout", postj(f"/business/{B1}/pos/checkout", {"items": [{"kind": "product", "id": "p1", "qty": 1}]}).status_code == 404); as_(U1)
ok("POS checkout needs CSRF token", c.post(f"/business/{B1}/pos/checkout", json={"items": []}).status_code in (400, 403))
r = c.get(f"/business/{B1}/pos"); ok("POS page renders with products", r.status_code == 200 and b"Steel Beam 6m" in r.data)

# =============== RFQ board + directed RFQ ===============
as_(U2)
r = post("/companies/zambezi-steel/rfq", {"buyer_business_id": B2, "title": "50 beams for warehouse", "description": "Need 50 x 6m beams delivered to Ndola by month end.", "budget": "5000", "currency": "ZMW", "request_type": "product", "deadline": "2026-12-01"})
rq = DB["koja_b2b_unified_requests"][0]; ok("directed RFQ creates an open request tagged with industry", rq["status"] == "open" and rq["category"] == "Manufacturing" and rq["buyer_business_id"] == B2)
ok("target recorded + owner notified", DB["koja_connectplus_rfq_targets"][0]["target_business_id"] == B1 and any(n[0] == U1["id"] and "quote" in n[1].lower() for n in NOTES), NOTES)
post("/companies/zambezi-steel/rfq", {"buyer_business_id": B1, "title": "x", "description": "y"}); ok("cannot RFQ with a business you don't own", len(DB["koja_b2b_unified_requests"]) == 1)
as_(U1); n_rq = len(DB["koja_b2b_unified_requests"]); post("/companies/zambezi-steel/rfq", {"buyer_business_id": B1, "title": "Self", "description": "own company"})
ok("cannot RFQ your own company from itself", len(DB["koja_b2b_unified_requests"]) == n_rq)
r = c.get("/business/connect-plus/rfqs"); ok("supplier sees RFQ marked 'Sent to you'", r.status_code == 200 and b"50 beams for warehouse" in r.data and b"Sent to you" in r.data)
as_(U2); r = c.get("/business/connect-plus/rfqs"); ok("buyer's own RFQ excluded from board", b"50 beams for warehouse" not in r.data)
as_(U3); DB["koja_businesses"].append({"id": "b9", "owner_id": U3["id"], "name": "Other", "business_number": "KJ-BIZ-2026-DDDD4444", "created_at": "x"})
r = c.get("/business/connect-plus/rfqs"); ok("third party sees it without 'Sent to you'", b"50 beams for warehouse" in r.data and b"Sent to you" not in r.data)
r = c.get("/business/connect-plus/rfqs?industry=mining"); ok("board industry filter", b"50 beams" not in r.data)
r = c.get("/business/connect-plus/rfqs?q=warehouse&type=product"); ok("board keyword + type filter", b"50 beams" in r.data)
p1["accepts_rfq"] = False; as_(U2); ok("company not accepting RFQs -> 404", c.get("/companies/zambezi-steel/rfq").status_code == 404); p1["accepts_rfq"] = True

# =============== contracts ===============
as_(U1)
post(f"/business/{B1}/contracts/new", {"counterparty_number": "KJ-BIZ-2026-NOPE0000", "title": "T", "terms": "x" * 30}); ok("unknown counterparty refused", not DB.get("koja_connectplus_contracts"))
post(f"/business/{B1}/contracts/new", {"counterparty_number": "KJ-BIZ-2026-AAAA1111", "title": "T", "terms": "x" * 30}); ok("cannot contract with yourself", not DB.get("koja_connectplus_contracts"))
post(f"/business/{B1}/contracts/new", {"counterparty_number": "kj-biz-2026-bbbb2222", "title": "Supply of beams", "terms": "Supplier delivers 50 beams within 30 days of payment. " * 2, "value": "5000", "currency": "ZMW", "start_date": "2026-11-01", "end_date": "2027-01-01"})
ct = DB["koja_connectplus_contracts"][0]; cid = ct["id"]; ok("draft contract created", ct["status"] == "draft" and ct["party_b_business_id"] == B2 and not ct.get("terms_hash"))
as_(U2); ok("draft invisible to the other party", c.get(f"/business/contracts/{cid}").status_code == 404)
as_(U3); ok("outsider cannot view contract", c.get(f"/business/contracts/{cid}").status_code == 404); ok("outsider cannot act on contract", post(f"/business/contracts/{cid}/send").status_code == 404 and ct["status"] == "draft")
as_(U1); post(f"/business/contracts/{cid}/send"); ok("send fixes terms fingerprint", ct["status"] == "sent" and len(ct["terms_hash"]) == 64 and ct["terms_hash"] == A._bh_contract_hash(ct))
ok("counterparty notified", any(n[0] == U2["id"] and "contract" in n[2].lower() for n in NOTES))
post(f"/business/contracts/{cid}/accept", {"authorised": "1"}); ok("sender cannot accept own contract", ct["status"] == "sent")
as_(U2); r = c.get(f"/business/contracts/{cid}"); ok("recipient sees sent contract", r.status_code == 200 and b"Supply of beams" in r.data and b"Terms unchanged" in r.data)
post(f"/business/contracts/{cid}/accept"); ok("accept needs authority confirmation", ct["status"] == "sent")
post(f"/business/contracts/{cid}/accept", {"authorised": "1"}); ok("accept -> active with signer + time", ct["status"] == "active" and ct["accepted_by"] == U2["id"] and ct["accepted_at"])
post(f"/business/contracts/{cid}/terminate"); ok("terminate needs a reason", ct["status"] == "active")
post(f"/business/contracts/{cid}/terminate", {"reason": "Supplier defaulted"}); ok("terminate with reason", ct["status"] == "terminated" and ct["closed_reason"] == "Supplier defaulted")
post(f"/business/contracts/{cid}/accept", {"authorised": "1"}); ok("closed contract cannot be re-accepted", ct["status"] == "terminated")
as_(U1)
post(f"/business/{B1}/contracts/new", {"counterparty_number": "KJ-BIZ-2026-BBBB2222", "title": "Tamper test", "terms": "Original terms that are long enough."}); c2 = DB["koja_connectplus_contracts"][1]
post(f"/business/contracts/{c2['id']}/send"); c2["terms"] = "SNEAKY changed terms after sending, long enough."
as_(U2); r = c.get(f"/business/contracts/{c2['id']}"); ok("tampered terms flagged in the UI", b"differ from the sent version" in r.data)
post(f"/business/contracts/{c2['id']}/accept", {"authorised": "1"}); ok("tampered contract cannot be accepted", c2["status"] == "sent")
as_(U1); r = c.get(f"/business/{B1}/contracts"); ok("contract list renders", r.status_code == 200 and b"Supply of beams" in r.data)
as_(U2); post(f"/business/contracts/{c2['id']}/reject"); ok("recipient can reject", c2["status"] == "rejected")

# =============== partnerships ===============
as_(U1); post(f"/business/{B1}/partnerships", {"partner_number": "KJ-BIZ-2026-BBBB2222", "partnership_type": "supplier", "message": "Let's partner"})
pt = DB["koja_connectplus_partnerships"][0]; ok("partnership proposed", pt["status"] == "proposed" and pt["partnership_type"] == "supplier")
post(f"/business/{B1}/partnerships", {"partner_number": "KJ-BIZ-2026-BBBB2222", "partnership_type": "reseller"}); ok("duplicate proposal blocked", len(DB["koja_connectplus_partnerships"]) == 1)
post(f"/business/partnerships/{pt['id']}/accept"); ok("proposer cannot accept their own proposal", pt["status"] == "proposed")
as_(U3); post(f"/business/partnerships/{pt['id']}/accept"); ok("outsider cannot accept", pt["status"] == "proposed")
as_(U2); post(f"/business/partnerships/{pt['id']}/accept"); ok("partner accepts", pt["status"] == "accepted")
r = c.get("/companies/zambezi-steel"); ok("accepted partner shown on public profile", b"Copperbelt Foods" in r.data)
as_(U2); post(f"/business/partnerships/{pt['id']}/end"); ok("either side can end", pt["status"] == "ended")
as_(U2); post("/companies/zambezi-steel/partner", {"business_id": B2, "partnership_type": "referral", "message": "again"}); ok("re-propose from company page after ended", len(DB["koja_connectplus_partnerships"]) == 2)

# =============== investors ===============
as_(U3); r = post("/business/connect-plus/investor/register", {"display_name": "Ngoma Capital", "contact_email": "inv@ngoma.example.com", "ticket_min": "10000", "ticket_max": "50000", "industries": ["manufacturing"]}); ok("declaration required", not DB.get("koja_connectplus_investor_profiles"))
post("/business/connect-plus/investor/register", {"display_name": "Ngoma Capital", "contact_email": "inv@ngoma.example.com", "ticket_min": "50000", "ticket_max": "10000", "declaration": "1"}); ok("ticket range validated", not DB.get("koja_connectplus_investor_profiles"))
post("/business/connect-plus/investor/register", {"display_name": "Ngoma Capital", "contact_email": "inv@ngoma.example.com", "ticket_min": "10000", "ticket_max": "50000", "industries": ["manufacturing", "bogus"], "declaration": "1"})
ip = DB["koja_connectplus_investor_profiles"][0]; ok("investor registers as pending, bogus industry dropped", ip["status"] == "pending" and ip["industries"] == ["manufacturing"])
r = c.get("/business/connect-plus/investments"); ok("pending investor cannot browse", r.status_code == 302)
as_(U1); post(f"/business/{B1}/fundraising", {"title": "Expand plant", "summary": "Short", "amount_sought": "100000"}); ok("short summary refused", not DB.get("koja_connectplus_investment_listings"))
post(f"/business/{B1}/fundraising", {"title": "Expand plant", "summary": "Zambezi Steel is expanding its Kitwe plant to double output and serve new mining contracts across the region.", "amount_sought": "100000", "currency": "usd", "instrument": "equity", "use_of_funds": "New rolling mill"})
ls = DB["koja_connectplus_investment_listings"][0]; ok("listing created pending (not public)", ls["status"] == "pending" and ls["currency"] == "USD" and ls["industry"] == "manufacturing")
as_(U3); ok("investor cannot express interest in unapproved listing", post(f"/business/connect-plus/investments/{ls['id']}/interest", {"message": "hi"}).status_code in (302, 404) and not DB.get("koja_connectplus_investor_interests"))
as_(U1); ok("non-admin cannot reach moderation", c.get("/admin/business-hub").status_code == 302 and post("/admin/business-hub/action", {"kind": "investor", "id": ip["id"], "action": "approve"}).status_code == 302 and ip["status"] == "pending")
as_(ADM); r = c.get("/admin/business-hub"); ok("admin console renders pending items", r.status_code == 200 and b"Ngoma Capital" in r.data and b"Expand plant" in r.data and b"(verified)" in r.data, (r.status_code, [t for t in (b"Ngoma Capital", b"Expand plant", b"(verified)") if t not in r.data], r.data[:200] if r.status_code != 200 else ""))
post("/admin/business-hub/action", {"kind": "investor", "id": ip["id"], "action": "approve"}); post("/admin/business-hub/action", {"kind": "listing", "id": ls["id"], "action": "approve"})
ok("admin approves investor + listing", ip["status"] == "approved" and ls["status"] == "published" and ls.get("reviewed_by") == ADM["id"])
ok("bad moderation action rejected", post("/admin/business-hub/action", {"kind": "listing", "id": ls["id"], "action": "explode"}).status_code == 302 and ls["status"] == "published")
as_(U3); r = c.get("/business/connect-plus/investments"); ok("approved investor sees listing + disclaimer", r.status_code == 200 and b"Expand plant" in r.data and b"does not give investment advice" in r.data)
post(f"/business/connect-plus/investments/{ls['id']}/interest", {"message": "Interested in the mill"}); it = DB["koja_connectplus_investor_interests"][0]
ok("interest recorded + owner notified", it["status"] == "sent" and any(n[0] == U1["id"] and "interest" in n[1].lower() for n in NOTES))
post(f"/business/connect-plus/investments/{ls['id']}/interest", {"message": "again"}); ok("duplicate interest blocked", len(DB["koja_connectplus_investor_interests"]) == 1)
as_(U1); r = c.get(f"/business/{B1}/fundraising"); ok("owner sees interest but NOT investor email yet", b"Ngoma Capital" in r.data and b"inv@ngoma.example.com" not in r.data)
as_(U2); post(f"/business/connect-plus/interest/{it['id']}/accept"); ok("another owner cannot respond to the interest", it["status"] == "sent")
as_(U1); post(f"/business/connect-plus/interest/{it['id']}/accept"); r = c.get(f"/business/{B1}/fundraising"); ok("accepting reveals investor contact", it["status"] == "accepted" and b"inv@ngoma.example.com" in r.data)
ok("investor notified of acceptance", any(n[0] == U3["id"] and "accepted" in n[1].lower() for n in NOTES))
as_(U1); DB["koja_connectplus_investor_profiles"].append({"id": "ip-own", "user_id": U1["id"], "display_name": "Owner1 as investor", "status": "approved", "contact_email": "o@t.com"})
n_int = len(DB["koja_connectplus_investor_interests"]); post(f"/business/connect-plus/investments/{ls['id']}/interest", {"message": "self-deal"})
ok("owner cannot invest in own listing", len(DB["koja_connectplus_investor_interests"]) == n_int)
post(f"/business/{B1}/fundraising/{ls['id']}/close"); ok("owner closes request", ls["status"] == "closed")

# =============== moderation: suspend profile ===============
as_(ADM); post("/admin/business-hub/action", {"kind": "profile", "id": p1["id"], "action": "suspend"}); as_(None)
ok("suspended profile gone from directory and public page", b"Zambezi Steel" not in c.get("/business-directory").data and c.get("/companies/zambezi-steel").status_code == 404)
as_(U1); post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "industry": "manufacturing", "location": "Kitwe", "description": DESC, "publish": "on"}); ok("owner cannot self-republish while suspended", p1["status"] == "suspended")
as_(ADM); post("/admin/business-hub/action", {"kind": "profile", "id": p1["id"], "action": "restore"}); ok("restore returns profile to draft", p1["status"] == "draft")
as_(U1); post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "industry": "manufacturing", "location": "Kitwe", "description": DESC, "publish": "on"}); ok("owner can republish after restore", p1["status"] == "published")
post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "industry": "manufacturing", "location": "Kitwe", "description": DESC}, data=None) if False else None
# logo upload path
post(f"/business/{B1}/profile", {"public_name": "Zambezi Steel", "industry": "manufacturing", "location": "Kitwe", "description": DESC, "publish": "on", "logo": (io.BytesIO(b"\x89PNG"), "l.png")}, content_type="multipart/form-data"); ok("logo upload stored", p1["logo_url"] == "https://cdn.example.com/logo.png")

# =============== every new page renders for the right user ===============
as_(U1)
pages = [f"/business/{B1}/hub", f"/business/{B1}/profile", f"/business/{B1}/services", f"/business/{B1}/pricing", f"/business/{B1}/inventory", f"/business/{B1}/pos",
         f"/business/{B1}/contracts", f"/business/{B1}/contracts/new", f"/business/{B1}/partnerships", f"/business/{B1}/fundraising", "/business/connect-plus/investors",
         "/business/connect-plus/investor/register", "/business/connect-plus/rfqs", "/industries", "/business-directory", "/companies", "/compare", "/companies/zambezi-steel/partner"]
bad = [(u, c.get(u, follow_redirects=True).status_code) for u in pages if c.get(u, follow_redirects=True).status_code != 200]
ok("all new pages render (200)", not bad, bad)
print(f"\n{sum(res)}/{len(res)} passed")
