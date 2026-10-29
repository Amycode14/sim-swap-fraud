"""Consistent SQLite demo backup via backup API (never copy a live database file)."""
import argparse
import sqlite3
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--source',default='data/platform.db')
parser.add_argument('--destination',required=True)
args=parser.parse_args()
if Path(args.destination).exists():raise SystemExit('Destination exists; use a new backup path')
source=sqlite3.connect(args.source)
destination=sqlite3.connect(args.destination)
source.backup(destination)
assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
source.close();destination.close()
print('Consistent database backup created and integrity checked.')
