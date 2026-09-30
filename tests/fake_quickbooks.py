"""An in-memory stand-in for Intuit's sign-in and QuickBooks Online APIs.

It replaces quickbooks._send, so tests exercise the real request-building
and response-handling code without touching the network."""

import base64
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import parse_qs, urlparse

from backline import quickbooks as qb

CLIENT_ID, CLIENT_SECRET = "test-client-id", "test-client-secret"


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fault(status, code, message, detail=""):
    return status, json.dumps({"Fault": {"Error": [{"Message": message, "Detail": detail, "code": code}],
                                         "type": "ValidationFault"}})


class FakeQuickBooks:
    def __init__(self):
        self.realm = "9130"
        self.company_name = "Sandbox Company_US_1"
        self.access_token, self.refresh_token = "access-0", "refresh-0"
        self.issued = 0
        self.valid_codes = {"good-code"}
        self.refresh_fails = False
        self.expire_access = False  # the next API call gets a 401
        self.down = False
        self.tax_rate = Decimal(0)  # percent QuickBooks charges on TAX lines
        self.calls, self.emails, self.revoked = [], [], []
        self.next_id = 100
        self.customers, self.invoices, self.payments = {}, {}, {}
        self.items = {
            "1": {"Id": "1", "Name": "Services", "Type": "Service"},
            "2": {"Id": "2", "Name": "Audio & backline rental", "Type": "Service"},
            "3": {"Id": "3", "Name": "Customer deposits", "Type": "Service"},
            "4": {"Id": "4", "Name": "Hours", "Type": "Category"},
        }
        self.tax_codes = {
            "TAX": {"Id": "TAX", "Name": "TAX"},
            "NON": {"Id": "NON", "Name": "NON"},
            "5": {"Id": "5", "Name": "Chicago 10.25%"},
        }

    # --- helpers for tests: things that happen inside QuickBooks ---------------

    def new_id(self):
        self.next_id += 1
        return str(self.next_id)

    def receive_payment(self, invoice_ids_amounts, date="2030-02-01", ref=None):
        """A client pays in QuickBooks (online, or the office records a check there)."""
        if isinstance(invoice_ids_amounts, tuple):
            invoice_ids_amounts = [invoice_ids_amounts]
        pid = self.new_id()
        lines = [{"Amount": float(amount), "LinkedTxn": [{"TxnId": iid, "TxnType": "Invoice"}]}
                 for iid, amount in invoice_ids_amounts]
        first = self.invoices[invoice_ids_amounts[0][0]]
        self.payments[pid] = {"Id": pid, "SyncToken": "0", "TxnDate": date, "CustomerRef": first["CustomerRef"],
                              "TotalAmt": float(sum(_money(a) for _i, a in invoice_ids_amounts)), "Line": lines,
                              "PaymentRefNum": ref}
        return pid

    def api_calls(self, method=None, path_end=None):
        return [c for c in self.calls if c[1] != "token" and (method is None or c[0] == method)
                and (path_end is None or c[1].endswith(path_end))]

    # --- request handling --------------------------------------------------------

    def __call__(self, method, url, headers, body=None):
        if self.down:
            raise qb.QuickBooksError("Couldn't reach QuickBooks. Check the internet connection and try again.")
        if url == qb.TOKEN_URL:
            self.calls.append((method, "token", {}, body))
            return self._token(headers, body)
        if url == qb.REVOKE_URL:
            self.revoked.append(json.loads(body)["token"])
            return 200, ""
        parsed = urlparse(url)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        assert url.startswith(qb.API_BASE["sandbox"] + "/v3/company/"), url
        assert params.get("minorversion") == qb.MINOR_VERSION
        realm, path = re.match(r"^/v3/company/([^/]+)/(.+)$", parsed.path).groups()
        assert realm == self.realm
        payload = json.loads(body) if body and headers.get("Content-Type") == "application/json" else None
        self.calls.append((method, path, params, payload))
        if headers.get("Authorization") != f"Bearer {self.access_token}" or self.expire_access:
            self.expire_access = False
            return 401, json.dumps({"fault": {"error": [{"message": "message=AuthenticationFailed",
                                                         "detail": "Token expired", "code": "3200"}],
                                              "type": "AUTHENTICATION"}})
        return self._api(method, path, params, payload)

    def _token(self, headers, body):
        assert headers["Authorization"] == "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        form = {k: v[0] for k, v in parse_qs(body).items()}
        if form["grant_type"] == "authorization_code":
            if form["code"] not in self.valid_codes:
                return 400, json.dumps({"error": "invalid_grant"})
            assert form["redirect_uri"].endswith("/settings/quickbooks/callback")
        elif form["grant_type"] == "refresh_token":
            if self.refresh_fails or form["refresh_token"] != self.refresh_token:
                return 400, json.dumps({"error": "invalid_grant"})
        else:
            return 400, json.dumps({"error": "unsupported_grant_type"})
        self.issued += 1
        self.access_token, self.refresh_token = f"access-{self.issued}", f"refresh-{self.issued}"
        return 200, json.dumps({"token_type": "bearer", "access_token": self.access_token, "expires_in": 3600,
                                "refresh_token": self.refresh_token, "x_refresh_token_expires_in": 8726400})

    def _api(self, method, path, params, payload):
        if method == "GET" and path == f"companyinfo/{self.realm}":
            return 200, json.dumps({"CompanyInfo": {"CompanyName": self.company_name}})
        if method == "GET" and path == "query":
            return self._query(params["query"], params)
        if method == "POST" and path == "customer":
            if any(c["DisplayName"] == payload["DisplayName"] for c in self.customers.values()):
                return _fault(400, "6240", "Duplicate Name Exists Error", "The name supplied already exists.")
            cid = self.new_id()
            self.customers[cid] = {**payload, "Id": cid, "SyncToken": "0"}
            return 200, json.dumps({"Customer": self.customers[cid]})
        if method == "POST" and path == "invoice":
            if params.get("operation") == "void":
                return self._void(payload)
            return self._save_invoice(payload)
        m = re.match(r"^invoice/(\w+)(/send)?$", path)
        if m:
            inv = self.invoices.get(m.group(1))
            if inv is None:
                return _fault(400, "610", "Object Not Found", "Object Not Found : Something you're trying to use has been made inactive.")
            if m.group(2):
                self.emails.append((inv["Id"], inv["BillEmail"]["Address"]))
            return 200, json.dumps({"Invoice": self._render_invoice(inv, params)})
        if method == "POST" and path == "payment":
            return self._save_payment(payload)
        raise AssertionError(f"unexpected QuickBooks call {method} {path}")

    def _query(self, sql, params):
        m = re.match(r"^select \* from (\w+)(?: where (.+?))?(?: maxresults \d+)?$", sql.strip(), re.I)
        assert m, sql
        entity, where = m.groups()
        store = {"Customer": self.customers, "Invoice": self.invoices, "Payment": self.payments,
                 "Item": self.items, "TaxCode": self.tax_codes}[entity]
        rows = list(store.values())
        if entity == "Customer":  # like QuickBooks, queries skip inactive records
            rows = [r for r in rows if r.get("Active", True)]
        for cond in re.split(r"\s+and\s+", where or "", flags=re.I):
            cond = cond.strip()
            if not cond:
                continue
            if re.fullmatch(r"Active = true", cond, re.I):
                rows = [r for r in rows if r.get("Active", True)]
                continue
            eq = re.fullmatch(r"(\w+) = '((?:[^'\\]|\\.)*)'", cond)
            if eq:
                value = eq.group(2).replace("\\'", "'").replace("\\\\", "\\")
                rows = [r for r in rows if r.get(eq.group(1)) == value]
                continue
            ids = re.fullmatch(r"Id in \((.+)\)", cond, re.I)
            assert ids, f"unsupported query: {sql}"
            wanted = set(re.findall(r"'([^']*)'", ids.group(1)))
            rows = [r for r in rows if r["Id"] in wanted]
        if entity == "Invoice":
            rows = [self._render_invoice(r, params) for r in rows]
        if entity == "Payment":
            rows = [dict(r) for r in rows]
        return 200, json.dumps({"QueryResponse": {entity: rows, "startPosition": 1, "maxResults": len(rows)} if rows else {}})

    def _totals(self, inv):
        subtotal = discount = taxable = Decimal(0)
        for line in inv["Line"]:
            if line["DetailType"] == "SalesItemLineDetail":
                amount = _money(line["Amount"])
                subtotal += amount
                if line["SalesItemLineDetail"]["TaxCodeRef"]["value"] == "TAX":
                    taxable += amount
            elif line["DetailType"] == "DiscountLineDetail":
                discount += _money(line["Amount"])
        if subtotal and taxable:
            taxable -= discount * taxable / subtotal
        total = subtotal - discount + _money(taxable * self.tax_rate / 100)
        if inv.get("voided"):
            total = Decimal(0)
        paid = sum((_money(line["Amount"]) for p in self.payments.values() for line in p["Line"]
                    if any(t["TxnId"] == inv["Id"] for t in line["LinkedTxn"])), Decimal(0))
        return total, total - paid

    def _render_invoice(self, inv, params):
        total, balance = self._totals(inv)
        out = {**inv, "TotalAmt": float(total), "Balance": float(max(balance, Decimal(0)))}
        out["LinkedTxn"] = [{"TxnId": p["Id"], "TxnType": "Payment"} for p in self.payments.values()
                            if any(t["TxnId"] == inv["Id"] for line in p["Line"] for t in line["LinkedTxn"])]
        out.pop("voided", None)
        if params.get("include") == "invoiceLink" and inv.get("AllowOnlineCreditCardPayment") and inv.get("BillEmail"):
            out["InvoiceLink"] = f"https://connect.intuit.com/t/pay-{inv['Id']}"
        return out

    def _save_invoice(self, payload):
        if payload["CustomerRef"]["value"] not in self.customers:
            return _fault(400, "2500", "Invalid Reference Id", "Customer not found")
        for line in payload.get("Line", []):
            if line["DetailType"] == "SalesItemLineDetail":
                detail = line["SalesItemLineDetail"]
                if detail["ItemRef"]["value"] not in self.items:
                    return _fault(400, "2500", "Invalid Reference Id", "Item not found")
                if _money(Decimal(str(detail["Qty"])) * Decimal(str(detail["UnitPrice"]))) != _money(line["Amount"]):
                    return _fault(400, "6070", "Amount is not equal to UnitPrice * Qty")
        if "Id" in payload:
            inv = self.invoices.get(payload["Id"])
            if inv is None:
                return _fault(400, "610", "Object Not Found")
            if payload["SyncToken"] != inv["SyncToken"]:
                return _fault(400, "5010", "Stale Object Error")
            assert payload.get("sparse") is True
            inv.update({k: v for k, v in payload.items() if k not in ("Id", "SyncToken", "sparse")})
            inv["SyncToken"] = str(int(inv["SyncToken"]) + 1)
        else:
            iid = self.new_id()
            inv = self.invoices[iid] = {**payload, "Id": iid, "SyncToken": "0"}
        return 200, json.dumps({"Invoice": self._render_invoice(inv, {})})

    def _void(self, payload):
        inv = self.invoices[payload["Id"]]
        if payload["SyncToken"] != inv["SyncToken"]:
            return _fault(400, "5010", "Stale Object Error")
        inv["voided"] = True
        inv["SyncToken"] = str(int(inv["SyncToken"]) + 1)
        return 200, json.dumps({"Invoice": self._render_invoice(inv, {})})

    def _save_payment(self, payload):
        assert payload["CustomerRef"]["value"] in self.customers
        for line in payload["Line"]:
            for t in line["LinkedTxn"]:
                assert t["TxnType"] == "Invoice" and t["TxnId"] in self.invoices
                inv = self.invoices[t["TxnId"]]
                assert inv["CustomerRef"] == payload["CustomerRef"], "payment and invoice customers differ"
                if _money(line["Amount"]) > self._totals(inv)[1]:
                    return _fault(400, "6000", "A business validation error has occurred while processing your request",
                                  "The payment amount is more than the invoice balance.")
        pid = self.new_id()
        self.payments[pid] = {**payload, "Id": pid, "SyncToken": "0"}
        return 200, json.dumps({"Payment": self.payments[pid]})
