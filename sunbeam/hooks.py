# Copyright 2022 Canonical Ltd.
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
import logging
import shutil

from snaphelpers import Snap

from sunbeam.log import setup_logging

LOG = logging.getLogger(__name__)
DEFAULT_CONFIG = {
    "control-plane.cloud": "microk8s",
    "control-plane.model": "openstack",
    "node.role": "CONVERGED",
    "snap.channel.juju": "3.0/stable",
    "snap.channel.microk8s": "1.25-strict/stable",
    "snap.channel.openstack-hypervisor": "xena/edge",
}


def _update_default_config(snap: Snap) -> None:
    """Add any missing default configuration keys.

    :param snap: the snap reference
    :type snap: Snap
    :return: None
    """
    option_keys = set([k.split(".")[0] for k in DEFAULT_CONFIG.keys()])
    current_options = snap.config.get_options(*option_keys)
    for option, default in DEFAULT_CONFIG.items():
        if option not in current_options:
            snap.config.set({option: default})


def install(snap: Snap) -> None:
    """Runs the 'install' hook for the snap.

    The 'install' hook will create the configuration and bundle deployment
    directories inside of $SNAP_COMMON as well as setting the default
    configuration options for the snap.

    :param snap: the snap instance
    :type snap: Snap
    :return:
    """
    setup_logging(snap.paths.common / "hooks.log")
    LOG.debug("Running install hook...")
    src = snap.paths.snap / "etc" / "bundles"
    dst = snap.paths.common / "etc" / "bundles"
    LOG.debug(f"Copying {src} to {dst}...")
    shutil.copytree(src, dst)

    logging.info(f"Setting default config: {DEFAULT_CONFIG}")
    snap.config.set(DEFAULT_CONFIG)


def upgrade(snap: Snap) -> None:
    """Runs the 'upgrade' hook for the snap.

    The 'upgrade' hook will upgrade the various bundle information, etc. This
    is

    :param snap:
    :return:
    """
    setup_logging(snap.paths.common / "hooks.log")
    LOG.debug("Running the upgrade hook...")
    src = snap.paths.snap / "etc" / "bundles"
    dst = snap.paths.common / "etc" / "bundles"
    LOG.debug(f"Updating {dst} from {src}...")
    shutil.copytree(src, dst, dirs_exist_ok=True)


def configure(snap: Snap) -> None:
    """Runs the `configure` hook for the snap.

    This method is invoked when the configure hook is executed by the snapd
    daemon. The `configure` hook is invoked when the user runs a sudo snap
    set openstack-hypervisor.<foo> setting.

    :param snap: the snap reference
    :type snap: Snap
    :return: None
    """
    setup_logging(snap.paths.common / "hooks.log")
    logging.info("Running configure hook")

    _update_default_config(snap)
