#! /usr/bin/env bash
# Use curl to fetch the first few layers of map tiles so the map is ready to use.

HOST="https://127.0.0.1:8084"

Help() {
  # Display Help
  echo "Fetch several lays of map tiles to initialize map tile data."
  echo
  echo "Syntax: initialize_map_tiles.sh [-h] [-H HOST]"
  echo "options:"
  echo "h     Print this help."
  echo "b     The hostname to fetch tiles from. (default: ${HOST})"
  echo
}

while getopts ":hH:" option; do
  case $option in
  h) # display Help
    Help
    exit
    ;;
  H)
    HOST="${OPTARG}"
    ;;
  *) # invalid argument(s)
    echo "Error: Invalid option"
    exit 1
    ;;
  esac
done

# Try to fetch the first tile multiple times if the service is starting, or if new map was imported.
for i in {1..100}; do
    # Try to fetch the first tile.
    wget "${HOST}/hot/3/0/0.png" \
      --quiet \
      --tries=1 \
      --no-check-certificate \
      --timeout 5 -O /dev/null || {
        echo "Attempt $i failed. Sleeping for 5 seconds..."
        sleep 5
        continue
    }
    # If we reach here, wget succeeded, so we exit the loop
    break
done

# If we've made it through all attempts, curl never succeeded
if [[ $i -eq $ATTEMPTS ]]; then
    echo "Failed to fetch the image after $ATTEMPTS attempts."
    exit 1
fi

echo "Fetching first map tile succeeded."

curl -ks \
  "${HOST}/hot/3/{0..7}/{0..7}.png" \
  "${HOST}/hot/4/{0..15}/{0..15}.png" \
  "${HOST}/hot/5/{0..31}/{0..31}.png" \
  "${HOST}/hot/6/{0..41}/{0..41}.png" >/dev/null 2>&1
echo "Fetching many map tiles completed."
