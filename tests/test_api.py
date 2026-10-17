"""The System API against its contract, with an in-memory Salesforce instead of Cosmos DB."""

import json

import azure.functions as func
import pytest

import function_app as api
import sample_data
from salesforce import FIRST_ORDER_NUMBER, OrderChanged, record_id, to_platform, to_salesforce

ORDER = {
    "customerId": "ACME", "channel": "salesforce", "status": "placed", "paymentStatus": "unpaid",
    "orderLines": [{"lineNumber": 1, "productId": "SKU-1042", "quantity": 12,
                    "unitPrice": {"value": 7000.0, "currency": "EUR"}}],
    "deliveryAddress": {"street": "Rue de la Loi 16", "postalCode": "1000", "city": "Brussels", "countryCode": "BE"},
    "requestedDeliveryDate": "2026-10-09", "idempotencyKey": "0b7e2a4c-4711-4c1e-9d2a-acme0001",
}


class FakeSalesforce:
    """Same interface as salesforce.Salesforce; ETags are version numbers."""

    def __init__(self):
        self.records, self.last = {}, FIRST_ORDER_NUMBER - 1

    def create(self, fields):
        self.last += 1
        number = str(self.last)
        record = {"id": record_id(number), "OrderNumber": number, **fields, "_etag": "1",
                  "CreatedDate": f"2026-10-16T10:{self.last % 60:02d}:00Z", "LastModifiedDate": "2026-10-16T10:00:00Z"}
        self.records[number] = record
        return record, record["_etag"]

    def get(self, number):
        record = self.records.get(number)
        return (record, record["_etag"]) if record else None

    def replace(self, number, fields, etag):
        if number not in self.records:
            return None
        if self.records[number]["_etag"] != etag:
            raise OrderChanged
        record = {**self.records[number], **fields, "_etag": str(int(etag) + 1)}
        self.records[number] = record
        return record, record["_etag"]

    def list_accounts(self):
        return sorted(sample_data.ACCOUNTS, key=lambda a: a["Name"])

    def get_account(self, customer_id):
        return next((a for a in sample_data.ACCOUNTS if a["AccountNumber"] == customer_id), None)

    def list_products(self):
        return sample_data.PRODUCTS

    def list(self, customer_id=None, status=None, idempotency_key=None, offset=0, limit=20):
        found = [r for r in self.records.values()
                 if (not customer_id or r["AccountId"] == customer_id)
                 and (not status or r["Order_Status__c"] == status)
                 and (not idempotency_key or r["Idempotency_Key__c"] == idempotency_key)]
        found.sort(key=lambda r: r["CreatedDate"], reverse=True)
        return found[offset:offset + limit], len(found)


