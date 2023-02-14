# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from unittest.mock import MagicMock, patch

import netifaces
import pytest
from snaphelpers import Snap, SnapConfig, SnapServices


@pytest.fixture
def snap_env():
    """Environment variables defined in the snap.

    This is primarily used to setup the snaphelpers bit.
    """
    yield {
        "SNAP": "/snap/mysnap/2",
        "SNAP_COMMON": "/var/snap/mysnap/common",
        "SNAP_DATA": "/var/snap/mysnap/2",
        "SNAP_INSTANCE_NAME": "",
        "SNAP_NAME": "mysnap",
        "SNAP_REVISION": "2",
        "SNAP_USER_COMMON": "",
        "SNAP_USER_DATA": "",
        "SNAP_VERSION": "1.2.3",
        "SNAP_REAL_HOME": "/home/ubuntu",
    }


@pytest.fixture
def snap(snap_env):
    snap = Snap(environ=snap_env)
    snap.config = MagicMock(SnapConfig)
    snap.services = MagicMock(SnapServices)
    yield snap


@pytest.fixture
def run():
    with patch("subprocess.run") as p:
        yield p


@pytest.fixture
def environ():
    with patch("os.environ") as p:
        yield p


nic_config = {
    "eth0": {
        netifaces.AF_LINK: [{"addr": "eth0mac1"}, {"addr": "eth0mac2"}],
        netifaces.AF_INET: [{"addr": "10.0.0.1"}],
        netifaces.AF_INET6: [{"addr": "fe80::52eb:f6ff:fe5c:2300%eth0"}],
    },
    "eth1": {
        netifaces.AF_LINK: [{"addr": "eth1mac1"}, {"addr": "eth1mac2"}],
        netifaces.AF_INET: [{"addr": "10.0.0.2"}],
    },
    "eth2": {netifaces.AF_LINK: [{"addr": "bond0mac1"}, {"addr": "eth2mac2"}]},
    "eth3": {netifaces.AF_LINK: [{"addr": "bond0mac1"}, {"addr": "eth3mac2"}]},
    "eth4": {netifaces.AF_LINK: [{"addr": "eth40mac1"}, {"addr": "eth4mac2"}]},
    "eth5": {netifaces.AF_LINK: [{"addr": "bond1mac1"}, {"addr": "eth5mac2"}]},
    "eth6": {netifaces.AF_LINK: [{"addr": "bond1mac1"}, {"addr": "eth6mac2"}]},
    "ovs-system": {netifaces.AF_LINK: [{"addr": "ovssysmac1"}]},
}
bond_config = {
    "bond0": {netifaces.AF_LINK: [{"addr": "bond0mac1"}, {"addr": "bond0mac2"}]},
    "bond1": {
        netifaces.AF_LINK: [{"addr": "bond1mac1"}, {"addr": "bond1mac2"}],
        netifaces.AF_INET: [{"addr": "10.0.0.19"}],
    },
}


@pytest.fixture
def ifaddresses():
    with patch("netifaces.ifaddresses") as p:

        def _ifaddresses(nic):
            return nic_config.get(nic) or bond_config.get(nic)

        p.side_effect = _ifaddresses
        yield p


@pytest.fixture
def interfaces():
    with patch("netifaces.interfaces") as p:
        p.return_value = list(nic_config.keys()) + list(bond_config.keys())
        yield p


@pytest.fixture
def pglob():
    def _glob(path):
        if path.startswith("/sys/devices/virtual/net"):
            nics = ["ovs-system", "bond0", "bond1"]
        else:
            nics = ["bond0", "bond1"]
        nics = [os.path.dirname(path) + f"/{n}" for n in nics]
        return nics

    with patch("glob.glob") as p:
        p.side_effect = _glob
        yield p
