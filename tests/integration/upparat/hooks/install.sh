#!/usr/bin/env bash
# Installs the provided file
#
# $1: timestamp from first call
# $2: retry count
# $3: meta from job document
# $4: file location

echo "Installing"
sleep 1
echo  "10%"
sleep 1
echo  "50%"
sleep 1
echo "100%"
cp $4 /tmp/demo.install
echo "Done!"
