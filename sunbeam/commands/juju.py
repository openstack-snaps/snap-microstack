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

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from juju.controller import Controller
from semver import VersionInfo
from snaphelpers import Snap

from sunbeam.jobs.common import BaseStep, InstallSnapStep, Result, ResultType

LOG = logging.getLogger(__name__)


class JujuHelper:
    """Helper class to interact with juju"""

    def __init__(self):
        home = os.environ.get("SNAP_REAL_HOME")
        os.environ["JUJU_DATA"] = f"{home}/.local/share/juju"

        self.controller = None

    async def disconnect_controller(self):
        await self.controller.disconnect()

    async def add_model(self, model: str) -> bool:
        """Add model to juju"""
        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            await self.controller.add_model(model)
            return True
        except Exception as e:
            LOG.error(f"Error in adding model {model}: {str(e)}")
            return False

    async def get_models(self) -> dict:
        """Get all models"""
        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            models = await self.controller.list_models()
            return models
        except Exception as e:
            LOG.info(f"Error in getting models: {str(e)}")
            return []

    async def get_model_status_full(self, model: str, timeout: int) -> dict:
        """Get juju status for the model"""
        if not self.controller:
            self.controller = Controller()
            await self.controller.connect()

        model = await self.controller.get_model(model)
        status = await model.get_status()
        return status

    async def get_model_status(self, model: str, timeout: int) -> dict:
        """Get juju status for the model"""
        apps_status = {}

        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            # Get the reference to the specified model
            model = await self.controller.get_model(model)
            start = time.time()
            apps = set(model.applications.keys())
            apps_count = len(apps)
            apps_active = set()

            while True:
                # now we sleep to allow progress to be made in the
                # libjuju futures
                await asyncio.sleep(1.0)
                timed_out = int(time.time() - start) > timeout

                for application in apps:
                    app_data = model.applications.get(application, None)
                    if app_data:
                        apps_status[application] = app_data.status
                        if app_data.status == "active":
                            apps_active.add(application)

                if apps_count == len(apps_active):
                    break

                if timed_out:
                    if timeout:
                        LOG.info("TIMEOUT: Workloads didn't reach acceptable status")
                    break
        except Exception as e:
            LOG.info(f"Error in getting model status: {str(e)}")

        return apps_status

    async def deploy_bundle(self, model: str, bundle: str) -> bool:
        """Deploy bundle"""
        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            # Get the reference to the specified model
            model = await self.controller.get_model(model)
            applications = await model.deploy(
                f"local:{bundle}",
                trust=True,
            )

            await model.block_until(
                lambda: all(
                    unit.workload_status == "active"
                    for application in applications
                    for unit in application.units
                )
            )

            return True
        except Exception as e:
            LOG.error(f"Error in deploying bundle: {str(e)}")
            return False

    async def wait_until_active(self, model: str) -> None:
        """Wait for all units in model to reach active status"""
        if not self.controller:
            self.controller = Controller()
            await self.controller.connect()

        model = await self.controller.get_model(model)

        await model.block_until(
            lambda: all(
                unit.workload_status == "active"
                for application in model.applications.values()
                for unit in application.units
            )
        )

    async def destroy_model(self, model_name: str, wait: bool = True) -> bool:
        """Destroy the model"""
        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            await self.controller.destroy_models(
                model_name, destroy_storage=True, force=True, max_wait=0
            )

            if wait:
                LOG.debug("Waiting for model to be removed")
                # Cannot use block_until as that is a method from the
                # model being destroyed.
                for i in range(0, 30):
                    models = await self.get_models()
                    if model_name not in models:
                        LOG.debug("Model has gone")
                        return True
                    else:
                        LOG.debug("Model still present")
                        await asyncio.sleep(10.0)
                else:
                    return False
            return True
        except Exception as e:
            LOG.error(f"Error in destroying model: {str(e)}")
            return False

    async def run_action(
        self, model: str, app: str, action_name: str, action_params: dict = {}
    ) -> dict:
        """Run actions on leader unit

        :param: app: Application name
        :param: action_name: Action to run
        :param: action_params: Parameters to action
        :return: dictionary of result from action
        """

        leader_unit = None
        action_result = {}

        try:
            if not self.controller:
                self.controller = Controller()
                await self.controller.connect()

            # Get the reference to the specified model
            model = await self.controller.get_model(model)

            application = model.applications.get(app, None)
            for unit in application.units:
                if await unit.is_leader_from_status():
                    leader_unit = unit
                    break

            if not leader_unit:
                return action_result

            LOG.debug(f"Running action {action_name} on {app} leader unit")
            action = await leader_unit.run_action(action_name, **action_params)
            result = await action.wait()
            action_result = result.results
            LOG.debug(f"Action result: {action_result}")

        except ValueError as valerr:
            LOG.error(valerr)
        except Exception as err:
            LOG.error(err)

        return action_result


