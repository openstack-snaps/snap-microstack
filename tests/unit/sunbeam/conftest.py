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

import socket
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def pglob():
    nic1 = MagicMock()
    nic1.name = "tap0783c4e4"
    nic2 = MagicMock()
    nic2.name = "ovs-switch"
    with patch("pathlib.PosixPath.glob") as p:
        p.return_value = [nic1, nic2]
        yield p


@pytest.fixture
def net_if_addrs():
    with patch("psutil.net_if_addrs") as p:
        p.return_value = {
            "eth0": [(socket.AF_INET6,)],
            "eth1": [(socket.AF_INET,)],
            "ovs-switch": [],
            "eth2": [],
            "eth3": [],
        }
        yield p
