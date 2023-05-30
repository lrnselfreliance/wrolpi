#! /usr/bin/env bash
# This should not be used outside the Zim docker container!!

# This file echos and imports Zim files.

echo Importing zim $*
kiwix-manage /library.xml add $*
