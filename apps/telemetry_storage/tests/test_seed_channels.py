import xml.etree.ElementTree as SysET
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.telemetry_storage.models import TelemetryChannel


@pytest.fixture
def mock_pui_list_xml() -> str:
    return """<?xml version="1.0"?>
<ISSLivePUIList>
    <Discipline name="EVA">
        <Symbol>
            <Public_PUI>NODE3000004</Public_PUI>
            <Description>Urine Processor Assembly</Description>
            <OPS_NOM>UPA_STATUS</OPS_NOM>
            <ENG_NOM>UPA Status Eng</ENG_NOM>
            <UNITS>Status</UNITS>
        </Symbol>
        <Symbol>
            <Public_PUI>AIRLOCK000001</Public_PUI>
            <Description>Airlock Power</Description>
            <OPS_NOM>AL_POWER</OPS_NOM>
            <ENG_NOM>AL Power Eng</ENG_NOM>
            <UNITS>Volts</UNITS>
        </Symbol>
    </Discipline>
</ISSLivePUIList>
"""


@pytest.mark.django_db
def test_seed_channels_command(mock_pui_list_xml: str) -> None:
    real_tree = SysET.parse(StringIO(mock_pui_list_xml))

    with (
        patch(
            "apps.telemetry_storage.management.commands.seed_channels.open"
        ) as mock_open,
        patch(
            "apps.telemetry_storage.management.commands.seed_channels.ET.parse"
        ) as mock_parse,
    ):
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parse.return_value = real_tree

        out = StringIO()
        call_command("seed_channels", stdout=out)

        output = out.getvalue()
        assert "Successfully processed 2 channels" in output
        assert "Verification passed: Only NODE3000004 is active" in output

        assert TelemetryChannel.all_objects.count() == 2  # type: ignore[misc]

        upa = TelemetryChannel.objects.get(public_pui="NODE3000004")
        assert upa.description == "Urine Processor Assembly"
        assert upa.ops_nom == "UPA_STATUS"
        assert upa.deleted_at is None

        with pytest.raises(TelemetryChannel.DoesNotExist):
            TelemetryChannel.objects.get(public_pui="AIRLOCK000001")

        airlock = TelemetryChannel.all_objects.get(public_pui="AIRLOCK000001")  # type: ignore[misc]
        assert airlock.description == "Airlock Power"
        assert airlock.deleted_at is not None


@pytest.mark.django_db
def test_seed_channels_idempotency(mock_pui_list_xml: str) -> None:
    real_tree = SysET.parse(StringIO(mock_pui_list_xml))

    with (
        patch(
            "apps.telemetry_storage.management.commands.seed_channels.open"
        ) as mock_open,
        patch(
            "apps.telemetry_storage.management.commands.seed_channels.ET.parse"
        ) as mock_parse,
    ):
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        mock_parse.return_value = real_tree

        out = StringIO()

        call_command("seed_channels", stdout=out)
        assert TelemetryChannel.all_objects.count() == 2  # type: ignore[misc]

        call_command("seed_channels", stdout=out)
        assert TelemetryChannel.all_objects.count() == 2  # type: ignore[misc]
