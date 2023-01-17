#! /bin/bash
set -e
set -x

wget https://github.com/htop-dev/htop/archive/refs/tags/3.2.1.tar.gz -O /tmp/htop-3.2.1.tar.gz
cd /tmp
tar xf /tmp/htop-3.2.1.tar.gz

( cd /tmp/htop-3.2.1 &&
    ./autogen.sh &&
    ./configure --enable-sensors &&
    make -5 &&
    make install
)

