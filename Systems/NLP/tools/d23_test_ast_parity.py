#!/usr/bin/env python3
"""Prove semantic equivalence of conflicted test modules from two Git refs."""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys

TEST_PATH = "Systems/NLP/tests/unit/test_length_policy.py"


def tree_source(ref: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{TEST_PATH}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Unable to read test source at {ref}: {result.stderr}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--d22", default="origin/fix/nlp-237-d22-shadow-integrity")
    parser.add_argument("--stage-c", default="origin/fix/nlp-216-length-q04q05q08")
    args = parser.parse_args()
    left = ast.dump(ast.parse(tree_source(args.d22)), include_attributes=False)
    right = ast.dump(ast.parse(tree_source(args.stage_c)), include_attributes=False)
    if left != right:
        print("BLOCKED: test ASTs differ; manual semantic review required", file=sys.stderr)
        return 1
    print(f"PASS: conflicted {TEST_PATH} has identical Python AST on both refs")
    print("This does not establish cable service integration compatibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
