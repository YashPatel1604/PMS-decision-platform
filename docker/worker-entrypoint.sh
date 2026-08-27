#!/bin/sh
set -eu
cd /app
exec pms-platform worker
