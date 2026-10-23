"""Local, streaming IEEE-CIS onboarding; no cloud calls or model training."""

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

SOURCE = "https://www.kaggle.com/competitions/ieee-fraud-detection/data"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def profile(path: Path, connection: sqlite3.Connection, table: str) -> dict:
    """Validate keys and training labels while retaining only aggregate column statistics."""
    transaction = table == "transactions"
    required = {"TransactionID", "TransactionDT", "isFraud"} if transaction else {"TransactionID"}
    before = checksum(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        names = reader.fieldnames or []
        if not required.issubset(names) or len(names) != len(set(names)):
            raise ValueError("Missing required or duplicate columns")
        if len(names) > 1000:
            raise ValueError("Too many columns")
        missing = dict.fromkeys(names, 0)
        count = 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row")
            key = row["TransactionID"]
            if not key.isascii() or not key.isdecimal() or len(key) > 18:
                raise ValueError("Invalid transaction key")
            key = int(key)
            if transaction:
                try:
                    elapsed = float(row["TransactionDT"])
                except ValueError:
                    raise ValueError("Invalid relative time") from None
                if not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError("Invalid relative time")
                if row["isFraud"] not in {"0", "1"}:
                    raise ValueError("Invalid fraud label")
                connection.execute(
                    "INSERT INTO transactions VALUES (?, ?, ?)",
                    (key, elapsed, int(row["isFraud"])),
                )
            else:
                connection.execute("INSERT INTO identities VALUES (?)", (key,))
            for name, value in row.items():
                missing[name] += value.strip() == ""
            count += 1
    if count == 0:
        raise ValueError("Empty source file")
    if checksum(path) != before:
        raise ValueError("Source changed during profiling")
    return {
        "name": path.name,
        "sha256": before,
        "bytes": path.stat().st_size,
        "rows": count,
        "columns": names,
        "missing_blank_cells": missing,
    }


def run(raw: Path, output: Path, approved_use: str, fraction: float = 0.8) -> dict:
    if not 0 < fraction < 1 or not approved_use.strip():
        raise ValueError("Require approved-use reference and split fraction between zero and one")
    if output.exists():
        raise ValueError("Output must be a new directory")
    # Disk-backed keys bound memory even for the full source. Temporary keys are removed on exit.
    with tempfile.TemporaryDirectory(prefix="ieee-profile-") as scratch:
        with closing(sqlite3.connect(Path(scratch) / "keys.db")) as connection:
            connection.execute(
                "CREATE TABLE transactions (id INTEGER PRIMARY KEY, dt REAL, label INTEGER)"
            )
            connection.execute("CREATE TABLE identities (id INTEGER PRIMARY KEY)")
            try:
                transaction = profile(raw / "train_transaction.csv", connection, "transactions")
                identity = profile(raw / "train_identity.csv", connection, "identities")
            except sqlite3.IntegrityError:
                raise ValueError("Duplicate transaction key") from None
            orphan_count = connection.execute(
                "SELECT count(*) FROM identities i LEFT JOIN transactions t ON i.id=t.id "
                "WHERE t.id IS NULL"
            ).fetchone()[0]
            if orphan_count:
                raise ValueError("Identity rows reference absent training transactions")
            connection.execute("CREATE INDEX time_order ON transactions(dt)")
            boundary = connection.execute(
                "SELECT dt FROM transactions ORDER BY dt LIMIT 1 OFFSET ?",
                (min(int(transaction["rows"] * fraction), transaction["rows"] - 1),),
            ).fetchone()[0]
            partitions = {}
            for name, operator in (("train", "<"), ("validation", ">=")):
                # Operator is an internal constant, never user input.
                count, fraud, start, end = connection.execute(
                    f"SELECT count(*), sum(label), min(dt), max(dt) FROM transactions "
                    f"WHERE dt {operator} ?",
                    (boundary,),
                ).fetchone()
                if not count:
                    raise ValueError("Time split produced an empty partition")
                partitions[name] = {
                    "rows": count,
                    "fraud_rows": fraud,
                    "fraud_rate": fraud / count,
                    "relative_time_min": start,
                    "relative_time_max": end,
                }
            report = {
                "domain": "ieee_cis",
                "source_uri": SOURCE,
                "approved_use": approved_use,
                "transform_version": 1,
                "inputs": [transaction, identity],
                "identity_match_rate": identity["rows"] / transaction["rows"],
                "unmatched_transactions": transaction["rows"] - identity["rows"],
                "time_semantics": "Relative elapsed time; not a calendar timestamp",
                "split": {
                    "boundary": boundary,
                    "train_rule": "TransactionDT < boundary",
                    "validation_rule": "TransactionDT >= boundary",
                    "requested_train_fraction": fraction,
                    "partitions": partitions,
                },
                "limitations": [
                    "Training tables only; competition test tables are not profiled",
                    "Missing counts treat only blank/whitespace cells as missing",
                    "No imputation, encoding, model training, or S3 upload performed",
                ],
            }
            output.mkdir(parents=True)
            with (output / "split_membership.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["TransactionID", "partition"])
                for key, dt in connection.execute("SELECT id, dt FROM transactions ORDER BY dt,id"):
                    writer.writerow([key, "train" if dt < boundary else "validation"])
            (output / "eda.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            lines = [
                "# IEEE-CIS training data EDA",
                "",
                f"Transactions: {transaction['rows']:,}",
                f"Identity match rate: {report['identity_match_rate']:.2%}",
                f"Unmatched transactions retained: {report['unmatched_transactions']:,}",
                "",
                "| Partition | Rows | Fraud rate |",
                "| --- | ---: | ---: |",
            ]
            for name, stats in partitions.items():
                lines.append(f"| {name} | {stats['rows']:,} | {stats['fraud_rate']:.2%} |")
            lines += [
                "",
                "Time ties stay together; no calendar dates are inferred.",
                "",
                "Column missing counts and source checksums are in eda.json.",
                "",
                *report["limitations"],
            ]
            (output / "EDA.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approved-use", required=True, help="Reference to accepted source terms")
    parser.add_argument("--train-fraction", type=float, default=0.8)
    args = parser.parse_args()
    try:
        run(args.raw, args.output, args.approved_use, args.train_fraction)
    except (ValueError, OSError, csv.Error, sqlite3.Error):
        parser.exit(1, "Dataset validation failed; check source files and output configuration.\n")
    print("Completed local IEEE-CIS profiling; no upload or training performed.")
