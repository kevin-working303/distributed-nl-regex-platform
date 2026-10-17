#!/usr/bin/env python
"""Generate a sizeable sample CSV (and optionally upload it to S3) so you can
demonstrate the pipeline on millions of rows.

Usage:
    python scripts/generate_sample_data.py --rows 2000000 --out sample.csv
    python scripts/generate_sample_data.py --rows 2000000 --out sample.csv \
        --upload --bucket my-bucket --key data/sample.csv \
        --access-key ... --secret-key ... --region us-east-1

No third-party deps required for generation (uses the stdlib csv module).
"""
import argparse
import csv
import random
import sys

FIRST = ["John", "Jane", "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry"]
LAST = ["Doe", "Smith", "Brown", "Johnson", "Williams", "Jones", "Garcia", "Miller", "Davis", "Lee"]
DOMAINS = ["example.com", "domain.com", "website.org", "mail.net", "corp.io"]


def gen_rows(n: int):
    for i in range(1, n + 1):
        first = random.choice(FIRST)
        last = random.choice(LAST)
        name = f"{first} {last}"
        sep = random.choice([".", "_", ""])
        email = f"{first.lower()}{sep}{last.lower()}@{random.choice(DOMAINS)}"
        phone = f"+1 ({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        yield [i, name, email, phone]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=1_000_000)
    p.add_argument("--out", default="sample.csv")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--bucket")
    p.add_argument("--key", default="sample.csv")
    p.add_argument("--access-key")
    p.add_argument("--secret-key")
    p.add_argument("--region")
    args = p.parse_args()

    print(f"Writing {args.rows:,} rows to {args.out} …", file=sys.stderr)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Name", "Email", "Phone"])
        for row in gen_rows(args.rows):
            w.writerow(row)
    print("Done.", file=sys.stderr)

    if args.upload:
        import boto3

        if not (args.bucket and args.access_key and args.secret_key):
            sys.exit("--upload requires --bucket, --access-key and --secret-key")
        print(f"Uploading to s3://{args.bucket}/{args.key} …", file=sys.stderr)
        s3 = boto3.client(
            "s3",
            aws_access_key_id=args.access_key,
            aws_secret_access_key=args.secret_key,
            region_name=args.region,
        )
        s3.upload_file(args.out, args.bucket, args.key)
        print("Uploaded.", file=sys.stderr)


if __name__ == "__main__":
    main()
