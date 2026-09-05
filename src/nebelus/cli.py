"""`nebelus` — the CLI over the SDK. Same auth (NEBELUS_API_KEY / NEBELUS_BASE_URL)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from .client import Nebelus, NebelusAPIError
from .export import export_to_code
from .models import AgentManifest


def _load_manifest(path: str) -> AgentManifest:
    p = Path(path)
    if p.suffix == ".json":
        return AgentManifest.model_validate(json.loads(p.read_text()))
    spec = importlib.util.spec_from_file_location("nebelus_manifest", p)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    manifest = getattr(mod, "manifest", None)
    if not isinstance(manifest, AgentManifest):
        raise SystemExit(f"{path} must define `manifest = AgentManifest(...)`")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nebelus", description="Nebelus Agents API CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("describe", help="everything buildable in this org, machine-readable")
    c = sub.add_parser("catalog", help="org catalog")
    c.add_argument("--view", default="models")
    c.add_argument("--query")
    a = sub.add_parser("apply", help="create-or-update from a manifest (.py or .json)")
    a.add_argument("path")
    d = sub.add_parser("diff", help="what apply would change")
    d.add_argument("path")
    p = sub.add_parser("probe", help="run the draft for real")
    p.add_argument("agent_id")
    p.add_argument("message")
    dep = sub.add_parser("deploy", help="deploy (needs org opt-in + deploy scope)")
    dep.add_argument("agent_id")
    e = sub.add_parser("export", help="export a live agent as a Python manifest")
    e.add_argument("agent_id")
    v = sub.add_parser("validate", help="pre-flight findings")
    v.add_argument("agent_id")
    args = ap.parse_args(argv)

    nb = Nebelus()
    try:
        if args.cmd == "describe":
            print(json.dumps(nb.describe(), indent=2, default=str))
        elif args.cmd == "catalog":
            print(json.dumps(nb.catalog(view=args.view, query=args.query), indent=2, default=str))
        elif args.cmd == "apply":
            agent = nb.apply(_load_manifest(args.path))
            print(f"{agent.id} {agent.status}")
        elif args.cmd == "diff":
            changes = nb.diff(_load_manifest(args.path))
            print(json.dumps(changes, indent=2, default=str) if changes else "in sync")
        elif args.cmd == "probe":
            r = nb.agents.probe(args.agent_id, args.message)
            print(r.reply or r.model_dump())
        elif args.cmd == "deploy":
            print(json.dumps(nb.agents.deploy(args.agent_id)))
        elif args.cmd == "validate":
            print(json.dumps(nb.agents.validate(args.agent_id).model_dump(), indent=2))
        elif args.cmd == "export":
            print(export_to_code(nb.agents.get(args.agent_id)))
    except NebelusAPIError as exc:
        print(f"error [{exc.status_code}]: {exc.detail}", file=sys.stderr)
        if exc.envelope:
            print(f"envelope: {json.dumps(exc.envelope)}", file=sys.stderr)
        if exc.blocked:
            print(f"blocked: {exc.blocked}", file=sys.stderr)
        return 1
    finally:
        nb.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
