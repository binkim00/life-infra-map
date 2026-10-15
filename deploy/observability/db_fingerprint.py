"""Compare exact public-table counts while application writers are stopped.

Reads through the existing DB container; never prints data rows or credentials.
This checks logical counts and schema names, not full byte-level row equality.
"""
import argparse
import json
from pathlib import Path
import subprocess


def query(sql):
    command = ["docker", "exec", "-i", "life-infra-map-runtime-db", "sh", "-c",
               'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1']
    result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Read-only DB fingerprint failed; inspect locally without exposing credentials")
    return result.stdout.splitlines()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect", type=Path)
    args = parser.parse_args()
    tables = query("SELECT quote_ident(n.nspname)||'.'||quote_ident(c.relname) "
                   "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                   "WHERE c.relkind='r' AND n.nspname='public' ORDER BY c.relname;")
    statements = ["BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;", "SET LOCAL statement_timeout='30s';"]
    for table in tables:
        literal = table.replace("'", "''")
        statements.append("SELECT json_build_object('table','" + literal + "','rows',count(*)) FROM " + table + ";")
    statements.append("COMMIT;")
    rows = {}
    for line in query("\n".join(statements)):
        if line.startswith("{"):
            item = json.loads(line)
            rows[item["table"]] = item["rows"]
    assert len(rows) == len(tables) and rows
    result = {"table_rows": rows, "table_count": len(rows), "read_only": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True))
    args.output.chmod(0o600)
    if args.expect:
        expected = json.loads(args.expect.read_text())
        assert expected["table_rows"] == rows, "Frozen source and target table counts differ"
    print(json.dumps({"table_count": len(rows), "counts_match_expected": True if args.expect else None}))


if __name__ == "__main__":
    main()
