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
ATTEMPTS=100
for i in {1..100}; do
    # Try to fetch the first tile.
    wget "${HOST}/hot/3/0/0.png" \
      --quiet \
      --tries=1 \
      --no-check-certificate \
      --timeout 5 -O /dev/null || {
        echo "Waiting for map to come up, sleeping for 5 seconds..."
        sleep 5
        continue
    }
    # If we reach here, wget succeeded, so we exit the loop
    break
done

# If we've made it through all attempts, curl never succeeded
if [[ $i -eq $ATTEMPTS ]]; then
    echo "Failed to fetch the image after $ATTEMPTS attempts."
    echo "  You can try resetting your map using /opt/wrolpi/scripts/reset_map.sh then importing a map again."
    exit 1
fi

echo "Fetching first map tile succeeded."


# Function to fetch and count downloads
fetch_and_count() {
    local level=$1
    local max_x=$2
    local max_y=$3

    local success_count=0
    local failure_count=0

    for x in $(seq 0 $max_x); do
        for y in $(seq 0 $max_y); do
            if wget -q --spider --no-check-certificate "${HOST}/hot/${level}/${x}/${y}.png"; then
                ((success_count++))
            else
                ((failure_count++))
            fi
        done
    done

    echo "Level $level - Successful downloads: $success_count"
}

# Fetch all tiles from each level so the map is ready to use.
fetch_and_count 3 7 7
fetch_and_count 4 15 15
fetch_and_count 5 31 31
fetch_and_count 6 41 41