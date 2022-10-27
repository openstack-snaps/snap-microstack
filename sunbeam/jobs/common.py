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

import enum
import logging
from typing import Optional

import click
from rich.console import Console
from rich.status import Status
from semver import VersionInfo

from sunbeam import utils
from sunbeam.snapd.changes import Status as SnapStatus
from sunbeam.snapd.client import Client as SnapClient

LOG = logging.getLogger(__name__)


class ResultType(enum.Enum):
    COMPLETED = 0
    FAILED = 1
    SKIPPED = 2


class Result:
    """The result of running a step"""

    def __init__(self, result_type: ResultType, message: Optional[str] = ""):
        """Creates a new result

        :param result_type:
        :param message:
        """
        self.result_type = result_type
        self.message = message


class StepResult:
    """The Result of running a Step.

    The results of running contain the minimum of the ResultType to indicate
    whether running the Step was completed, failed, or skipped.
    """

    def __init__(self, result_type: ResultType = ResultType.COMPLETED, **kwargs):
        """Creates a new StepResult.

        The StepResult will contain various information regarding the result
        of running a Step. By default, a new StepResult will be created with
        result_type set to ResultType.COMPLETED.

        Additional attributes can be stored in the StepResult object by using
        the kwargs values, but the keys must be unique to the StepResult
        already. If the kwargs contains a keyword that is an attribute on the
        object then a ValueError is raised.

        :param result_type: the result of running a plan or step.
        :param kwargs: additional attributes to store in the step.
        :raises: ValueError if a key in the kwargs already exists on the
                 object.
        """
        self.result_type = result_type
        for key, value in kwargs.items():
            # Note(wolsen) this is a bit of a defensive check to make sure
            # a bit of code doesn't accidentally override a base object
            # attribute.
            if hasattr(self, key):
                raise ValueError(
                    f"{key} was specified but already exists on " f"this StepResult."
                )
            self.__setattr__(key, value)


class BaseStep:
    """A step defines a logical unit of work to be done as part of a plan.

    A step determines what needs to be done in order to perform a logical
    action as part of carrying out a plan.
    """

    def __init__(self, name: str, description: str = ""):
        """Initialise the BaseStep

        :param name: the name of the step
        """
        self.name = name
        self.description = description

    def prompt(self, console: Optional[Console] = None) -> None:
        """Determines if the step can take input from the user.

        Prompts are used by Steps to gather the necessary input prior to
        running the step. Steps should not expect that the prompt will be
        available and should provide a reasonable default where possible.
        """
        pass

    def has_prompts(self) -> bool:
        """Returns true if the step has prompts that it can ask the user.

        :return: True if the step can ask the user for prompts,
                 False otherwise
        """
        return False

    def is_skip(self, status: Optional[Status] = None) -> bool:
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def run(self, status: Optional[Status]) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        pass


