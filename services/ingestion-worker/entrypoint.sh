#!/bin/sh
# Runs the worker and then waits LOG_LINGER_SECONDS before the container stops.
# Alloy looks for new containers every few seconds and a run lasts one to three, so without the
# wait the container is gone before its logs are read. The exit code of the worker is kept.
python -m ingestion_worker.main "$@"
code=$?
sleep "${LOG_LINGER_SECONDS:-0}"
exit "$code"
