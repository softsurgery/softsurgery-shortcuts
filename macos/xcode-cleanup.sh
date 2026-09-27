#!/bin/zsh

set -e

DEVICE_SUPPORT="$HOME/Library/Developer/Xcode/iOS DeviceSupport"

echo "🧹 Xcode cleanup"
echo "================"
echo

DRY_RUN=false

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN — nothing will be deleted"
    echo
fi

remove_path() {
    local path="$1"

    if $DRY_RUN; then
        echo "  Would remove: $path"
    else
        rm -rf "$path"
    fi
}

# --------------------------------------------------
# 1. Remove unavailable simulators
# --------------------------------------------------

echo "📱 Removing unavailable simulators..."

if $DRY_RUN; then
    echo "  Would run: xcrun simctl delete unavailable"
else
    xcrun simctl delete unavailable 2>/dev/null || true
fi

echo

# --------------------------------------------------
# 2. Keep newest DeviceSupport version for each
#    device model
# --------------------------------------------------

if [[ -d "$DEVICE_SUPPORT" ]]; then

    echo "📦 Checking iOS DeviceSupport..."

    typeset -A newest
    typeset -A newest_version

    for dir in "$DEVICE_SUPPORT"/*(/); do

        name="${dir:t}"

        # Extract:
        # model = iPhone15,3
        # version = 26.5.2
        #
        # Example:
        # iPhone15,3 26.5.2 (23F84)

        if [[ "$name" =~ '^(.+) ([0-9]+\.[0-9]+(\.[0-9]+)?) \(' ]]; then

            model="${match[1]}"
            version="${match[2]}"

            if [[ -z "${newest_version[$model]}" ||
                  "$version" > "${newest_version[$model]}" ]]; then

                newest[$model]="$dir"
                newest_version[$model]="$version"
            fi
        fi
    done

    for dir in "$DEVICE_SUPPORT"/*(/); do

        name="${dir:t}"

        if [[ "$name" =~ '^(.+) ([0-9]+\.[0-9]+(\.[0-9]+)?) \(' ]]; then

            model="${match[1]}"

            if [[ "$dir" != "${newest[$model]}" ]]; then

                echo "  Removing old: $name"
                remove_path "$dir"

            else

                echo "  Keeping:       $name"

            fi
        fi
    done

else

    echo "  DeviceSupport directory not found."

fi

echo

# --------------------------------------------------
# 3. Clean Yarn cache
# --------------------------------------------------

if command -v yarn >/dev/null 2>&1; then

    echo "🧶 Cleaning Yarn cache..."

    if $DRY_RUN; then
        echo "  Would run: yarn cache clean"
    else
        yarn cache clean || true
    fi

else

    echo "🧶 Yarn not installed — skipping."

fi

echo

# --------------------------------------------------
# 4. Clean CoreSimulator cache
# --------------------------------------------------

SIM_CACHE="/Library/Developer/CoreSimulator/Caches"

if [[ -d "$SIM_CACHE" ]]; then

    echo "📱 Cleaning CoreSimulator cache..."

    if $DRY_RUN; then
        echo "  Would clean: $SIM_CACHE"
    else
        sudo rm -rf "$SIM_CACHE"/*
    fi

fi

echo
echo "================"
echo "✅ Cleanup finished"
echo

df -h /
