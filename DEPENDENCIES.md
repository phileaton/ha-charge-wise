# Dependencies

Charge Wise has no additional Python runtime dependencies. The integration uses Home Assistant's built-in entity,
selector, coordinator, and service APIs; `manifest.json` declares an empty `requirements` list, and `requirements.txt`
is intentionally empty.

The development environment has separate `requirements_dev.txt` and `requirements_test.txt` files for repository
tooling and tests. Add a runtime package only when the integration needs it, and keep the requirement in
`manifest.json` and `requirements.txt` in sync.
