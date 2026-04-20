"""Management command that seeds ``TelemetryChannel`` rows from PUIList.xml.

Runs on first deployment (and whenever the PUI list is refreshed) to
populate the ~400 ISS telemetry channels PeeBot subscribes to. Parsing
uses :mod:`defusedxml` to harden against malformed/malicious XML.

In development the command intentionally keeps only ``NODE3000005`` (the
UPA Tank Level channel used by the PeeBot processor) marked active;
every other channel is soft-deleted at seed time so local ingestion
focuses on the one channel the processor actually cares about. Production
seeding is handled the same way today — broaden the active set by
adjusting ``target_active_pui`` once additional processors are wired up.
"""

from typing import Any, cast

import defusedxml.ElementTree as ET
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.telemetry_storage.models import TelemetryChannel


class Command(BaseCommand):
    """``seed_channels`` management command.

    Reads ``docs/PUIList.xml``, upserts a :class:`TelemetryChannel` row
    for every ``<Symbol>`` entry, and soft-deletes channels other than
    the single currently-targeted active channel.
    """

    help = "Seeds telemetry channels from docs/PUIList.xml"

    def handle(self, *args: Any, **options: Any) -> None:
        """Parse the PUI XML and upsert channel rows.

        Emits progress and verification output via ``self.stdout`` /
        ``self.stderr``. Re-raises any unexpected exception after logging
        so calling scripts see a non-zero exit status.
        """
        self.stdout.write("Seeding telemetry channels...")

        # Mypy doesn't see BASE_DIR on LazySettings
        xml_path = cast(Any, settings).BASE_DIR / "docs" / "PUIList.xml"

        if not xml_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {xml_path}"))
            return

        try:
            with open(xml_path, encoding="utf-8") as f:
                tree = ET.parse(f)

            root = tree.getroot()
            if root is None:
                self.stderr.write(self.style.ERROR("Invalid XML: Root element missing"))
                return

            symbols = root.findall(".//Symbol")
            if not symbols:
                self.stdout.write(self.style.WARNING("No symbols found in XML"))
                return

            count = 0
            updated = 0
            created = 0

            now = timezone.now()
            target_active_pui = "NODE3000005"

            for symbol in symbols:
                pui_elem = symbol.find("Public_PUI")
                desc_elem = symbol.find("Description")
                ops_elem = symbol.find("OPS_NOM")
                eng_elem = symbol.find("ENG_NOM")
                unit_elem = symbol.find("UNITS")

                if any(
                    e is None
                    for e in [pui_elem, desc_elem, ops_elem, eng_elem, unit_elem]
                ):
                    self.stdout.write(
                        self.style.WARNING("Skipping incomplete symbol entry")
                    )
                    continue

                public_pui = (
                    pui_elem.text.strip()
                    if pui_elem is not None and pui_elem.text
                    else ""
                )
                description = (
                    desc_elem.text.strip()
                    if desc_elem is not None and desc_elem.text
                    else ""
                )
                ops_nom = (
                    ops_elem.text.strip()
                    if ops_elem is not None and ops_elem.text
                    else ""
                )
                eng_nom = (
                    eng_elem.text.strip()
                    if eng_elem is not None and eng_elem.text
                    else ""
                )
                unit = (
                    unit_elem.text.strip()
                    if unit_elem is not None and unit_elem.text
                    else ""
                )

                deleted_at = None if public_pui == target_active_pui else now

                obj, was_created = TelemetryChannel.all_objects.update_or_create(
                    public_pui=public_pui,
                    defaults={
                        "description": description,
                        "ops_nom": ops_nom,
                        "eng_nom": eng_nom,
                        "unit": unit,
                        "deleted_at": deleted_at,
                    },
                )

                if was_created:
                    created += 1
                else:
                    updated += 1
                count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed {count} channels. "
                    f"Created: {created}, Updated: {updated}."
                )
            )

            active_count = TelemetryChannel.objects.count()
            self.stdout.write(f"Active channels: {active_count}")

            if active_count == 1:
                active_channel = TelemetryChannel.objects.first()
                if active_channel and active_channel.public_pui == target_active_pui:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Verification passed: Only {target_active_pui} is active."
                        )
                    )
                elif active_channel:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Verification failed: Active channel is "
                            f"{active_channel.public_pui}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Verification failed: Unexpected error retrieving "
                            "active channel"
                        )
                    )

            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Verification failed: Expected 1 active channel, "
                        f"found {active_count}"
                    )
                )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error seeding channels: {e!s}"))
            raise
