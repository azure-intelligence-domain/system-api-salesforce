"""Salesforce, as the System API sees it: the Order records in Cosmos DB, in Salesforce's own data
model (backend-systems/salesforce/README.md), and the mapping to and from the platform's contract.

Nothing else reads this data model: everyone else gets the contract (openapi.yaml).
"""

import os
from datetime import datetime, timezone

from azure.core import MatchConditions
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

FIRST_ORDER_NUMBER = 4711


class OrderChanged(Exception):
    """The order changed since it was read (ETag no longer matches)."""


def record_id(order_number: str) -> str:
    """Salesforce's 18-character record id, derived from the order number: 4711 → 801Ad0000004711AAA."""
    return f"801Ad{int(order_number):010d}AAA"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Mapping: contract ↔ Salesforce -------------------------------------------------------------

SALESFORCE_STATUS = {"placed": "Draft", "cancelled": "Cancelled", "rejected": "Cancelled"}


def to_salesforce(order: dict) -> dict:
    """The contract's newOrder → the fields of a Salesforce Order record."""
    lines = order["orderLines"]
    address = order["deliveryAddress"]
    return {
        "AccountId": order["customerId"],
        "Status": SALESFORCE_STATUS.get(order["status"], "Activated"),
        "Order_Status__c": order["status"],
        "Payment_Status__c": order["paymentStatus"],
        "Channel__c": order["channel"],
        "OrderItems": [
            {
                "OrderItemNumber": line.get("lineNumber", number),
                "Product2Id": line["productId"],
                "Quantity": line["quantity"],
                "UnitPrice": line["unitPrice"]["value"],
            }
            for number, line in enumerate(lines, start=1)
        ],
        "CurrencyIsoCode": lines[0]["unitPrice"]["currency"],
        "TotalAmount": round(sum(line["quantity"] * line["unitPrice"]["value"] for line in lines), 2),
        "ShippingStreet": address["street"],
        "ShippingPostalCode": address["postalCode"],
        "ShippingCity": address["city"],
        "ShippingCountryCode": address["countryCode"],
        "Requested_Delivery_Date__c": order.get("requestedDeliveryDate"),
        "Hold_Reason__c": order.get("holdReason"),
        "Cancellation_Reason__c": order.get("cancellationReason"),
        "Idempotency_Key__c": order.get("idempotencyKey"),
    }


def to_platform(record: dict) -> dict:
    """A Salesforce Order record → the contract's order (without HAL links)."""
    currency = record["CurrencyIsoCode"]
    order = {
        "orderId": record["OrderNumber"],
        "recordId": record["id"],
        "customerId": record["AccountId"],
        "channel": record["Channel__c"],
        "status": record["Order_Status__c"],
        "paymentStatus": record["Payment_Status__c"],
        "orderLines": [
            {
                "lineNumber": item["OrderItemNumber"],
                "productId": item["Product2Id"],
                "quantity": item["Quantity"],
                "unitPrice": {"value": item["UnitPrice"], "currency": currency},
            }
            for item in record["OrderItems"]
        ],
        "totalAmount": {"value": record["TotalAmount"], "currency": currency},
        "deliveryAddress": {
            "street": record["ShippingStreet"],
            "postalCode": record["ShippingPostalCode"],
            "city": record["ShippingCity"],
            "countryCode": record["ShippingCountryCode"],
        },
        "requestedDeliveryDate": record.get("Requested_Delivery_Date__c"),
        "holdReason": record.get("Hold_Reason__c"),
        "cancellationReason": record.get("Cancellation_Reason__c"),
        "idempotencyKey": record.get("Idempotency_Key__c"),
        "createdAt": record["CreatedDate"],
        "updatedAt": record["LastModifiedDate"],
    }
    return {key: value for key, value in order.items() if value is not None}


# --- Storage: Cosmos DB, with the System API's runtime identity ----------------------------------


class Salesforce:
    """Order records in Cosmos DB. Returns (record, etag) pairs; records are in Salesforce's model."""

    def __init__(self, endpoint: str, client_id: str | None = None):
        credential = DefaultAzureCredential(managed_identity_client_id=client_id)
        database = CosmosClient(endpoint, credential).get_database_client("salesforce")
        self.orders = database.get_container_client("Order")
        self.counters = database.get_container_client("AutoNumber")

    @classmethod
    def from_environment(cls) -> "Salesforce":
        return cls(os.environ["SALESFORCE_ENDPOINT"], os.environ.get("AZURE_CLIENT_ID"))

    def next_order_number(self) -> str:
        """Salesforce auto-number: increment the counter with optimistic concurrency."""
        while True:
            try:
                counter = self.counters.read_item("OrderNumber", partition_key="OrderNumber")
            except exceptions.CosmosResourceNotFoundError:
                try:
                    self.counters.create_item({"id": "OrderNumber", "last": FIRST_ORDER_NUMBER})
                    return str(FIRST_ORDER_NUMBER)
                except exceptions.CosmosResourceExistsError:
                    continue
            counter["last"] += 1
            try:
                self.counters.replace_item(
                    counter, counter, etag=counter["_etag"], match_condition=MatchConditions.IfNotModified
                )
                return str(counter["last"])
            except exceptions.CosmosAccessConditionFailedError:
                continue

    def create(self, fields: dict) -> tuple[dict, str]:
        number = self.next_order_number()
        timestamp = now()
        record = {"id": record_id(number), "OrderNumber": number, **fields,
                  "CreatedDate": timestamp, "LastModifiedDate": timestamp}
        saved = self.orders.create_item(record)
        return saved, saved["_etag"]

    def get(self, order_number: str) -> tuple[dict, str] | None:
        try:
            record = self.orders.read_item(record_id(order_number), partition_key=record_id(order_number))
        except exceptions.CosmosResourceNotFoundError:
            return None
        return record, record["_etag"]

    def replace(self, order_number: str, fields: dict, etag: str) -> tuple[dict, str] | None:
        current = self.get(order_number)
        if current is None:
            return None
        record = {**current[0], **fields, "LastModifiedDate": now()}
        try:
            saved = self.orders.replace_item(
                record["id"], record, etag=etag, match_condition=MatchConditions.IfNotModified
            )
        except exceptions.CosmosAccessConditionFailedError as changed:
            raise OrderChanged from changed
        return saved, saved["_etag"]

    def list(self, customer_id=None, status=None, idempotency_key=None, offset=0, limit=20) -> tuple[list[dict], int]:
        filters = {"AccountId": customer_id, "Order_Status__c": status, "Idempotency_Key__c": idempotency_key}
        filters = {field: value for field, value in filters.items() if value}
        where = [f"c.{field} = @{field}" for field in filters]
        parameters = [{"name": f"@{field}", "value": value} for field, value in filters.items()]
        condition = f" WHERE {' AND '.join(where)}" if where else ""
        total = list(self.orders.query_items(
            f"SELECT VALUE COUNT(1) FROM c{condition}", parameters=parameters, enable_cross_partition_query=True
        ))[0]
        page = list(self.orders.query_items(
            f"SELECT * FROM c{condition} ORDER BY c.CreatedDate DESC OFFSET {int(offset)} LIMIT {int(limit)}",
            parameters=parameters, enable_cross_partition_query=True,
        ))
        return page, total
