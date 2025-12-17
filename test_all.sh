#!/bin/bash
#
# Run all WROLPi test suites: pytest, controller, Jest, and Cypress
# Usage: ./test_all.sh [-v|-vv]
#
#   -v   Verbose output
#   -vv  Extra verbose output
#

set -o pipefail

# Parse arguments
VERBOSITY=0
while [[ $# -gt 0 ]]; do
    case $1 in
        -vv)
            VERBOSITY=2
            shift
            ;;
        -v)
            VERBOSITY=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-v|-vv]"
            echo ""
            echo "Options:"
            echo "  -v   Verbose output"
            echo "  -vv  Extra verbose output"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-v|-vv]"
            exit 1
            ;;
    esac
done

# Set verbosity flags for each test runner
if [ $VERBOSITY -eq 2 ]; then
    PYTEST_VERBOSE="-vv"
    JEST_VERBOSE="--verbose"
elif [ $VERBOSITY -eq 1 ]; then
    PYTEST_VERBOSE="-v"
    JEST_VERBOSE="--verbose"
else
    PYTEST_VERBOSE=""
    JEST_VERBOSE=""
fi

# Colors for output (if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    BOLD=''
    NC=''
fi

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Result tracking
PYTEST_RESULT=-1
CONTROLLER_RESULT=-1
JEST_RESULT=-1
CYPRESS_RESULT=-1

# Track if we started Docker
DOCKER_STARTED=false

# Cleanup function
cleanup() {
    if [ "$DOCKER_STARTED" = true ]; then
        echo -e "\n${YELLOW}Stopping Docker services...${NC}"
        cd "$PROJECT_ROOT"
        docker compose down
    fi
}

# Set trap for cleanup on exit or interrupt
trap cleanup EXIT INT TERM

# Print section header
print_header() {
    echo -e "\n${BLUE}${BOLD}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}${BOLD}  $1${NC}"
    echo -e "${BLUE}${BOLD}════════════════════════════════════════════════════════════════${NC}\n"
}

# Print result
print_result() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo -e "${GREEN}✓ $name PASSED${NC}"
    elif [ "$result" -eq -1 ]; then
        echo -e "${YELLOW}○ $name SKIPPED${NC}"
    else
        echo -e "${RED}✗ $name FAILED (exit code: $result)${NC}"
    fi
}

# Check if server is accessible
check_server() {
    curl -k -s -o /dev/null -w "%{http_code}" https://localhost:8443/api/status 2>/dev/null | grep -q "200"
}

# Wait for server to be ready
wait_for_server() {
    local max_attempts=60
    local attempt=1
    echo -e "${YELLOW}Waiting for server to be ready...${NC}"
    while [ $attempt -le $max_attempts ]; do
        if check_server; then
            echo -e "${GREEN}Server is ready!${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo -e "\n${RED}Server did not become ready within timeout${NC}"
    return 1
}

echo -e "${BOLD}WROLPi Test Suite Runner${NC}"
echo "Project root: $PROJECT_ROOT"

# ============================================================================
# 1. Backend pytest
# ============================================================================
print_header "Backend Tests (pytest)"
cd "$PROJECT_ROOT"

START_TIME=$(date +%s)
pytest -nauto $PYTEST_VERBOSE
PYTEST_RESULT=$?
END_TIME=$(date +%s)
echo -e "\n${BLUE}Duration: $((END_TIME - START_TIME)) seconds${NC}"

# ============================================================================
# 2. Controller tests
# ============================================================================
print_header "Controller Tests (pytest)"
cd "$PROJECT_ROOT/controller"

START_TIME=$(date +%s)
if [ -d "venv" ]; then
    source venv/bin/activate
    python -m pytest test/ -nauto --tb=short --confcutdir="$(pwd)" $PYTEST_VERBOSE
    CONTROLLER_RESULT=$?
    deactivate 2>/dev/null || true
else
    python3 -m pytest test/ -nauto --tb=short --confcutdir="$(pwd)" $PYTEST_VERBOSE
    CONTROLLER_RESULT=$?
fi
END_TIME=$(date +%s)
echo -e "\n${BLUE}Duration: $((END_TIME - START_TIME)) seconds${NC}"

# ============================================================================
# 3. Jest tests
# ============================================================================
print_header "Frontend Tests (Jest)"
cd "$PROJECT_ROOT/app"

START_TIME=$(date +%s)
CI=true npm test -- --watchAll=false $JEST_VERBOSE
JEST_RESULT=$?
END_TIME=$(date +%s)
echo -e "\n${BLUE}Duration: $((END_TIME - START_TIME)) seconds${NC}"

# ============================================================================
# 4. Cypress tests
# ============================================================================
print_header "End-to-End Tests (Cypress)"
cd "$PROJECT_ROOT/app"

# Check if server is running
if ! check_server; then
    echo -e "${YELLOW}Server not running. Starting Docker services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose up -d
    DOCKER_STARTED=true

    if ! wait_for_server; then
        echo -e "${RED}Failed to start server. Skipping Cypress tests.${NC}"
        CYPRESS_RESULT=-1
    else
        cd "$PROJECT_ROOT/app"
        START_TIME=$(date +%s)
        npm run cy:run
        CYPRESS_RESULT=$?
        END_TIME=$(date +%s)
        echo -e "\n${BLUE}Duration: $((END_TIME - START_TIME)) seconds${NC}"
    fi
else
    echo -e "${GREEN}Server is already running${NC}"
    START_TIME=$(date +%s)
    npm run cy:run
    CYPRESS_RESULT=$?
    END_TIME=$(date +%s)
    echo -e "\n${BLUE}Duration: $((END_TIME - START_TIME)) seconds${NC}"
fi

# ============================================================================
# Summary
# ============================================================================
print_header "Test Summary"

print_result "Backend (pytest)" $PYTEST_RESULT
print_result "Controller" $CONTROLLER_RESULT
print_result "Frontend (Jest)" $JEST_RESULT
print_result "End-to-End (Cypress)" $CYPRESS_RESULT

echo ""

# Calculate overall result
OVERALL_RESULT=0
[ $PYTEST_RESULT -ne 0 ] && [ $PYTEST_RESULT -ne -1 ] && OVERALL_RESULT=1
[ $CONTROLLER_RESULT -ne 0 ] && [ $CONTROLLER_RESULT -ne -1 ] && OVERALL_RESULT=1
[ $JEST_RESULT -ne 0 ] && [ $JEST_RESULT -ne -1 ] && OVERALL_RESULT=1
[ $CYPRESS_RESULT -ne 0 ] && [ $CYPRESS_RESULT -ne -1 ] && OVERALL_RESULT=1

if [ $OVERALL_RESULT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All tests passed!${NC}"
else
    echo -e "${RED}${BOLD}Some tests failed.${NC}"
fi

exit $OVERALL_RESULT
