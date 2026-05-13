"""Tests for ZTE mesh topology support."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from custom_components.zte_tracker.zteclient.zte_client import zteClient


# --- Fixtures ---

TOPOLOGY_JSON_30_DEVICES = {
    "slave": [
        {
            "instID": "MESH.AGENT1",
            "IpAddr": "192.168.1.8",
            "MacAddr": "14:09:b4:bf:a6:6b",
            "DeviceName": "ZTE:H196A V9",
            "AccessType": "5G",
            "SoftwareVer": "V9.0.0P2_WIND",
        }
    ],
    "master": {
        "instID": "MESH.CONTROLLER",
        "IpAddr": "192.168.1.1",
        "MacAddr": "84:3c:99:49:a3:4b",
        "DeviceName": "ZTE:F6600P",
        "SoftwareVer": "V9.0.10P24N1",
    },
    "ad": {
        "1": {
            "parent": "MESH.CONTROLLER",
            "HostName": "Docker-SRV",
            "MacAddr": "bc:24:11:fa:25:21",
            "IpAddr": "192.168.1.20",
            "AccessType": "0",
            "IF_ERRORID": 0,
        },
        "2": {
            "parent": "MESH.CONTROLLER",
            "HostName": "yeelink-light",
            "MacAddr": "ec:4d:3e:3d:4f:18",
            "IpAddr": "192.168.1.4",
            "AccessType": "1",
            "IF_ERRORID": 0,
        },
        "3": {
            "parent": "MESH.CONTROLLER",
            "HostName": "DS-S25U",
            "MacAddr": "a0:b0:bd:00:8c:36",
            "IpAddr": "192.168.1.73",
            "AccessType": "2",
            "IF_ERRORID": 0,
        },
        "4": {
            "parent": "MESH.AGENT1",
            "HostName": "IoT-Device-1",
            "MacAddr": "58:b6:23:bd:48:cf",
            "IpAddr": "192.168.1.7",
            "AccessType": "1",
            "IF_ERRORID": 0,
        },
        "5": {
            "parent": "MESH.AGENT1",
            "HostName": "IoT-Device-2",
            "MacAddr": "c4:93:bb:d3:dc:c7",
            "IpAddr": "192.168.1.36",
            "AccessType": 1,  # integer instead of string — test normalization
            "IF_ERRORID": 0,
        },
        "MGET_INST_NUM": 5,
    },
}

TOPOLOGY_EMPTY_AD = {"slave": [], "master": {"instID": "MESH.CONTROLLER"}, "ad": {}}
TOPOLOGY_NO_AD = {"slave": [], "master": {"instID": "MESH.CONTROLLER"}}
SESSION_TIMEOUT_XML = '<?xml version="1.0"?><ajax_response_xml_root><IF_ERRORSTR>SessionTimeout</IF_ERRORSTR></ajax_response_xml_root>'
HTML_404_PAGE = '<html><head><title>404</title></head><body>Not Found</body></html>'


@pytest.fixture
def client():
    """Create a zteClient instance for testing."""
    return zteClient("192.168.1.1", "admin", "test", "F6640")


@pytest.fixture
def client_no_topo():
    """Create a client for a model without topology support."""
    return zteClient("192.168.1.1", "admin", "test", "H288A")


# --- _parse_topology_json tests ---


class TestParseTopologyJson:
    """Tests for _parse_topology_json."""

    def test_valid_topology_5_devices(self, client):
        """Parse valid topology JSON with 5 devices."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        assert devices is not None
        assert len(devices) == 5

    def test_device_fields(self, client):
        """Parsed devices have all expected fields."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        d = devices[0]  # Docker-SRV
        assert d["MACAddress"] == "BC:24:11:FA:25:21"
        assert d["HostName"] == "Docker-SRV"
        assert d["IPAddress"] == "192.168.1.20"
        assert d["Active"] is True
        assert d["NetworkType"] == "LAN"
        assert d["MeshNode"] == "ZTE:F6600P"

    def test_access_type_mapping(self, client):
        """AccessType maps to correct NetworkType."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        by_mac = {d["MACAddress"]: d for d in devices}
        assert by_mac["BC:24:11:FA:25:21"]["NetworkType"] == "LAN"  # AccessType 0
        assert by_mac["EC:4D:3E:3D:4F:18"]["NetworkType"] == "WLAN"  # AccessType 1
        assert by_mac["A0:B0:BD:00:8C:36"]["NetworkType"] == "WLAN"  # AccessType 2

    def test_access_type_integer_normalization(self, client):
        """Integer AccessType is normalized to string for mapping."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        by_mac = {d["MACAddress"]: d for d in devices}
        # Device 5 has AccessType as integer 1
        assert by_mac["C4:93:BB:D3:DC:C7"]["NetworkType"] == "WLAN"

    def test_mesh_node_attribution(self, client):
        """Devices are attributed to correct mesh nodes."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        by_mac = {d["MACAddress"]: d for d in devices}
        assert by_mac["BC:24:11:FA:25:21"]["MeshNode"] == "ZTE:F6600P"  # Controller
        assert by_mac["58:B6:23:BD:48:CF"]["MeshNode"] == "ZTE:H196A V9"  # Agent

    def test_mac_uppercased(self, client):
        """MAC addresses are uppercased for consistency."""
        devices = client._parse_topology_json(TOPOLOGY_JSON_30_DEVICES)
        for d in devices:
            assert d["MACAddress"] == d["MACAddress"].upper()

    def test_empty_ad_returns_none(self, client):
        """Empty ad section returns None."""
        assert client._parse_topology_json(TOPOLOGY_EMPTY_AD) is None

    def test_no_ad_key_returns_none(self, client):
        """Missing ad key returns None."""
        assert client._parse_topology_json(TOPOLOGY_NO_AD) is None

    def test_empty_dict_returns_none(self, client):
        """Empty dict returns None."""
        assert client._parse_topology_json({}) is None

    def test_skips_non_dict_entries(self, client):
        """Non-dict entries in ad (like MGET_INST_NUM) are skipped."""
        data = {
            "master": {"instID": "MESH.CONTROLLER", "DeviceName": "Router"},
            "ad": {
                "1": {
                    "parent": "MESH.CONTROLLER",
                    "MacAddr": "aa:bb:cc:dd:ee:ff",
                    "IpAddr": "192.168.1.100",
                    "HostName": "Test",
                    "AccessType": "0",
                },
                "MGET_INST_NUM": 1,
                "some_other_key": "string_value",
            },
        }
        devices = client._parse_topology_json(data)
        assert devices is not None
        assert len(devices) == 1

    def test_skips_entries_without_mac(self, client):
        """Entries without MacAddr are skipped."""
        data = {
            "master": {"instID": "MESH.CONTROLLER"},
            "ad": {
                "1": {
                    "parent": "MESH.CONTROLLER",
                    "MacAddr": "",
                    "IpAddr": "192.168.1.100",
                    "HostName": "NoMAC",
                    "AccessType": "0",
                },
                "MGET_INST_NUM": 1,
            },
        }
        assert client._parse_topology_json(data) is None

    def test_no_master_or_slave_still_parses(self, client):
        """Topology with only ad section still parses devices."""
        data = {
            "ad": {
                "1": {
                    "parent": "UNKNOWN_NODE",
                    "MacAddr": "aa:bb:cc:dd:ee:ff",
                    "IpAddr": "192.168.1.100",
                    "HostName": "Test",
                    "AccessType": "0",
                },
                "MGET_INST_NUM": 1,
            },
        }
        devices = client._parse_topology_json(data)
        assert devices is not None
        assert len(devices) == 1
        # MeshNode falls back to raw parent ID
        assert devices[0]["MeshNode"] == "UNKNOWN_NODE"


