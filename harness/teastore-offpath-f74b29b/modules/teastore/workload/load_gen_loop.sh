#!/bin/bash
# Robust TeaStore Load Generator (Looping)
# Stateful (cookies) + duration-based looping for experiments.

# 1. Set Defaults
HOST=${1:-localhost}
PROTO=${2:-http}
WEBUI_PORT=${3:-8080}

# Duration/pacing can be controlled via args or env vars.
# Args: <host> <proto> <port> <duration_seconds>
DURATION_SECONDS=${DURATION_SECONDS:-${4:-60}}
SLEEP_BETWEEN_CYCLES_SECONDS=${SLEEP_BETWEEN_CYCLES_SECONDS:-1}

# Persona / journey for multi-user campaigns. TeaStore ships users user1..user90
# (password "password"). JOURNEY selects how far through the funnel a cycle goes:
#   full     = login -> browse -> cart -> checkout -> confirm (default, original)
#   browse   = login -> browse only (no cart/checkout) — read-heavy
#   abandon  = login -> browse -> add to cart, then leave (no checkout)
USERNAME=${USERNAME:-user2}
JOURNEY=${JOURNEY:-full}

BASE_URL="${PROTO}://${HOST}:${WEBUI_PORT}/tools.descartes.teastore.webui"
COOKIE_FILE=$(mktemp)

EXPERIMENT_NAME=${EXPERIMENT_NAME:-""}

function log() {
  local ts
  ts=$(date +"%Y-%m-%dT%H:%M:%S%z")
  if [ -n "$EXPERIMENT_NAME" ]; then
    echo "[${ts}] [${EXPERIMENT_NAME}] $*"
  else
    echo "[${ts}] $*"
  fi
}

log "Target: ${BASE_URL}"
log "Cookie jar: ${COOKIE_FILE}"
log "Duration: ${DURATION_SECONDS}s (sleep_between_cycles=${SLEEP_BETWEEN_CYCLES_SECONDS}s)"

trap "rm -f ${COOKIE_FILE}" EXIT

# --- Helper Functions ---

# Wrapper to execute curl and print: [HTTP CODE] METHOD URL
function req_wrapper() {
  local method=$1
  local url=$2
  shift 2
  local data_args=("$@")

  # We use a separate file descriptor to capture the write-out var separate from body
  # But for simplicity in a load gen, we just capture the status code at the end

  # Run curl, follow redirects (-L), use cookies (-b/-c), silent (-s), output status code (-w)
  # --max-time: a wedged SUT must cost one slow request, not stall the whole
  # cycle (2026-07-18: hung webui -> 3 cycles/300s instead of ~99)
  local response
  response=$(curl -kLs --max-time "${REQ_TIMEOUT_SECONDS:-15}" -o /dev/null -w "%{http_code}" -b "${COOKIE_FILE}" -c "${COOKIE_FILE}" -X "${method}" "${url}" "${data_args[@]}")

  log "👉 [HTTP ${response}] ${method} ${url}"
}

# 2. Health Check
function check_status () {
  log "Checking system status..."
  count=$(curl -kLs --max-time "${REQ_TIMEOUT_SECONDS:-15}" "${BASE_URL}/status" | grep -c "OK")

  if [ "$count" -ge 5 ]; then
    log "System healthy ($count/5 services)"
  else
    log "SYSTEM DEGRADED ($count/5 services online)"
  fi
}

# 3. Load Generation
function run_load () {
  log "Starting load cycle"

  # A. Login
  log "Login as ${USERNAME} (journey=${JOURNEY})"
  req_wrapper POST "${BASE_URL}/loginAction" -d "username=${USERNAME}" -d "password=password" -d "signin=Sign+in"

  # B. Get Categories
  # We fetch the page content specifically here to parse IDs
  PAGE_CONTENT=$(curl -kLs --max-time "${REQ_TIMEOUT_SECONDS:-15}" -b "${COOKIE_FILE}" "${BASE_URL}/")
  CATEGORIES=$(echo "$PAGE_CONTENT" | grep -oE "category=[0-9]+" | grep -oE "[0-9]+" | head -3)

  if [ -z "$CATEGORIES" ]; then
    log "No categories found (WebUI/DB issue)"
  else
    for cat in $CATEGORIES; do
      log "Browse category ${cat}"
      req_wrapper GET "${BASE_URL}/category?category=${cat}&number=30"

      # Get products
      PAGE_CONTENT=$(curl -kLs --max-time "${REQ_TIMEOUT_SECONDS:-15}" -b "${COOKIE_FILE}" "${BASE_URL}/category?category=${cat}&number=30")
      PRODUCTS=$(echo "$PAGE_CONTENT" | grep -oE "product\?id=[0-9]+" | grep -oE "[0-9]+" | head -3)

      for prod in $PRODUCTS; do
        # View Product
        req_wrapper GET "${BASE_URL}/product?id=${prod}"

        # Add to Cart (skip for browse-only journeys)
        if [ "$JOURNEY" != "browse" ]; then
          log "Add product ${prod} to cart"
          req_wrapper POST "${BASE_URL}/cartAction" -d "productid=${prod}" -d "addToCart=Add+to+Cart"
        fi
      done
    done
  fi

  # C. Checkout Flow — only the "full" journey completes the order; "browse"
  # never carts, "abandon" carts then leaves without checkout.
  if [ "$JOURNEY" = "full" ]; then
    log "View cart"
    req_wrapper GET "${BASE_URL}/cart"

    log "Proceed to checkout"
    req_wrapper POST "${BASE_URL}/cartAction" -d "proceedtoCheckout=Proceed+to+Checkout"

    log "Confirm order"
    req_wrapper POST "${BASE_URL}/cartAction" \
         -d "firstname=Jon" \
         -d "lastname=Snow" \
         -d "address1=Winterfell" \
         -d "address2=The+North" \
         -d "cardtype=volvo" \
         -d "cardnumber=314159265359" \
         -d "expirydate=12%2F2025" \
         -d "confirm=Confirm"
  elif [ "$JOURNEY" = "abandon" ]; then
    log "View cart then abandon"
    req_wrapper GET "${BASE_URL}/cart"
  fi

  # D. Return to Home
  log "Return home"
  req_wrapper GET "${BASE_URL}/"

  log "Load cycle complete"
}

# --- Main Execution ---
if ! [[ "$DURATION_SECONDS" =~ ^[0-9]+$ ]] || [ "$DURATION_SECONDS" -le 0 ]; then
  log "Invalid DURATION_SECONDS='${DURATION_SECONDS}' (must be positive int)"
  exit 2
fi

end_ts=$(( $(date +%s) + DURATION_SECONDS ))
cycle=0

check_status

while [ "$(date +%s)" -lt "$end_ts" ]; do
  cycle=$((cycle + 1))
  log "Cycle ${cycle}"
  run_load

  now=$(date +%s)
  if [ "$now" -ge "$end_ts" ]; then
    break
  fi
  sleep "$SLEEP_BETWEEN_CYCLES_SECONDS" || true
done

log "Finished after ${cycle} cycles"
