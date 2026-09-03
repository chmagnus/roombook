PREFIX      := /opt/roombook

CONFDIR     := /etc/roombook
SERVICEUSER := roombook

.PHONY: install uninstall

install:
	# service account: no login shell, no home directory
	id -u $(SERVICEUSER) >/dev/null 2>&1 || \
		useradd --system --no-create-home --shell /usr/sbin/nologin $(SERVICEUSER)

	install -d -m 0755 -o root -g root $(PREFIX)
	install -m 0755 -o root -g root src/main.py $(PREFIX)/

	# group-readable so the service can read config, not writable by it
	install -d -m 0750 -o root -g $(SERVICEUSER) $(CONFDIR)
	install -d -m 0750 -o root -g $(SERVICEUSER) $(CONFDIR)/profiles

	# creds stay root-only, systemd reads them before dropping privileges
	install -d -m 0700 -o root -g root $(CONFDIR)/creds

	install -m 0644 systemd/roombook@.service /etc/systemd/system/
	install -m 0644 systemd/roombook@.timer   /etc/systemd/system/
	systemctl daemon-reload
		
	@echo "Installed. See README for config, credentials and enabling the timer."

uninstall:
	systemctl disable --now 'roombook@*.timer' 2>/dev/null || true
	rm -f /etc/systemd/system/roombook@.service /etc/systemd/system/roombook@.timer
	systemctl daemon-reload
	rm -rf $(PREFIX)
	@echo "Left $(CONFDIR) in place, remove manually if you want the creds gone."
