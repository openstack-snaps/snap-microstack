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

import logging
import subprocess
from typing import Optional

from semver import VersionInfo
from snaphelpers import Snap

from sunbeam.jobs.common import BaseStep, InstallSnapStep, Result, ResultType

LOG = logging.getLogger(__name__)
snap = Snap()


class EnsureMicrok8sInstalled(InstallSnapStep):
    """Validates microk8s is installed.

    Note, this can go away if we can default include the microk8s snap
    """

    MIN_VERSION = VersionInfo(1, 25, 0)

    def __init__(self, channel: str = "latest/stable"):
        super().__init__(snap="microk8s", channel=channel)

    def _is_classic(self, channel: str) -> bool:
        return "strict" not in channel


class BaseCoreMicroK8sEnableStep(BaseStep):
    """Base add-on enablement step"""

    def __init__(self, addon: str, *args):
        """Enables high availability for the microk8s cluster"""
        super().__init__(
            f"Enable microk8s {addon}", f"Enabling microk8s {addon} add-on"
        )
        self._addon = addon
        self._args = None
        if len(args):
            self._args = [a for a in args]

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        cmd = ["/snap/bin/microk8s", "status", "-a", self._addon]
        try:
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            LOG.debug(
                f"Command finished. stdout={process.stdout}, " "stderr={process.stderr}"
            )
            return process.stdout.strip() == "enabled"
        except subprocess.CalledProcessError:
            LOG.exception("Error determining ha-cluster add on status")
            return False

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        cmd = ["/snap/bin/microk8s", "enable", self._addon]
        if self._args:
            cmd.extend(self._args)

        try:
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            LOG.debug(
                f"Command finished. stdout={process.stdout}, " "stderr={process.stderr}"
            )
            return Result(ResultType.COMPLETED)
        except subprocess.CalledProcessError as e:
            if "timed out waiting" in e.stderr and self.is_skip():
                # TODO(wolsen) work on the timeout and retry handling for the
                #  scenario where the enablement times out. This will suffice
                #  for now, but it'd be better to wait until it is actually done
                #  which will require querying k8s.
                LOG.debug(
                    "Addon timedout enabling. Wait and see if it is enabled "
                    "and continue on"
                )
                return Result(ResultType.COMPLETED)

            error_message = f"Error enabling microk8s add-on {self._addon}"
            LOG.exception(error_message)
            LOG.error(e.stderr)
            return Result(ResultType.FAILED, error_message)


class EnableHighAvailability(BaseCoreMicroK8sEnableStep):
    """Enables high availability for the Microk8s cluster."""

    def __init__(self):
        """Enables high availability for the microk8s cluster"""
        super().__init__("ha-cluster")


class EnableDNS(BaseCoreMicroK8sEnableStep):
    """Enables the coredns addon for Microk8s"""

    def __init__(self):
        super().__init__("dns")

    def has_prompts(self) -> bool:
        return True

    def prompt(self, console: Optional["rich.console.Console"] = None) -> None:
        """Prompt the user for usptream nameserver.

        Prompts the user to determine the upstream nameserver to be used
        to configure dns.

        :param console: the console to prompt on
        :type console: rich.console.Console (Optional)
        """
        from rich.prompt import Prompt

        console.print()
        nameservers = Prompt.ask(
            "Comma separated upstream nameservers:",
            default="8.8.8.8,8.8.4.4",
            console=console,
        )
        self._args = [nameservers]
        snap.config.set({"microk8s.dns": nameservers})


class EnableStorage(BaseCoreMicroK8sEnableStep):
    """Enable host-based storage for microk8s"""

    def __init__(self):
        super().__init__("hostpath-storage")


class EnableMetalLB(BaseCoreMicroK8sEnableStep):
    """Enable metallb for microk8s"""

    def __init__(self):
        network = snap.config.get("microk8s.metallb")
        super().__init__("metallb", network)

    def has_prompts(self) -> bool:
        return True

    def prompt(self, console: Optional["rich.console.Console"] = None) -> None:
        """Prompt the user for which IP ranges to configure.

        Prompts the user to determine which IP ranges need to be configured.

        :param console: the console to prompt on
        :type console: rich.console.Console (Optional)
        """
        from rich.prompt import Prompt

        console.print()
        network = Prompt.ask(
            "Which network range should be used for control " "plane services: ",
            default="10.20.20.1/29",
            console=console,
        )
        self._args = [network]
        snap.config.set({"microk8s.metallb": network})


class EnableAccessToUser(BaseStep):
    """Enable microk8s access to user"""

    def __init__(self, user: str):
        super().__init__(
            name="Ensure microk8s access", description="Provide microk8s access to user"
        )
        self.user = user

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        # Check if user is already part of group
        return False

    def run(self, status: Optional["Status"] = None):
        """Add user to snap_microk8s group"""
        cmd = ["usermod", "-a", "-G", "snap_microk8s", self.user]

        try:
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            LOG.debug(
                f"Command finished. stdout={process.stdout}, " "stderr={process.stderr}"
            )
            return Result(ResultType.COMPLETED)
        except subprocess.CalledProcessError as e:
            error_message = "Adding user to snap_microk8s group failed"
            LOG.exception(error_message)
            LOG.error(e.stderr)
            return Result(ResultType.FAILED, error_message)
