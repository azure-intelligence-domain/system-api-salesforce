# Order Changed Meanwhile

`412 Precondition Failed`, `application/problem+json`

The order changed after it was read: the `If-Match` header no longer matches its `ETag`. Nothing was
saved. Read the order again, apply the change to what you read, and replace it with the new `ETag`.
