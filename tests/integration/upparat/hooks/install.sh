#!/usr/bin/env bash
# Installs the provided file
#
# $1: meta from job document
# $2: file location

echo "Installing"
sleep 1
echo  "10%"
sleep 1
echo  "50%"
sleep 1
echo "100%"
cp $2 /tmp/demo.install
echo "Done!"
