import os

import requests

WEB_SERVICE_URL = os.environ["WEB_SERVICE_URL"]
CRON_SECRET = os.environ["CRON_SECRET"]


def main():
    response = requests.post(
        f"{WEB_SERVICE_URL}/api/descarga-mensual",
        headers={"X-Cron-Secret": CRON_SECRET},
        timeout=300,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
