# roombook

Books a study room at the University of Glasgow automatically.

The booking system opens a 7-day window at midnight. This runs on a systemd
timer at 23:59:55, logs in, polls until the room is free, and books it.

One instance per person.
