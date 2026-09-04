# roombook
Books a study room at the University of Glasgow automatically.

The booking system opens a 7-day window at midnight. This runs on a systemd
timer at 23:59:55, logs in, polls until the room is free, and books it.

One instance per person.

Polls rather than firing once at midnight to lower the chance of failure.
A tighter countdown with a single fire is the next thing to try.



## History

First version was written in November 2025 and ran on my main computer. Runing on cron job. It worked,
but it was a single script with credentials and settings hardcoded, no version
control.

Second version was automated on systemd on a Raspberry pi and the configuration spread across four directories that only existed
because I had put them there by hand.

Currently on version 3.

## Where it runs

Anything that stays on overnight works, a Pi, a spare box, a small VPS. It just
needs Python and systemd.

The machine has to be awake every
night. So V1 I had to disable Suspend on my Desktop which was energy draining. V2 was to fix this.

It now runs in a Proxmox LXC on the management VLAN alongside my other automation. The container doesn't need to be big.



## How it works

### [main.py](src/main.py)

1. First login via the `/timetable/login` API endpoint. This takes a JSON body
   with a username and password.

2. Then `/timetable/bookingv2/findrooms` with the room ID, date and time range.
   Returns a list of matching rooms, or an empty list if nothing is free. This
   runs in a loop, up to `max_retry` times with `retry_delay` between attempts,
   until a room comes back.

3. Finally `/timetable/bookingv2` to book. The slots are sent as a list of
   half-hour timestamps, so a 10:00–12:00 booking becomes four entries: 10:00,
   10:30, 11:00 and 11:30.

Note:

All three share one `requests.Session()`, so the cookie set at login carries
through the next two requests.

The API stores times in UTC and displays them in local time. During BST the script has to send local time minus one hour, which is what
`findrooms_hour_offset = -1` does.
But the time of this change was not exact, because I added this during march 2026 when I got fail bookings few days before the switch, so I suspect that it was done manually on server side. 

### Timer

The timer fires at 23:59:55, not at midnight. Login takes around two seconds, so
starting at midnight would mean still authenticating while the window is already
open.

- `AccuracySec=1s` - systemd batches timers into a one-minute window by default
  to save power. Turned off here, the exact second matters.
- `RandomizedDelaySec=0` - jitter exists so a fleet of machines doesn't hit a
  server at the same moment. Don't need it.
- `Persistent=false` - a missed run replayed hours later would request a date
  outside the booking window. Better to just skip a night.

If no room appears within the retry budget, it raises and exits non-zero, so systemd marks the unit failed and the journal has the traceback.

## Install

Needs Python 3.11+ (for `tomllib`), `requests`, systemd, and the host timezone
set to `Europe/London`.

```bash
sudo timedatectl set-timezone Europe/London
sudo apt install -y python3-requests

git clone https://github.com/chmagnus/roombook.git
cd roombook
sudo make install
```

This creates the `roombook` service account, installs the script to
`/opt/roombook`, creates `/etc/roombook` with the right ownership, and installs
the systemd units. It does not write any config or credentials.

OK to re-run, use it to deploy script changes.

To remove:

```bash
sudo make uninstall
```

`/etc/roombook` is left behind, so an uninstall never deletes
credentials.

## Setup

First copy the config:

```bash
sudo cp config/config.example.toml /etc/roombook/config.toml
sudo nano /etc/roombook/config.toml
```
Room IDs are in [docs/rooms.md](docs/rooms.md).

Then one profile per person. `NAME` becomes the systemd instance name, so keep
it short, like initials:

```bash
sudo cp config/profile.example.toml /etc/roombook/profiles/NAME.toml
sudo nano /etc/roombook/profiles/NAME.toml
```

Credentials, two files per person. These are read by systemd as root and passed
to the script through `$CREDENTIALS_DIRECTORY`, so the service user never has
read access to them on disk:

```bash
sudo nano /etc/roombook/creds/NAME.guid
sudo nano /etc/roombook/creds/NAME.password
sudo chmod 600 /etc/roombook/creds/NAME.*
```

Enable:

```bash
sudo systemctl enable --now roombook@NAME.timer
systemctl list-timers 'roombook@*'
```

## Day to day

If you want to change a room or time just edit the profile, nothing else. The script reads it
fresh on every run:

```bash
sudo nano /etc/roombook/profiles/NAME.toml
```

For changing the schedule, use a drop in:

```bash
sudo systemctl edit roombook@.timer
```

For test run without waiting:

```bash
sudo systemctl start roombook@NAME.service
journalctl -u roombook@NAME.service -n 40
```
Note: you might need to switch the days ahead back to 7 for testing.