class EnsureJujuInstalled(InstallSnapStep):
    """Validates the Juju is installed.

    Note, this can go away if Juju adds an interface for us to know that it
    is present.
    """

    MIN_JUJU_VERSION = VersionInfo(2, 9, 30)

    def __init__(self, channel: str = "latest/stable"):
        super().__init__(snap="juju", channel=channel)

    def _is_classic(self, channel: str) -> bool:
        return channel.split("/")[0].startswith("2.9")


class JujuStepHelper:
    def _get_juju_binary(self) -> str:
        """Get juju binary path."""
        snap = Snap()
        juju_binary = snap.paths.snap / "juju" / "bin" / "juju"
        return str(juju_binary)

    def _juju_cmd(self, *args):
        """Runs the specified juju command line command

        The command will be run using the json formatter. Invoking functions
        do not need to worry about the format or the juju command that should
        be used.

        For example, to run the juju bootstrap microk8s, this method should
        be invoked as:

          self._juju_cmd('bootstrap', 'microk8s')

        Any results from running with json are returned after being parsed.
        Subprocess execution errors are raised to the calling code.

        :param args: command to run
        :return:
        """
        cmd = [self._get_juju_binary()]
        cmd.extend(args)
        cmd.extend(["--format", "json"])

        LOG.debug(f'Running command {" ".join(cmd)}')
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        LOG.debug(
            f"Command finished. stdout={process.stdout}, " "stderr={process.stderr}"
        )

        return json.loads(process.stdout.strip())

    def check_model_present(self, model_name):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        LOG.debug("Retrieving model information from Juju")
        models = asyncio.get_event_loop().run_until_complete(self.jhelper.get_models())
        LOG.debug(f"Juju models: {models}")
        return model_name in models


class BootstrapJujuStep(BaseStep, JujuStepHelper):
    """Bootstraps the Juju controller."""

    def __init__(self, cloud):
        super().__init__("Bootstrap Juju", "Bootstrapping Juju into microk8s")

        self.controller_name = None
        self.cloud = cloud

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """

        # Determine which kubernetes clouds are added
        try:
            clouds = self._juju_cmd("clouds")
            LOG.debug(f"Available clouds in juju are {clouds.keys()}")

            k8s_clouds = []
            for name, details in clouds.items():
                if details["type"] == "k8s":
                    k8s_clouds.append(name)

            LOG.debug(
                f"There are {len(k8s_clouds)} k8s clouds available: " f"{k8s_clouds}"
            )

            controllers = self._juju_cmd("controllers")

            LOG.debug(f"Found controllers: {controllers.keys()}")
            LOG.debug(controllers)
            controllers = controllers.get("controllers", {})
            if not controllers:
                return False

            existing_controllers = []
            for name, details in controllers.items():
                if details["cloud"] in k8s_clouds:
                    existing_controllers.append(name)

            LOG.debug(
                f"There are {len(existing_controllers)} existing k8s "
                f"controllers running: {existing_controllers}"
            )
            if not existing_controllers:
                return False

            # Simply use the first existing kubernetes controller we find.
            # We actually probably need to provide a way for this to be
            # influenced, but for now - we'll use the first controller.
            self.controller_name = existing_controllers[0]
            return True
        except subprocess.CalledProcessError as e:
            LOG.exception(
                "Error determining whether to skip the bootstrap "
                "process. Defaulting to not skip."
            )
            LOG.debug(str(e))
            return False

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            clouds = self._juju_cmd("clouds")
            k8s_clouds = []
            for name, details in clouds.items():
                if details["type"] == "k8s":
                    k8s_clouds.append(name)

            LOG.debug(
                f"There are {len(k8s_clouds)} k8s clouds available: " f"{k8s_clouds}"
            )

            if not k8s_clouds:
                LOG.critical(
                    "\nNo k8s cloud detected by Juju.\n"
                    "Run below command for non-microk8s kubernetes cloud "
                    "to provide access to config file:\n"
                    "sudo snap connect microstack:dot-kubernetes\n"
                )
                return Result(
                    ResultType.FAILED,
                    "Could not find any k8s clouds to bootstrap",
                )

            if self.cloud not in k8s_clouds:
                LOG.critical(f"Could not find {self.cloud} as a suitable cloud!")
                return Result(
                    ResultType.FAILED,
                    f"Could not find {self.cloud} cloud to bootstrap",
                )

            cmd = [self._get_juju_binary(), "bootstrap", self.cloud]

            # TODO(wolsen) probably want to refactor this into a proper quirks type
            #  thing.
            snap = Snap()
            juju_channel = snap.config.get("snap.channel.juju")
            if juju_channel.startswith("2.9"):
                cmd.extend(["--agent-version", "2.9.34"])

            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            LOG.debug(
                f"Command finished. stdout={process.stdout}, " "stderr={process.stderr}"
            )

            return Result(ResultType.COMPLETED)
        except subprocess.CalledProcessError as e:
            LOG.exception("Error bootstrapping Juju")
            return Result(ResultType.FAILED, str(e))


class CreateModelStep(BaseStep, JujuStepHelper):
    """Creates the specified model name."""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__("Create model", f"Creating {model} model")
        self.jhelper = jhelper
        self.model = model

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return self.check_model_present(self.model)

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        LOG.debug(f"Adding model: {self.model}")
        result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.add_model(self.model)
        )

        if result:
            return Result(ResultType.COMPLETED)
        else:
            return Result(ResultType.FAILED, f"Error in creation of model {self.model}")


class DeployBundleStep(BaseStep):
    """Creates the specified model name."""

    def __init__(self, jhelper: JujuHelper, model: str, bundle: Path, name: str):
        super().__init__("Deploy bundle", f"Deploying {name} bundle")

        self.jhelper = jhelper
        self.model = model
        self.bundle = bundle
        self.name = name
        self.options = ["--trust"]

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """

        apps_status = asyncio.get_event_loop().run_until_complete(
            self.jhelper.get_model_status(self.model, timeout=0)
        )

        LOG.debug(f"Status of model {self.model}: {apps_status}")

        # TODO(hemanth): If all apps are active, skipping deploy bundle
        # Running bootstrap command multiple times with some apps not active
        # is destructive as deploy_bundle kills all units of application
        # using SIGTERM in single go where as upgrade_charm does the same
        # one unit after another.
        # Deploy bundle logic should change to deploy application by
        # application checking current status instead of bundle deploy.
        if apps_status:
            for app, status in apps_status.items():
                if status != "active":
                    return False
            return True

        return False

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.deploy_bundle(self.model, self.bundle)
        )

        if result:
            return Result(ResultType.COMPLETED)
        else:
            return Result(ResultType.FAILED, f"Error deploying bundle {self.name}")


