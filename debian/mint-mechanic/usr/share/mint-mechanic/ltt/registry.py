"""Data-driven feature registry (design principle P4).

Each toggle/app row is a plain dict consumed by one generic row builder, so
adding a feature is adding a data row — not new UI plumbing. This is the clean
pattern lifted from ATT's newer tabs. Phase 0 defines the data + shape; the
generic GTK row builder lands with the Services view in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceRow:
    key: str            # stable id
    label: str          # shown to the user
    unit: str           # systemd unit name
    description: str     # one-line what/why
    packages: list[str] = field(default_factory=list)  # provides the unit, if optional


# A conservative starter set of common, GUI-worthy services Mint has no toggle
# for. Curated, not exhaustive — rows get added as data, never as new code.
SERVICES: tuple[ServiceRow, ...] = (
    ServiceRow("bluetooth", "Bluetooth", "bluetooth.service",
               "Bluetooth device support."),
    ServiceRow("cups", "Printing (CUPS)", "cups.service",
               "Local and network printing."),
    ServiceRow("ssh", "SSH server", "ssh.service",
               "Incoming remote shell access.", ["openssh-server"]),
    ServiceRow("smbd", "File sharing (Samba)", "smbd.service",
               "Windows-style network file shares.", ["samba"]),
    ServiceRow("avahi", "Zeroconf (Avahi)", "avahi-daemon.service",
               "Local .local network discovery."),
)


def services() -> tuple[ServiceRow, ...]:
    return SERVICES
