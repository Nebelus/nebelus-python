"""`nebelus` — the CLI over the SDK. Same auth (NEBELUS_API_KEY / NEBELUS_BASE_URL)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import webbrowser
from pathlib import Path

from .client import Nebelus, NebelusAPIError
from .export import export_to_code
from .models import AgentManifest


def _open_browser(url: str) -> None:
    """Best-effort browser open — never fail the command if it can't (e.g. headless).
    The URL is always printed too, so suppressing here is safe."""
    import contextlib

    with contextlib.suppress(Exception):
        webbrowser.open(url)


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
    lg = sub.add_parser("login", help="sign in from the terminal (device flow — no API key needed)")
    lg.add_argument("--base-url", help="override the API host (default $NEBELUS_BASE_URL or api.nebelus.ai)")
    lg.add_argument("--no-browser", action="store_true", help="don't auto-open the browser; just print the URL")
    sub.add_parser("logout", help="remove the stored credentials")
    sub.add_parser("describe", help="everything buildable in this org, machine-readable")
    ls = sub.add_parser("list", help="list this org's agents (id, name, status)")
    ls.add_argument("--json", action="store_true", help="print the full JSON rows")
    up = sub.add_parser("upgrade", help="upgrade your plan (opens the browser)")
    up.add_argument("--no-browser", action="store_true", help="just print the URL")
    bl = sub.add_parser("billing", help="open Billing & Usage in the browser")
    bl.add_argument("--no-browser", action="store_true", help="just print the URL")
    c = sub.add_parser("catalog", help="org catalog")
    c.add_argument("--view", default="models")
    c.add_argument("--query")
    b = sub.add_parser("build", help="AI-assisted: describe an agent and the Vibe Builder builds it (draft)")
    b.add_argument("prompt", help="plain-language description of the agent to build")
    b.add_argument("--constraints", help="optional extra constraints to honor")
    b.add_argument("--json", action="store_true", help="print the full JSON result")
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
    k = sub.add_parser("keys", help="manage API keys")
    ksub = k.add_subparsers(dest="keys_cmd", required=True)
    kc = ksub.add_parser("create", help="mint an API key (full value shown once)")
    kc.add_argument("--scope", action="append", dest="scopes", required=True,
                    help="repeatable, e.g. --scope api.construction.read --scope api.construction.write")
    kc.add_argument("--name")
    ksub.add_parser("list", help="list this org's API keys (masked)")
    args = ap.parse_args(argv)

    # login/logout run BEFORE constructing the client (login has no credentials yet).
    if args.cmd == "login":
        from ._auth import device_login

        try:
            creds = device_login(base_url=args.base_url, open_browser=not args.no_browser)
        except Exception as exc:  # noqa: BLE001 — surface a clean CLI message
            print(f"login failed: {exc}", file=sys.stderr)
            return 1
        print(f"\nSigned in. Credentials saved for {creds['base_url']}.")
        return 0
    if args.cmd == "logout":
        from ._auth import clear_credentials

        print("Signed out." if clear_credentials() else "No stored credentials.")
        return 0

    nb = Nebelus()
    try:
        if args.cmd == "describe":
            print(json.dumps(nb.describe(), indent=2, default=str))
        elif args.cmd == "list":
            rows = nb.agents.list()
            if args.json:
                print(json.dumps(rows, indent=2, default=str))
            elif not rows:
                print("No agents yet. Create one with `nebelus build \"...\"` or `nebelus apply <file>`.")
            else:
                for row in rows:
                    status = str(row.get("status", ""))
                    print(f"{row.get('id')}  {status:8}  {row.get('name','')}"
                          + (f"  [{row.get('model_id')}]" if row.get('model_id') else ""))
        elif args.cmd == "catalog":
            print(json.dumps(nb.catalog(view=args.view, query=args.query), indent=2, default=str))
        elif args.cmd == "build":
            print("Building your agent… this can take a minute or two.", file=sys.stderr, flush=True)
            result = nb.build(args.prompt, constraints=args.constraints)
            if args.json:
                print(json.dumps(result, indent=2, default=str))
            elif result.get("built"):
                agent = result["agent"]
                print(f"built {agent['id']} ({agent.get('name')}) [{agent['status']}]")
                if result.get("notes"):
                    print(f"\n{result['notes']}")
                print(f"\nrefine it:  nebelus export {agent['id']} > agent.py")
            else:
                print(f"nothing built [{result.get('status')}]")
                if result.get("notes"):
                    print(result["notes"])
                return 1
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
        elif args.cmd == "upgrade":
            info = (nb.describe() or {}).get("account") or {}
            kind, url = info.get("kind"), info.get("upgrade_url")
            if kind == "developers" and info.get("deploy_enabled"):
                print("You're already on the Deploy tier — `nebelus deploy` is enabled.")
            elif not url or kind == "enterprise":
                print("Your workspace is managed by our team — contact sales@nebelus.ai to change your plan.")
            else:
                print(f"\n  Opening your upgrade page:\n  {url}")
                if kind == "core":
                    print("  (Nebelus Core upgrades are handled by our team.)")
                if not args.no_browser:
                    _open_browser(url)
                print("\n  Sign in if prompted, then complete the upgrade in your browser.")
        elif args.cmd == "billing":
            base = nb._t.base_url or "https://api.nebelus.ai"
            portal = base if ("localhost" in base or "127.0.0.1" in base) else "https://app.nebelus.ai"
            url = f"{portal}/billing-usage/billing"
            print(f"\n  Opening billing:\n  {url}")
            if not args.no_browser:
                _open_browser(url)
        elif args.cmd == "keys":
            if args.keys_cmd == "create":
                out = nb.keys.create(scopes=args.scopes, name=args.name)
                print(out.get("sensitive_id") or json.dumps(out, indent=2))
                print("Save this key now — it won't be shown again.", file=sys.stderr)
            else:
                for row in nb.keys.list():
                    print(f"{row.get('partial_key', row.get('id'))}  {row.get('name','')}  {row.get('scopes', [])}")
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
