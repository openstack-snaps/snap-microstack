# Copyright (c) 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from sunbeam.commands import configure


class TestConfigure:
    def test_get_nic_macs(self, ifaddresses):
        assert configure.get_nic_macs("eth0") == ["eth0mac1", "eth0mac2"]

    def test_is_configured(self, ifaddresses):
        assert configure.is_configured("eth0")
        assert not configure.is_configured("eth2")

    def test_get_free_nics(self, pglob, ifaddresses, interfaces):
        # ['eth2', 'eth3', 'ovs-system', 'bond0', 'bond1']
        # Should see:
        #     eth0 dropped for being ipv4 configured
        #     eth1 dropped for being ipv4 and ipv6 configured
        #     eth2 dropped for being part of a bridge
        #     eth3 dropped for being part of a bridge
        #     eth4 pass
        #     eth5 dropped for being part of a bridge
        #     eth6 dropped for being part of a bridge
        #     ovs-system dropped for being virtual
        #     bond0 pass
        #     bond1 dropped for being ipv4 configured
        assert configure.get_free_nics() == ["eth4", "bond0"]