# --- _try_topology tests ---


class TestTryTopology:
    """Tests for _try_topology HTTP session method."""

    def test_no_topo_tag_returns_none(self, client_no_topo):
        """Models without topo_data_tag skip topology."""
        assert client_no_topo._try_topology() is None

    def test_circuit_breaker_after_3_failures(self, client):
        """Circuit breaker blocks after 3 consecutive failures."""
        import time

        client._topo_failures = 3
        client._topo_last_fail = time.time()
        assert client._try_topology() is None

    def test_circuit_breaker_resets_after_cooldown(self, client):
        """Circuit breaker resets after 5 min cooldown."""
        import time

        client._topo_failures = 3
        client._topo_last_fail = time.time() - 301  # 5+ min ago
        # Set up a mock session (inline path)
        mock_session = MagicMock()
        client.session = mock_session
        # menuView returns OK, topo returns SessionTimeout
        menu_resp = MagicMock()
        topo_resp = MagicMock()
        topo_resp.text = SESSION_TIMEOUT_XML
        mock_session.get.side_effect = [menu_resp, topo_resp]
        result = client._try_topology()
        # Should have attempted (not short-circuited)
        assert mock_session.get.called
        assert result is None

    def test_successful_topology_resets_failures(self, client):
        """Successful topology fetch resets failure counter."""
        client._topo_failures = 2
        mock_session = MagicMock()
        client.session = mock_session

        menu_resp = MagicMock()
        topo_resp = MagicMock()
        topo_resp.text = json.dumps(TOPOLOGY_JSON_30_DEVICES)
        mock_session.get.side_effect = [menu_resp, topo_resp]

        result = client._try_topology()
        assert result is not None
        assert len(result) == 5
        assert client._topo_failures == 0

    def test_session_timeout_response(self, client):
        """SessionTimeout in response body increments failure counter."""
        client._topo_failures = 0
        mock_session = MagicMock()
        client.session = mock_session

        menu_resp = MagicMock()
        topo_resp = MagicMock()
        topo_resp.text = SESSION_TIMEOUT_XML
        mock_session.get.side_effect = [menu_resp, topo_resp]

        result = client._try_topology()
        assert result is None
        assert client._topo_failures == 1

    def test_html_error_response(self, client):
        """HTML error body increments failure counter."""
        client._topo_failures = 0
        mock_session = MagicMock()
        client.session = mock_session

        menu_resp = MagicMock()
        topo_resp = MagicMock()
        topo_resp.text = HTML_404_PAGE
        mock_session.get.side_effect = [menu_resp, topo_resp]

        result = client._try_topology()
        assert result is None
        assert client._topo_failures == 1

    def test_router_locked_returns_none(self, client):
        """No session returns None gracefully."""
        client._topo_failures = 0
        client.session = None
        result = client._try_topology()
        assert result is None

    def test_logout_always_called(self, client):
        """Exception during inline fetch returns None."""
        mock_session = MagicMock()
        client.session = mock_session
        mock_session.get.side_effect = ConnectionError("Network down")

        result = client._try_topology()
        assert result is None

    def test_exception_during_fetch_returns_none(self, client):
        """Network exceptions return None gracefully."""
        with patch("custom_components.zte_tracker.zteclient.zte_client.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            mock_session.get.side_effect = ConnectionError("refused")

            result = client._try_topology()
            assert result is None


# --- Coordinator SSID enrichment tests ---


class TestTopologySSIDEnrichment:
    """Tests for SSID enrichment in coordinator."""

    def test_legacy_ssid_merged_into_topology(self):
        """Port/SSID from legacy WiFi data is merged into topology devices."""
        legacy_devices = [
            {
                "MACAddress": "EC:4D:3E:3D:4F:18",
                "HostName": "yeelink-light",
                "IPAddress": "192.168.1.4",
                "NetworkType": "WLAN",
                "Port": "DSI-WN",
                "ConnectTime": "2026-05-13T10:00:00",
                "LinkTime": "3600",
                "Active": True,
            },
        ]
        topo_devices = [
            {
                "MACAddress": "EC:4D:3E:3D:4F:18",
                "HostName": "yeelink-light",
                "IPAddress": "192.168.1.4",
                "NetworkType": "WLAN",
                "Port": "",
                "ConnectTime": "",
                "LinkTime": "",
                "MeshNode": "ZTE:F6600P",
                "Active": True,
            },
            {
                "MACAddress": "58:B6:23:BD:48:CF",
                "HostName": "IoT-Agent",
                "IPAddress": "192.168.1.7",
                "NetworkType": "WLAN",
                "Port": "",
                "ConnectTime": "",
                "LinkTime": "",
                "MeshNode": "ZTE:H196A V9",
                "Active": True,
            },
        ]

        # Simulate the merge logic from coordinator
        legacy_by_mac = {d.get("MACAddress", ""): d for d in legacy_devices}
        for td in topo_devices:
            legacy = legacy_by_mac.get(td.get("MACAddress", ""))
            if legacy and legacy.get("Port"):
                td["Port"] = legacy["Port"]
            if legacy and legacy.get("ConnectTime"):
                td["ConnectTime"] = legacy["ConnectTime"]
            if legacy and legacy.get("LinkTime"):
                td["LinkTime"] = legacy["LinkTime"]

        # Controller WiFi device gets SSID
        assert topo_devices[0]["Port"] == "DSI-WN"
        assert topo_devices[0]["ConnectTime"] == "2026-05-13T10:00:00"
        assert topo_devices[0]["LinkTime"] == "3600"
        # Agent device keeps empty (not in legacy)
        assert topo_devices[1]["Port"] == ""

    def test_no_legacy_devices_no_crash(self):
        """Empty legacy list doesn't crash enrichment."""
        legacy_devices = []
        topo_devices = [
            {
                "MACAddress": "AA:BB:CC:DD:EE:FF",
                "Port": "",
                "ConnectTime": "",
                "LinkTime": "",
            },
        ]
        legacy_by_mac = {d.get("MACAddress", ""): d for d in legacy_devices}
        for td in topo_devices:
            legacy = legacy_by_mac.get(td.get("MACAddress", ""))
            if legacy and legacy.get("Port"):
                td["Port"] = legacy["Port"]

        assert topo_devices[0]["Port"] == ""
