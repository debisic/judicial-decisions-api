#!/bin/sh

python pipeline.py

# Keep container alive after script runs
tail -f /dev/null

