"""[Sales] Salesforce System API (openapi.yaml): orders as Salesforce keeps them, in the platform's
contract. Only API Management reaches it (Easy Auth lets in the gateways' identities only), and only
building blocks on the platform's allow-list reach the gateway's system-apis product (ADR 0014).

A System API stores what it is given: the order domain's rules live in the Order Process API.
"""

import json
import logging

import azure.functions as func

import contract
from salesforce import OrderChanged, Salesforce, to_platform, to_salesforce

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)  # Easy Auth guards the door

PROBLEMS = "https://github.com/azure-intelligence-domain/system-api-salesforce/blob/main/docs/problems/"
_salesforce: Salesforce | None = None


def salesforce() -> Salesforce:
    global _salesforce
    if _salesforce is None:
        _salesforce = Salesforce.from_environment()
    return _salesforce


# --- Responses ----------------------------------------------------------------------------------


def hal(status: int, body: dict, headers: dict | None = None) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/hal+json", headers=headers)


def problem(status: int, title: str, detail: str, slug: str, instance: str) -> func.HttpResponse:
    body = {"type": PROBLEMS + slug + ".md", "title": title, "status": status, "detail": detail, "instance": instance}
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/problem+json")


def invalid(detail: str, instance: str) -> func.HttpResponse:
    return problem(400, "Invalid Request", detail, "invalid-request", instance)


def with_links(order: dict) -> dict:
    return {"_links": {"self": {"href": f"/orders/{order['orderId']}"}}, **order}


def etag_header(etag: str) -> dict:
    return {"ETag": etag if etag.startswith('"') else f'"{etag}"'}


# --- Handlers (plain functions, so the tests can call them with a fake Salesforce) --------------


def correlation_problem(req: func.HttpRequest) -> func.HttpResponse | None:
    errors = contract.violations(contract.CORRELATION, req.headers.get("Correlation-Id", ""))
    if errors:
        return invalid("The Correlation-Id header is missing or invalid, for example ord-4711.", req.url)
    logging.info("Correlation-Id %s: %s %s", req.headers["Correlation-Id"], req.method, req.url)
    return None


def read_order(req: func.HttpRequest) -> tuple[dict | None, func.HttpResponse | None]:
    try:
        body = req.get_json()
    except ValueError:
        return None, invalid("The body is not JSON.", req.url)
    errors = contract.violations(contract.NEW_ORDER, body)
    if not errors and len({line["unitPrice"]["currency"] for line in body["orderLines"]}) > 1:
        errors = ["orderLines: all lines must have the same currency"]
    if errors:
        return None, invalid("; ".join(errors), req.url)
    return body, None


def create_order(req: func.HttpRequest, sf: Salesforce) -> func.HttpResponse:
    if refused := correlation_problem(req):
        return refused
    body, refused = read_order(req)
    if refused:
        return refused
    record, etag = sf.create(to_salesforce(body))
    order = with_links(to_platform(record))
    return hal(201, order, {"Location": f"/orders/{order['orderId']}", **etag_header(etag)})


def retrieve_order(req: func.HttpRequest, sf: Salesforce) -> func.HttpResponse:
    if refused := correlation_problem(req):
        return refused
    order_id = req.route_params["orderId"]
    found = sf.get(order_id) if order_id.isdigit() else None
    if found is None:
        return problem(404, "Order Not Found", f"Salesforce has no order {order_id}.", "order-not-found", req.url)
    record, etag = found
    return hal(200, with_links(to_platform(record)), etag_header(etag))


def replace_order(req: func.HttpRequest, sf: Salesforce) -> func.HttpResponse:
    if refused := correlation_problem(req):
        return refused
    order_id = req.route_params["orderId"]
    if_match = req.headers.get("If-Match", "")
    if not if_match:
        return invalid("The If-Match header is required: the ETag of the order as it was read.", req.url)
    body, refused = read_order(req)
    if refused:
        return refused
    try:
        saved = sf.replace(order_id, to_salesforce(body), if_match.strip('"')) if order_id.isdigit() else None
    except OrderChanged:
        return problem(412, "Order Changed Meanwhile",
                       "The order changed since it was read. Read it again and retry.", "order-changed", req.url)
    if saved is None:
        return problem(404, "Order Not Found", f"Salesforce has no order {order_id}.", "order-not-found", req.url)
    record, etag = saved
    return hal(200, with_links(to_platform(record)), etag_header(etag))


def retrieve_list_of_orders(req: func.HttpRequest, sf: Salesforce) -> func.HttpResponse:
    if refused := correlation_problem(req):
        return refused
    try:
        offset = int(req.params.get("offset", 0))
        limit = int(req.params.get("limit", 20))
    except ValueError:
        return invalid("offset and limit are integers.", req.url)
    if offset < 0 or not 1 <= limit <= 100:
        return invalid("offset is at least 0; limit is between 1 and 100.", req.url)
    query = {name: req.params.get(name) for name in ("customerId", "status", "idempotencyKey")}
    records, total = sf.list(query["customerId"], query["status"], query["idempotencyKey"], offset, limit)

    filters = "".join(f"{name}={value}&" for name, value in query.items() if value)
    page = lambda start: {"href": f"/orders?{filters}offset={start}&limit={limit}"}  # noqa: E731
    last = max(0, (total - 1) // limit * limit)
    links = {"self": page(offset), "first": page(0), "last": page(last)}
    if offset > 0:
        links["prev"] = page(max(0, offset - limit))
    if offset + limit < total:
        links["next"] = page(offset + limit)
    orders = [with_links(to_platform(record)) for record in records]
    return hal(200, {"_links": links, "totalCount": total, "_embedded": {"orders": orders}})


# --- Routes (host.json: no route prefix, so the paths are the contract's) -----------------------


@app.route(route="orders", methods=["POST"])
def createOrder(req: func.HttpRequest) -> func.HttpResponse:
    return create_order(req, salesforce())


@app.route(route="orders", methods=["GET"])
def retrieveListOfOrders(req: func.HttpRequest) -> func.HttpResponse:
    return retrieve_list_of_orders(req, salesforce())


@app.route(route="orders/{orderId}", methods=["GET"])
def retrieveOrder(req: func.HttpRequest) -> func.HttpResponse:
    return retrieve_order(req, salesforce())


@app.route(route="orders/{orderId}", methods=["PUT"])
def replaceOrder(req: func.HttpRequest) -> func.HttpResponse:
    return replace_order(req, salesforce())
