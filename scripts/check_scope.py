"""Repository policy gate (T08/T10/T12 support).

- No AI/LLM/embedding dependencies in M0 lockfiles.
- `.env` is ignored and untracked; `.env.example` holds only `dev-only-` passwords.
- Lightweight secret scan of tracked files: key formats and Luhn-valid PAN candidates.
  This is a heuristic, not a replacement for a dedicated scanner.

Usage: python scripts/check_scope.py [repo_root]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PACKAGES = {
    "openai", "anthropic", "langchain", "langchain-core", "langchain-openai", "langgraph",
    "llama-index", "llama-index-core", "litellm", "cohere", "mistralai", "groq",
    "google-generativeai", "google-genai", "transformers", "sentence-transformers",
    "torch", "tiktoken", "huggingface-hub", "voyageai", "@anthropic-ai/sdk", "ai",
    "@langchain/core", "@google/generative-ai",
}  # fmt: skip

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
}
_PAN_CANDIDATE = re.compile(r"(?<![\w.-])\d(?:[ -]?\d){12,18}(?![\w.-])")
_SKIP_SCAN = {"uv.lock", "package-lock.json"}


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


def tracked_files(root: Path) -> list[Path]:
    proc = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if proc.returncode != 0:
        raise SystemExit("check_scope: git is required to list repository files")
    return [root / line for line in proc.stdout.splitlines() if line and (root / line).is_file()]


def check_dependencies(root: Path) -> list[str]:
    errors = []
    names: set[str] = set()
    lock = root / "uv.lock"
    if lock.exists():
        names |= set(re.findall(r'^name = "([^"]+)"', lock.read_text(encoding="utf-8"), re.M))
    npm_lock = root / "package-lock.json"
    if npm_lock.exists():
        names |= set(
            re.findall(r'"node_modules/((?:@[^/"]+/)?[^/"]+)"', npm_lock.read_text("utf-8"))
        )
    for name in sorted(names & FORBIDDEN_PACKAGES):
        errors.append(f"forbidden AI/LLM dependency in lockfile: {name}")
    return errors


def check_env_files(root: Path, files: list[Path]) -> list[str]:
    errors = []
    rel = {p.relative_to(root).as_posix() for p in files}
    if ".env" in rel:
        errors.append(".env is not ignored by git")
    if _git(root, "check-ignore", "-q", ".env").returncode != 0:
        errors.append(".env must be listed in .gitignore")
    example = root / ".env.example"
    if not example.exists():
        errors.append(".env.example missing")
    else:
        for line in example.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip().endswith("PASSWORD") and not value.strip().startswith("dev-only-"):
                errors.append(f".env.example: {key.strip()} must be a 'dev-only-' placeholder")
    return errors


def scan_secrets(root: Path, files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        if path.name in _SKIP_SCAN:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root).as_posix()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{rel}: possible {label}")
        for match in _PAN_CANDIDATE.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            if 13 <= len(digits) <= 19 and luhn_ok(digits):
                errors.append(f"{rel}: Luhn-valid PAN-like number")
                break
    return errors


def check_repo(root: Path) -> list[str]:
    files = tracked_files(root)
    return check_dependencies(root) + check_env_files(root, files) + scan_secrets(root, files)


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    errors = check_repo(root)
    for error in errors:
        print(f"[FAIL] {error}")
    print(f"policy: {'OK' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
