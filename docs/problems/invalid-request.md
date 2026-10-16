# Invalid Request

`400 Bad Request`, `application/problem+json`

The request does not match the [contract](../../openapi.yaml): the body breaks the `newOrder`
schema (the `detail` says where), the order lines have different currencies, `If-Match` is missing
on a replace, or the `Correlation-Id` header is missing or invalid.
