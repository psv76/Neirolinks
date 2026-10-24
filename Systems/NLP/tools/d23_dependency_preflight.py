#!/usr/bin/env python3
"""Read-only Git merge preflight for independent NLP D22 and Stage C branches.

No checkout, index mutation, merge commit, working SQLite or DWG access.
Requires a repository checkout with both refs fetched.
"""
import argparse
import json
import subprocess
import sys


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--d22", default="origin/fix/nlp-237-d22-shadow-integrity")
    parser.add_argument("--stage-c", default="origin/fix/nlp-216-length-q04q05q08")
    args = parser.parse_args()
    before = git("status", "--porcelain").stdout
    if before.strip():
        print("BLOCKED: worktree is not clean", file=sys.stderr)
        return 2
    refs = {}
    for key, ref in (("d22", args.d22), ("stage_c", args.stage_c)):
        resolved = git("rev-parse", "--verify", f"{ref}^{{commit}}")
        if resolved.returncode:
            print(f"BLOCKED: missing reference: {ref}", file=sys.stderr)
            return 2
        refs[key] = resolved.stdout.strip()
    base = git("merge-base", refs["d22"], refs["stage_c"])
    if base.returncode:
        print("BLOCKED: no merge-base", file=sys.stderr)
        return 2
    probe = git("merge-tree", "--write-tree", refs["d22"], refs["stage_c"])
    if probe.returncode not in (0, 1):
        print(probe.stderr, file=sys.stderr)
        return 2
    after = git("status", "--porcelain").stdout
    if after != before:
        print("BLOCKED: preflight modified working tree", file=sys.stderr)
        return 2
    report = {
        "d22_sha": refs["d22"],
        "stage_c_sha": refs["stage_c"],
        "merge_base_sha": base.stdout.strip(),
        "clean_merge": probe.returncode == 0,
        "conflicted": probe.returncode == 1,
        "merge_tree_output": probe.stdout[-16000:],
        "non_mutating": True,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
