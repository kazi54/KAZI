"""kazi adapters — list available destination adapters."""


def list_adapters() -> None:
    """List all registered destination adapters."""
    from kazi.delivery.destinations import DestinationRegistry

    registry = DestinationRegistry()

    print(f"\n  KAZI OS — Destination Adapters")
    print(f"  ──────────────────────────────")
    print(f"  {'ADAPTER':<20} {'CLASS':<35} {'STATUS'}")
    print(f"  {'─'*20} {'─'*35} {'─'*10}")

    for name, cls in registry._adapters.items():
        status = "built-in"
        print(f"  {name:<20} {cls.__name__:<35} {status}")

    print(f"\n  Register custom adapters in your domain's routes.py:")
    print(f"    registry.register('salesforce', SalesforceDestination)")
    print()
