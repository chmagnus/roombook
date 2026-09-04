"""
JMS Roombooking with API requests 

login_url = "https://frontdoor.spa.gla.ac.uk/timetable/login"
findrooms_url = "https://frontdoor.spa.gla.ac.uk/timetable/bookingv2/findrooms"
book_url = "https://frontdoor.spa.gla.ac.uk/timetable/bookingv2"
"""


import os
import sys
import tomllib
import requests
import logging
import time
import argparse
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path

# Logging
def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

server_log = logging.getLogger("server")
client_log = logging.getLogger("client")


# Creds
def read_secret(name):
    return (Path(os.environ["CREDENTIALS_DIRECTORY"]) / name).read_text().strip()

# CLI args
def parse_args():
    ap = argparse.ArgumentParser(description="Book a room for a single profile.")
    ap.add_argument("--config", required=True, help="Shared config TOML")
    ap.add_argument("--profile", required=True, help="Per-person profile TOML")
    return ap.parse_args()


"""
Main Booking Process
"""
def main(config_path, profile_path):
        
    configure_logging()

    # get creds
    GUID = read_secret("guid")
    PASSWORD = read_secret("password")

    # Configs
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    with open(profile_path, "rb") as f:
        profile = tomllib.load(f)

    # Shared settings
    base_url = config["base_url"].rstrip("/")
    max_retry = config["max_retry"]
    retry_delay = config["retry_delay"]
    timeout = config["timeout"]
    days_ahead = config["booking_days_ahead"]
    hour_offset = config["findrooms_hour_offset"]

    # Per-person settings
    room_id = profile["room_id"]
    start_time = profile["start_time"]
    end_time = profile["end_time"]
    attendees = profile["attendees"]

    # Build urls
    login_url = f"{base_url}/login"
    findrooms_url = f"{base_url}/bookingv2/findrooms"
    book_url = f"{base_url}/bookingv2"

    # Build date
    booking_date = (datetime.now().date() + timedelta(days=days_ahead)).strftime("%d %b %Y")

    client_log.info("<<<<<<<<<<<<< Booking sequence initiated >>>>>>>>>>>>>")
    s = requests.Session()

    # Generated block for dropping connection
    s.headers.update({"Connection": "close"})  # helps with RemoteDisconnected
    retries = Retry(
        total=3,         # how many internal retries per request
        connect=3,
        read=3,
        backoff_factor=0.5,
        allowed_methods=frozenset(["POST"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))


    room_free = False

    # Login page
    login_payload = {"guid": GUID, "password": PASSWORD, "rememberMe": True}
    r = s.post(login_url, json = login_payload, timeout = 30)

    client_log.info("Logging in...")
    server_log.info(f"Login status={r.status_code} {r.reason}")

    # Offset applied to both payloads. API stores UTC, displays local time,
    # so send local minus one hour during BST. See config.example.toml.
    room_payload = {
                "location": room_id,
                "bookingDate": booking_date,
                "startTime": f'{int(start_time[:2]) + hour_offset:02d}{start_time[2:]}',
                "endTime": f'{int(end_time[:2]) + hour_offset:02d}{end_time[2:]}',
                "attendees": attendees
                }
   
    client_log.info("Finding room...")

    # Check room loop
    for attempt in range(1,max_retry+1):
        r = s.post(findrooms_url, json = room_payload, timeout = 30)

        """
        For one room search (this script),
        if room is empty, 
        the return Json would be [].
        """

        data = r.json()
        if isinstance(data, list) and data:
            room_free = True
            client_log.info("Room found")
            server_log.info(f"Findrooms status={r.status_code} {r.reason}")
            break
        
        client_log.info(f"Attempt {attempt}, room not available.")
        time.sleep(retry_delay)

    if not room_free:
        raise Exception("Room never became free")

    # Book room
    dates = [(datetime.strptime(booking_date, "%d %b %Y").replace(hour=int(start_time[:2]) + hour_offset, minute=int(start_time[3:])) + timedelta(minutes=30*i)).strftime("%Y-%m-%d %H:%M")
            for i in range(int((datetime.strptime(booking_date, "%d %b %Y").replace(hour=int(end_time[:2]) + hour_offset, minute=int(end_time[3:])) - datetime.strptime(booking_date, "%d %b %Y").replace(hour=int(start_time[:2]) + hour_offset, minute=int(start_time[3:]))).total_seconds() // 1800))]    
    booking_payload = {
            "dates": dates,
            "attendees": attendees,
            "locationId": room_id
        }


    client_log.info("Booking room...")
    t0 = time.time()
    r = s.post(book_url, json=booking_payload, timeout=timeout)
    server_log.info(f"Bookroom status={r.status_code} {r.reason} (took {time.time()-t0:.3f}s)")

    if not r.ok:
        raise Exception(f"Booking failed: {r.status_code} {r.reason}")

    client_log.info(f"Booked {room_id} on {booking_date}, sent {dates[0]} to {dates[-1]}")
    client_log.info("<<<<<<<<<<<<< Booking sequence ended >>>>>>>>>>>>>")

"""
Run the booking
"""
def run():
    try:
        args = parse_args()
        main(args.config, args.profile)
    except Exception:
        client_log.exception("Booking failed")
        return 1

if __name__ == "__main__":
    raise SystemExit(run())
