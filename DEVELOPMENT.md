This document contains instructions to set up your system for WROLPi development.

# Setup

## Debian 12

1. Install accessory packages necessary for testing:
    * `sudo apt install ffmpeg chromium chromium-driver sysstat aria2 nodejs npm`
2. Create Python environment:
    * `python -m venv venv`
3. Activate the new environment:
    * `. venv/bin/activate`
4. Build the docker containers:
    * `./scripts/dev_build.sh`
5. Start the docker containers:
    * `docker compose up`
6. Browse to the development containers:
    * https://localhost:8443
7. Install npm dependencies used outside the app:
    * `npm install single-file-cli@2.0.73 readability-extractor@0.0.6`
8. Run the tests. All tests should pass.
    * `pytest`