def request(method, url, body=None, route=None, params=None, headers=None):
    headers = {"Correlation-Id": "ord-4711", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else b""
    return func.HttpRequest(method, url, headers=headers, params=params or {}, route_params=route or {}, body=data)


@pytest.fixture
def sf():
    return FakeSalesforce()


def test_the_first_order_is_4711(sf):
    response = api.create_order(request("POST", "/orders", ORDER), sf)
    order = json.loads(response.get_body())
    assert response.status_code == 201
    assert response.mimetype == "application/hal+json"
    assert response.headers["Location"] == "/orders/4711"
    assert order["orderId"] == "4711" and order["recordId"] == "801Ad0000004711AAA"
    assert order["totalAmount"] == {"value": 84000.0, "currency": "EUR"}  # Salesforce computes it


def test_salesforce_keeps_its_own_model(sf):
    fields = to_salesforce(ORDER)
    assert fields["AccountId"] == "ACME"
    assert fields["Status"] == "Draft" and fields["Order_Status__c"] == "placed"
    assert fields["ShippingCity"] == "Brussels"
    assert fields["OrderItems"][0] == {"OrderItemNumber": 1, "Product2Id": "SKU-1042", "Quantity": 12, "UnitPrice": 7000.0}
    assert to_salesforce({**ORDER, "status": "cancelled"})["Status"] == "Cancelled"
    assert to_salesforce({**ORDER, "status": "confirmed"})["Status"] == "Activated"


def test_round_trip_keeps_the_order(sf):
    record, _ = sf.create(to_salesforce(ORDER))
    order = to_platform(record)
    assert {k: order[k] for k in ORDER} == ORDER


def test_contract_violations_are_400_problems(sf):
    response = api.create_order(request("POST", "/orders", {**ORDER, "orderLines": []}), sf)
    problem = json.loads(response.get_body())
    assert response.status_code == 400 and response.mimetype == "application/problem+json"
    assert problem["title"] == "Invalid Request" and "orderLines" in problem["detail"]


def test_mixed_currencies_are_refused(sf):
    lines = ORDER["orderLines"] + [{"productId": "SKU-7", "quantity": 1, "unitPrice": {"value": 1.0, "currency": "USD"}}]
    assert api.create_order(request("POST", "/orders", {**ORDER, "orderLines": lines}), sf).status_code == 400


@pytest.mark.parametrize("correlation_id", ["", "ORD 4711"])
def test_correlation_id_is_required(sf, correlation_id):
    response = api.retrieve_order(request("GET", "/orders/4711", route={"orderId": "4711"},
                                          headers={"Correlation-Id": correlation_id}), sf)
    assert response.status_code == 400


def test_retrieve_order_with_etag(sf):
    api.create_order(request("POST", "/orders", ORDER), sf)
    response = api.retrieve_order(request("GET", "/orders/4711", route={"orderId": "4711"}), sf)
    assert response.status_code == 200 and response.headers["ETag"] == '"1"'
    assert json.loads(response.get_body())["_links"]["self"]["href"] == "/orders/4711"


@pytest.mark.parametrize("order_id", ["4712", "abc"])
def test_unknown_order_is_404(sf, order_id):
    response = api.retrieve_order(request("GET", f"/orders/{order_id}", route={"orderId": order_id}), sf)
    assert response.status_code == 404
    assert json.loads(response.get_body())["title"] == "Order Not Found"


def test_replace_needs_the_current_etag(sf):
    api.create_order(request("POST", "/orders", ORDER), sf)
    cancelled = {**ORDER, "status": "cancelled", "cancellationReason": "Customer withdrew the order."}
    route = {"orderId": "4711"}

    assert api.replace_order(request("PUT", "/orders/4711", cancelled, route), sf).status_code == 400  # no If-Match
    ok = api.replace_order(request("PUT", "/orders/4711", cancelled, route, headers={"If-Match": '"1"'}), sf)
    assert ok.status_code == 200 and json.loads(ok.get_body())["status"] == "cancelled"
    stale = api.replace_order(request("PUT", "/orders/4711", cancelled, route, headers={"If-Match": '"1"'}), sf)
    assert stale.status_code == 412 and json.loads(stale.get_body())["title"] == "Order Changed Meanwhile"


def test_list_pages_with_hal_links(sf):
    for key in ("a", "b", "c"):
        api.create_order(request("POST", "/orders", {**ORDER, "idempotencyKey": key}), sf)
    sf.create(to_salesforce({**ORDER, "customerId": "GLOBEX"}))

    response = api.retrieve_list_of_orders(request("GET", "/orders", params={"customerId": "ACME", "limit": "2"}), sf)
    page = json.loads(response.get_body())
    assert page["totalCount"] == 3 and len(page["_embedded"]["orders"]) == 2
    assert page["_links"]["next"]["href"] == "/orders?customerId=ACME&offset=2&limit=2"
    assert page["_links"]["last"]["href"] == "/orders?customerId=ACME&offset=2&limit=2"
    assert "prev" not in page["_links"]

    by_key = api.retrieve_list_of_orders(request("GET", "/orders", params={"idempotencyKey": "b"}), sf)
    assert [o["idempotencyKey"] for o in json.loads(by_key.get_body())["_embedded"]["orders"]] == ["b"]

    sf.replace("4712", to_salesforce({**ORDER, "status": "cancelled"}), "1")
    cancelled = api.retrieve_list_of_orders(request("GET", "/orders", params={"status": "cancelled"}), sf)
    assert [o["orderId"] for o in json.loads(cancelled.get_body())["_embedded"]["orders"]] == ["4712"]


def test_list_refuses_a_limit_over_100(sf):
    assert api.retrieve_list_of_orders(request("GET", "/orders", params={"limit": "500"}), sf).status_code == 400


def test_references_and_timeline_are_kept(sf):
    with_more = {**ORDER, "references": {"erpOrderNumber": "8000043217", "shipmentId": "SPD-004711"},
                 "timeline": [{"fact": "OrderPlaced", "domain": "order", "occurredAt": "2026-10-03T09:12:00Z"}]}
    created = json.loads(api.create_order(request("POST", "/orders", with_more), sf).get_body())
    assert created["references"] == with_more["references"] and created["timeline"] == with_more["timeline"]
    record = sf.records["4711"]
    assert record["ERP_Order_Number__c"] == "8000043217" and record["Order_Milestones__r"][0]["Fact__c"] == "OrderPlaced"


def test_accounts_and_products(sf):
    accounts = json.loads(api.retrieve_list_of_accounts(request("GET", "/accounts"), sf).get_body())
    assert accounts["totalCount"] == 4 and accounts["_embedded"]["accounts"][0]["customerId"] == "ACME"
    acme = api.retrieve_account(request("GET", "/accounts/ACME", route={"customerId": "ACME"}), sf)
    assert json.loads(acme.get_body())["shippingAddress"]["city"] == "Brussels"
    assert api.retrieve_account(request("GET", "/accounts/X", route={"customerId": "X"}), sf).status_code == 404
    products = json.loads(api.retrieve_list_of_products(request("GET", "/products"), sf).get_body())
    press = next(p for p in products["_embedded"]["products"] if p["productId"] == "SKU-1042")
    assert press["unitPrice"] == {"value": 7000.0, "currency": "EUR"}
