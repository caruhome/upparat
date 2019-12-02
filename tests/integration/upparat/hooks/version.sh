#!/usr/bin/env bash
# Gets the system version
#
# $1: meta from job document

if [[ $1 = "same" ]]; then
   echo "0.1.3"
else
   echo "0.1.2"
fi
