#!/bin/sh
# Same process tree as Cloud Foundry: the launcher runs `sh -c "<manifest command>"`, and the
# manifest command starts with `exec`, so sh is replaced by celery and receives the signals.
# The flags are the sri-worker flags from manifest.yml.
exec celery -A probe worker --loglevel=info -Q celery,tenant-default,tenant-bulk-scraping --concurrency=2 --max-tasks-per-child=20 --max-memory-per-child=1200000 -O fair --prefetch-multiplier=1
