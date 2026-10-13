#!/usr/bin/env python3
"""inventory gate (shipped, not core): the generated inventories under
`docs/inventory/` match what their extractors print now
(`docs/process/inventories.md`). A project registers it in
`docs/process/gates.local.json`:

    {"inventory": {"module": null, "command": ["scripts/process/check_inventory.py", "."]}}

and starts it in shadow (`gate_modes.py weaken inventory --to shadow --observe`).

Without `docs/process/inventories.local.json` the gate fails: whoever
registered it expected lists, and a renamed configuration must not turn it
silently green. Otherwise it is `inventory.py check`, exit 0 or 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import inventory  # noqa: E402
import inventory_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else ".").resolve()
    try:
        conf = inventory_config.load(root)
    except inventory_config.ConfigError as exc:
        print(f"inventory: FAILED: {exc}")
        return 1
    if not conf:  # missing, or `{"inventories": {}}`: a registered gate expected lists
        print(f"inventory: FAILED: registered but no inventory in {inventory_config.CONFIG} — "
              "configure the inventories or take the gate out of docs/process/gates.local.json")
        return 1
    try:
        errors, said = inventory.check(root, conf)
    except inventory.InventoryError as exc:
        errors, said = [str(exc)], []
    for note in said:
        print(f"inventory: note: {note}")
    if errors:
        print("inventory: FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"inventory: OK ({len(conf)} list(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
