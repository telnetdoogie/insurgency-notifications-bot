#!/bin/bash
message="$@"

## format to parse to curl
msg_content=\"$message\"

## discord webhook
url='https://discord.com/api/webhooks/<some_webhook_id_here>'

## sending the message to discord
curl -H "Content-Type: application/json" -sS -X POST -d "{\"username\": \"My_Bot_Name\", \"content\": $msg_content}" $url