class DestroyModelStep(BaseStep, JujuStepHelper):
    """Destroys the specified model name."""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__("Destroy model", f"Destroying model {model}")

        self.jhelper = jhelper
        self.model = model
        self.options = ["--destroy-storage", "-y"]

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return not self.check_model_present(self.model)

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.destroy_model(self.model)
        )

        if result:
            return Result(ResultType.COMPLETED)
        else:
            return Result(ResultType.FAILED, "Error destroying model")


class ModelStatusStep(BaseStep, JujuStepHelper):
    """Get the status of the specified model name."""

    def __init__(
        self,
        jhelper: JujuHelper,
        model: str,
        states: Optional[Path] = None,
        timeout: Optional[int] = None,
    ):
        super().__init__(
            "Model status", f"Retrieving status of applications in model {model}"
        )

        self.jhelper = jhelper
        self.model = model
        self.states = states
        self.timeout = timeout or 0

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return not self.check_model_present(self.model)

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            apps_status = asyncio.get_event_loop().run_until_complete(
                self.jhelper.get_model_status(self.model, timeout=self.timeout)
            )

            status_message = []
            for app, status in apps_status.items():
                message = f"App {app} is in {status} state"
                status_message.append(message)

            return Result(ResultType.COMPLETED, status_message)
        except Exception as e:  # noqa
            LOG.exception("Error getting status of model")
            return Result(ResultType.FAILED, str(e))


class WriteModelStatusStep(BaseStep, JujuStepHelper):
    """Get the status of the specified model name."""

    def __init__(
        self,
        jhelper: JujuHelper,
        model: str,
        file_path: str,
        timeout: Optional[int] = None,
    ):
        super().__init__("Write Model status", f"Record status of model {model}")

        self.jhelper = jhelper
        self.model = model
        self.file_path = file_path
        self.timeout = timeout or 0

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return not self.check_model_present(self.model)

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            _status = asyncio.get_event_loop().run_until_complete(
                self.jhelper.get_model_status_full(self.model, timeout=self.timeout)
            )
            # Running json.dump directly on the json returned by to_json
            # results in a single line. There is probably a better way of
            # doing this.
            status = json.loads(_status.to_json())
            with open(self.file_path, "w") as f:
                json.dump(status, f, ensure_ascii=False, indent=4)
            return Result(ResultType.COMPLETED, "Inspecting Model Status")
        except Exception as e:  # noqa
            return Result(ResultType.FAILED, str(e))


class WriteCharmLog(BaseStep, JujuStepHelper):
    def __init__(
        self,
        jhelper: JujuHelper,
        model: str,
        file_path: str,
    ):
        super().__init__(
            "Get charm logs model", f"Getting charm logs for {model} model"
        )
        self.jhelper = jhelper
        self.model = model
        self.file_path = file_path

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return not self.check_model_present(self.model)

    def run(self):
        try:
            # libjuju model.debug_log is broken.
            cmd = [
                self._get_juju_binary(),
                "debug-log",
                "--model",
                self.model,
                "--replay",
                "--no-tail",
            ]
            # Stream output directly to the file to avoid holding the entire
            # blob of data in RAM.
            with open(self.file_path, "wb") as f:
                subprocess.check_call(cmd, stdout=f)
        except subprocess.CalledProcessError as e:
            return Result(ResultType.FAILED, str(e))
        return Result(ResultType.COMPLETED, "Inspecting Charm Log")
