#!/usr/bin/env bash
# Gets the system version
#
# $1: time elapsed since the first call
# $2: retry count
# $3: meta from job document

if [[ $1 = "same" ]]; then
   echo "0.0.1"
else
   echo "0.0.0"
fi
