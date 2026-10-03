#!/bin/bash

notify=false

if [[ "$1" == "--notify" ]]; then
    notify=true
    shift
fi

message="$*"

## Discord webhook
url='https://discord.com/api/webhooks/<webhook id>'
username='<bot name>'

if $notify; then

    ## Normal Discord notification
    payload=$(jq -n \
        --arg username "$username" \
        --arg content "$message" \
        '{
            username: $username,
            content: $content
        }'
    )

else

    ## Suppress Discord push notification
    payload=$(jq -n \
        --arg username "$username" \
        --arg content "$message" \
        '{
            username: $username,
            flags: 4096,
            content: $content
        }'
    )

fi

curl -sS \
    -H "Content-Type: application/json" \
    -X POST \
    -d "$payload" \
    "$url"