import argparse
import json
import sys
from . import __version__
from .core import Engine
from .firmware import Firmware
from .layout import load_config
from .util import Error


def main(argv=None, engine=None):
    parser = argparse.ArgumentParser(prog="nli", description="NEIROLINKS Installer / Updater")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="Persistent config under /mnt/data/etc/neiro/nli/")
    parser.add_argument("--json", action="store_true", help="Emit complete audit record, including read-only operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for command in ("check", "update", "verify", "rollback"):
        sub.add_parser(command).add_argument("component")
    sub.add_parser("firmware").add_argument("action", choices=("check", "update", "recover"))
    args = parser.parse_args(argv)
    try:
        e = engine or Engine(load_config(args.config))
        if args.command == "firmware":
            result = Firmware(e).execute(args.action)
        elif args.command in ("update", "rollback"):
            result = e.mutate(args.command, args.component)
        else:
            result = e.read_operation(args.command, getattr(args, "component", None))
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        result = {"final_status": "failed", "error": str(exc)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("NLI " + __version__)
        for k in ("object", "role", "hostname", "command", "component", "from_version", "to_version",
                  "preflight", "backup", "install", "verify", "rollback", "error", "reason", "output_log"):
            if result.get(k) is not None:
                print(k + ": " + str(result[k]))
        if "components" in result:
            for name, state in result["components"].items():
                print(name + ": " + (state["manifest"]["version"] + " / " + state.get("last_result", "unknown")
                                      if state else "not registered as installed; baseline check required"))
        if result.get("pending"):
            print("RECOVERY REQUIRED: " + json.dumps(result["pending"], ensure_ascii=False))
        for component, record in result.get("last_operations", {}).items():
            print("Last " + str(component) + ": " + record["command"] + " / " + record["final_status"])
        for attempt in result.get('verification_attempts', []):
            for event in attempt.get('journal', []):
                print('JOURNAL ' + event['category'] + ': ' + event['message'])
        print("RESULT: " + result["final_status"])
    return 0 if result["final_status"] == "ok" else (3 if result["final_status"] == "unavailable" else 1)


if __name__ == "__main__":
    sys.exit(main())
