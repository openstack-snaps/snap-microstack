# Copyright (c) 2023 Canonical Ltd.
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

import click
import copy

INSTALL_SCRIPT_TEMPLATE = """USER=$(whoami)
sudo snap install microk8s --channel {microk8s_channel}
sudo microk8s status --wait-ready
sudo microk8s enable dns hostpath-storage
sudo microk8s enable metallb {metallb_range}
sudo usermod -a -G snap_microk8s $USER
sudo chown -f -R $USER ~/.kube
sudo microk8s disable metallb
sudo microk8s enable metallb {metallb_range}
sudo usermod -a -G snap_microk8s $USER
sudo chown -f -R $USER ~/.kube
newgrp snap_microk8s
newgrp lxd
id
touch /var/snap/microk8s/current/var/lock/no-cert-reissue
sudo snap install juju --channel {juju_channel}
mkdir -p .local/share
sudo snap install openstackclients
sudo snap install openstack-hypervisor --channel {hypervisor_channel}
microstack -v bootstrap
microstack -v openrc > admin_openrc
microstack -v configure -a -o demo_openrc"""

DEFAULT = {
    "metallb_range": "10.177.200.170-10.177.200.190",
    "microk8s_channel": "1.25-strict/stable",
    "juju_channel": "3.0/candidate",
    "hypervisor_channel": "yoga/edge",
}


@click.command()
def install_script() -> None:
    """Generate install script"""
    ctxt = copy.deepcopy(DEFAULT)
    print(INSTALL_SCRIPT_TEMPLATE.format(**ctxt))