class InstallSnapStep(BaseStep):
    """Installs a Snap

    This is a step used to install a snap. It attempts to take into account
    minimum versions and allowing snaps to already be installed (for the
    offline case).
    """

    MIN_VERSION = VersionInfo(0, 0, 1)

    def __init__(self, snap: str, channel: Optional[str] = "latest/stable"):
        self.snap = snap
        super().__init__(name=f"Install {snap}", description=f"Installing {snap}")
        self.channel = channel
        self.snap_client = SnapClient()
        self._installed_version = None

    def _is_classic(self, channel: str) -> bool:
        """Determines if the snap should be installed using classic confinement.

        :param channel: the channel that the snap is being installed from
        :type channel: str
        :return: True if the snap should be installed in classic mode, False otherwise
        """
        return False

    def _is_valid_version(self, version: VersionInfo) -> bool:
        """Determines if a currently installed version of the snap is okay.

        :return: True if the version is ok. False, otherwise.
        """
        if version > self.MIN_VERSION:
            return True

        return False

    def is_skip(self, status: Optional[Status] = None) -> bool:
        """Determines if the desired version of software is already installed.

        :param status: an optional status object that can be updated to
                       provide additional information regarding the current
                       status.
        :return: True if a sufficient version of software is already
                 installed
        """
        if status:
            status.update(status=f"Checking for installed {self.snap}")

        snaps = self.snap_client.snaps.get_installed_snaps([self.snap])
        if not snaps:
            LOG.debug(f"No {self.snap} snaps were installed.")
            return False

        # It is possible to install snaps multiple times with different names,
        # each getting different paths and contexts. Until there is
        # communication available between this snap and the Juju/Microk8s snaps
        # this configuration cannot be safely supported.
        if len(snaps) > 1:
            LOG.warning(f"Multiple {self.snap} snaps are installed.")
            # TODO(wolsen) Determine if there's a way we can handle this. It is
            #  possible that there are two snaps installed, with one installed
            #  to the default path and another installed with a different name
            raise click.ClickException(
                f"Found {len(snaps)} {self.snap} snaps already installed. "
                f"Only one installed {self.snap} snap is allowed."
            )

        # Hmm, could be a developer version of the snap as a test, or something
        # to that effect. Maybe allow it, but prompt for confirmation of the
        # unknown behavior.
        inst_snap = snaps[0]
        try:
            if status:
                status.update(
                    status=f"Found {self.snap} version " f"{inst_snap.version}"
                )

            LOG.debug(f"Found {self.snap} version {inst_snap.version} " "installed.")
            version = utils.parse_version(inst_snap.version)
            self._installed_version = version
            if self._is_valid_version(version):
                return True

            LOG.debug(f"The installed {self.snap} is too old.")
            raise click.ClickException(
                f"The installed version of {self.snap} ({inst_snap.version}) "
                f"is too old. Install a version newer than "
                f"{self.MIN_VERSION} and try again."
            )
        except ValueError:
            LOG.error(f"Failed to parse the {self.snap} version string.")
            self._installed_version = utils.UNKNOWN_VERSION
            return False

    def has_prompts(self) -> bool:
        """Determines if we need to prompt the user

        The user will be prompted if no software snap is installed or if the
        version installed isn't a known version (for the developer scenario).

        :return: True if there are prompts, False otherwise
        """
        # Need to prompt the user that we will install a new version.
        if not self._installed_version:
            return True

        # If this is an unknown version...
        if self._installed_version == utils.UNKNOWN_VERSION:
            return True

        return False

    def prompt(self, console: Optional[Console] = None) -> None:
        """Prompts the user for installation or verification.

        :param console:
        :return:
        """
        if not self._installed_version:
            from rich.prompt import Confirm

            console.print()
            confirm = Confirm.ask(
                f"Install {self.snap} onto this machine?", default="Yes"
            )
            if not confirm:
                raise click.ClickException(
                    f"{self.snap} needs to be installed to continue."
                )

    def run(self, status: Optional[Status] = None) -> Result:
        """Checks to see if Juju is installed..."""

        if self._installed_version:
            # At this point, there's a version of Juju installed and any
            # prompts have been bypassed at this point. As such, there's
            # nothing to do.
            LOG.debug(f"{self.snap} is already installed, nothing to do.")
            return Result(ResultType.COMPLETED)

        try:
            LOG.debug(f"Installing {self.snap} from channel {self.channel}")
            if status:
                status.update(
                    f"Installing {self.snap} from channel " f"{self.channel} ..."
                )
            change_id = self.snap_client.snaps.install(
                self.snap, self.channel, classic=self._is_classic(self.channel)
            )
            LOG.debug(f"Initiated installation with change {change_id}")
            self.snap_client.changes.wait_until(
                change_id, [SnapStatus.DoneStatus, SnapStatus.ErrorStatus]
            )
        except:  # noqa
            LOG.exception(f"Error occurred installing {self.snap}")
            return Result(ResultType.FAILED, f"Error occurred installing {self.snap}")

        return Result(ResultType.COMPLETED)
