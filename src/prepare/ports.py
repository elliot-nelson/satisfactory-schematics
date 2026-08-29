"""Normalize the raw connection-component dump into ports.json.

Port positions aren't in the docs dump -- conveyor/pipe connections are Blueprint components
(FGFactoryConnectionComponent = belt, FGPipeConnectionFactory = pipe) on the Build_* blueprint.
``sf-extract --dump-ports`` records their RelativeLocation/RelativeRotation/direction; here we
classify role/kind and convert to building-local meters (X fwd, Y right, Z up), keeping the facing
yaw so the renderer can pick the correct edge. Power connections are skipped -- they're just a nub
on the body, not a belt/pipe mouth, so there's nothing worth drawing.

Output looks like: ``{name: [{role, kind, pos:[x,y,z] m, yaw: deg}]}``.
"""

from __future__ import annotations

from typing import Any


def classify(port: dict[str, Any]) -> tuple[str, str]:
    """(role, kind) for a belt/pipe connection: input/output + belt/pipe."""
    cls = port["class"]
    props = port.get("props", {})
    if "Pipe" in cls:
        pct = props.get("mPipeConnectionType", "")
        return ("output" if "PRODUCER" in pct else "input"), "pipe"
    return ("output" if "FCD_OUTPUT" in props.get("mDirection", "") else "input"), "belt"


def build_ports(raw: list[dict], name_by_leaf: dict[str, str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in raw:
        leaf = entry["asset"].rsplit("/", 1)[-1]
        name = name_by_leaf.get(leaf)
        if name is None:
            continue
        ports: list[dict] = []
        for pt in entry.get("ports", []):
            if "PowerConnection" in pt["class"]:  # power nub, not a belt/pipe mouth -- skip it
                continue
            role, kind = classify(pt)
            loc = pt["loc"]
            ports.append(
                {
                    "role": role,
                    "kind": kind,
                    "pos": [round(loc[i] / 100.0, 4) for i in range(3)],
                    "yaw": round(pt["rot"][1], 2),
                }
            )
        out[name] = ports
    return out
