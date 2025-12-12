#!/bin/bash
# Integration tests for WROLPi Controller
#
# This script tests that the Controller service is running and responding correctly.
# It can be run against a local development environment or a production deployment.
#
# Usage:
#   ./scripts/test_controller_integration.sh
#   CONTROLLER_URL=http://192.168.1.100:8087 ./scripts/test_controller_integration.sh

set -e

CONTROLLER_URL="${CONTROLLER_URL:-http://localhost:8087}"
API_URL="${API_URL:-http://localhost:8081}"

echo "Testing Controller Integration"
echo "=============================="
echo "Controller: $CONTROLLER_URL"
echo "API: $API_URL"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    FAILED=1
}

skip() {
    echo -e "${YELLOW}○ $1 (skipped)${NC}"
}

FAILED=0
TESTS_RUN=0
TESTS_PASSED=0

run_test() {
    local name="$1"
    local cmd="$2"
    TESTS_RUN=$((TESTS_RUN + 1))

    if eval "$cmd" > /dev/null 2>&1; then
        pass "$name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        fail "$name"
        return 1
    fi
}

# Test 1: Controller health
echo "1. Testing Controller health endpoint..."
run_test "Controller health endpoint responds" \
    "curl -sf '$CONTROLLER_URL/api/health'"

# Test 2: Status endpoint
echo ""
echo "2. Testing status endpoints..."
STATUS=$(curl -sf "$CONTROLLER_URL/api/status" 2>/dev/null || echo '{}')

if echo "$STATUS" | grep -q '"cpu"'; then
    pass "Status endpoint returns CPU data"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Status endpoint missing CPU data"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if echo "$STATUS" | grep -q '"memory"'; then
    pass "Status endpoint returns memory data"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Status endpoint missing memory data"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if echo "$STATUS" | grep -q '"load"'; then
    pass "Status endpoint returns load data"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Status endpoint missing load data"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 3: Individual status endpoints
echo ""
echo "3. Testing individual status endpoints..."
run_test "CPU status endpoint" \
    "curl -sf '$CONTROLLER_URL/api/status/cpu'"

run_test "Memory status endpoint" \
    "curl -sf '$CONTROLLER_URL/api/status/memory'"

run_test "Load status endpoint" \
    "curl -sf '$CONTROLLER_URL/api/status/load'"

run_test "Network status endpoint" \
    "curl -sf '$CONTROLLER_URL/api/status/network'"

run_test "Power status endpoint" \
    "curl -sf '$CONTROLLER_URL/api/status/power'"

# Test 4: Services endpoint
echo ""
echo "4. Testing services endpoint..."
SERVICES=$(curl -sf "$CONTROLLER_URL/api/services" 2>/dev/null || echo '[]')

if [ "$SERVICES" != "[]" ] && echo "$SERVICES" | grep -qE '\[|{'; then
    pass "Services endpoint returns data"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    # May return empty list or error in Docker mode without socket
    skip "Services endpoint (may require Docker socket or systemd)"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 5: Disks endpoint
echo ""
echo "5. Testing disks endpoints..."
DISKS_RESPONSE=$(curl -sf "$CONTROLLER_URL/api/disks" 2>/dev/null)
DISKS_STATUS=$?

if [ $DISKS_STATUS -eq 0 ]; then
    pass "Disks endpoint responds"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    # May return 501 in Docker mode
    DISKS_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "$CONTROLLER_URL/api/disks" 2>/dev/null || echo "000")
    if [ "$DISKS_CODE" = "501" ]; then
        skip "Disks endpoint (not available in Docker mode)"
    else
        fail "Disks endpoint failed"
    fi
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 6: UI accessibility
echo ""
echo "6. Testing Controller UI..."
UI=$(curl -sf "$CONTROLLER_URL/" 2>/dev/null || echo '')
if echo "$UI" | grep -q "WROLPi Controller"; then
    pass "Controller UI loads"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Controller UI failed to load"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 7: Info endpoint
echo ""
echo "7. Testing info endpoint..."
INFO=$(curl -sf "$CONTROLLER_URL/api/info" 2>/dev/null || echo '{}')
if echo "$INFO" | grep -q '"version"'; then
    pass "Info endpoint returns version"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    fail "Info endpoint missing version"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 8: OpenAPI documentation
echo ""
echo "8. Testing OpenAPI documentation..."
run_test "OpenAPI JSON endpoint" \
    "curl -sf '$CONTROLLER_URL/openapi.json'"

# Test 9: Nginx routing (if available)
echo ""
echo "9. Testing nginx routing (optional)..."
NGINX_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "https://localhost/api/status" --insecure 2>/dev/null || echo "000")
if [ "$NGINX_STATUS" = "200" ]; then
    pass "Nginx routes /api/status to Controller"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
else
    skip "Nginx routing (nginx not available or HTTPS not configured)"
fi

# Test 10: Main API still works (if available)
echo ""
echo "10. Testing main API (optional)..."
API_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$API_URL/api/echo" 2>/dev/null || echo "000")
if [ "$API_STATUS" = "200" ]; then
    pass "Main API responds"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
else
    skip "Main API (not running or not accessible)"
fi

# Summary
echo ""
echo "=============================="
echo "Tests run: $TESTS_RUN"
echo "Tests passed: $TESTS_PASSED"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All required tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
