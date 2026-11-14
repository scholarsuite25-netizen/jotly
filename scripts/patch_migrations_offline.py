"""One-time patcher: makes all migration upgrades runnable in Alembic offline mode
so the full PostgreSQL schema (including RLS policies) can be generated as a single
SQL file for the Supabase SQL Editor."""

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "apps" / "api" / "migrations" / "versions"

pattern = re.compile(
    r"    bind = op\.get_bind\(\)\n"
    r"    if bind\.dialect\.name == \"postgresql\":\n"
    r"        for stmt in (\w+)\(\):\n"
    r"            op\.execute\(stmt\)\n"
)

replacement = (
    "    from alembic import context as _ctx\n"
    "    if _ctx.is_offline_mode():\n"
    "        for stmt in {fn}():\n"
    "            op.execute(stmt)\n"
    "    else:\n"
    "        bind = op.get_bind()\n"
    "        if bind.dialect.name == \"postgresql\":\n"
    "            for stmt in {fn}():\n"
    "                op.execute(stmt)\n"
)

patched = 0
for path in sorted(VERSIONS.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    matches = pattern.findall(text)
    if not matches:
        continue
    def _sub(m: re.Match) -> str:
        return replacement.format(fn=m.group(1))
    new_text, n = pattern.subn(_sub, text)
    if n:
        path.write_text(new_text, encoding="utf-8", newline="\n")
        patched += n
        print(f"patched {path.name}: {n} site(s)")

print(f"total patched sites: {patched}")
