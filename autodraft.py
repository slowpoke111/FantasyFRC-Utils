import requests
import dotenv
import os

dotenv.load_dotenv()

TBA_KEY = os.getenv("TBA_API_KEY", "")
YEAR = 2026

teams = [
    122, 157, 190,
    316, 321, 341,
    427, 449, 484,
    714, 1218, 2377,
    2539, 3637, 4373,
    5000, 5181, 6328,
    10979
]

headers = {
    "X-TBA-Auth-Key": TBA_KEY
}


def get(url):
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


results = []

for team in teams:
    print(f"Processing {team}")

    teamKey = f"frc{team}"
    highestOpr = None
    highestEvent = None

    try:
        events = get(f"https://www.thebluealliance.com/api/v3/team/{teamKey}/events/{YEAR}")

        for event in events:
            eventKey = event["key"]

            try:
                oprData = get(f"https://www.thebluealliance.com/api/v3/event/{eventKey}/oprs")
                oprs = oprData.get("oprs", {})

                if teamKey in oprs:
                    opr = oprs[teamKey]

                    if highestOpr is None or opr > highestOpr:
                        highestOpr = opr
                        highestEvent = eventKey

            except Exception:
                continue

    except Exception as e:
        print(f"Failed {team}: {e}")

    if highestOpr is None:
        highestOpr = 0

    results.append((team, highestOpr, highestEvent))


results.sort(key=lambda x: x[1], reverse=True)

import pyperclip

output = "Team\tOPR\n"

for team, opr, event in results:
    output += f"{team}\t{opr:.2f}\n"

pyperclip.copy(output)

print("Copied to clipboard!")
