# Security checklist

The chief hands this page to the merge reviewer when the plan's `touches:` names data, auth or
external. The reviewer checks the diff against each item.

- **Inputs** are validated at the boundary where they enter, before any use.
- **Secrets** never enter the tree, a log, an error message or a test fixture.
- **Auth** is checked on every path to a capability, error and retry paths included, not only the
  happy one.
- **External calls** carry a timeout and handle failure: refused, slow, malformed and partial
  responses.
- **Migrations** are reversible, and the rollback is stated.
