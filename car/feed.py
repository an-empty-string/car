import json
import os
import threading

import requests


def send_feed_data(data):
    for key in ["login_code", "doors", "voters", "turfs"]:
        if key in data["obj"]:
            del data["obj"][key]

    print(f"[feed] {json.dumps(data)}")

    if webhooks := os.getenv("FEED_WEBHOOKS"):
        for hook in webhooks.split(";"):
            threading.Thread(
                target=send_webhook,
                args=(
                    hook,
                    data,
                ),
            ).start()


def send_webhook(url, data):
    requests.post(url=url, json=data, timeout=1)
