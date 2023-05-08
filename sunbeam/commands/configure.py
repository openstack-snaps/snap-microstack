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
import glob
import ipaddress
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import click
import netifaces
from rich.console import Console

import sunbeam.commands.question_helper as question_helper
from sunbeam import utils
from sunbeam.commands.juju import JujuHelper
from sunbeam.commands.ohv import UpdateExternalNetworkConfigStep
from sunbeam.commands.terraform import (
    TerraformException,
    TerraformHelper,
    TerraformInitStep,
)
from sunbeam.jobs.common import BaseStep, Result, ResultType, Status

LOG = logging.getLogger(__name__)
console = Console()


def get_nic_macs(nic: str) -> list:
    """Return list of mac addresses associates with nic."""
    addrs = netifaces.ifaddresses(nic)
    return sorted([a["addr"] for a in addrs[netifaces.AF_LINK]])


def is_configured(nic: str) -> bool:
    """Whether interface is configured with IPv4 or IPv6 address."""
    addrs = netifaces.ifaddresses(nic)
    return bool(addrs.get(netifaces.AF_INET) or addrs.get(netifaces.AF_INET6))


def get_free_nics() -> list:
    """Return a list of nics which doe not have a v4 or v6 address."""
    virtual_nic_dir = "/sys/devices/virtual/net/*"
    virtual_nics = [Path(p).name for p in glob.glob(virtual_nic_dir)]
    bond_nic_dir = "/proc/net/bonding/*"
    bonds = [Path(p).name for p in glob.glob(bond_nic_dir)]
    bond_macs = []
    for bond_iface in bonds:
        bond_macs.extend(get_nic_macs(bond_iface))
    candidate_nics = []
    for nic in netifaces.interfaces():
        if nic in bonds and not is_configured(nic):
            LOG.debug(f"Found bond {nic}")
            candidate_nics.append(nic)
            continue
        macs = get_nic_macs(nic)
        if list(set(macs) & set(bond_macs)):
            LOG.debug(f"Skipping {nic} it is part of a bond")
            continue
        if nic in virtual_nics:
            LOG.debug(f"Skipping {nic} it is virtual")
            continue
        if is_configured(nic):
            LOG.debug(f"Skipping {nic} it is configured")
        else:
            LOG.debug(f"Found nic {nic}")
            candidate_nics.append(nic)
    return candidate_nics


def get_free_nic() -> str:
    nics = get_free_nics()
    nic = ""
    if len(nics) > 0:
        nic = nics[0]
    return nic


def user_questions():
    return {
        "username": question_helper.PromptQuestion(
            "Username to use for access to OpenStack", default_value="demo"
        ),
        "password": question_helper.PromptQuestion(
            "Password to use for access to OpenStack",
            default_function=question_helper.generate_password,
        ),
        "cidr": question_helper.PromptQuestion(
            "Network range to use for project network", default_value="192.168.122.0/24"
        ),
        "security_group_rules": question_helper.ConfirmQuestion(
            "Setup security group rules for SSH and ICMP ingress", default_value=True
        ),
        "remote_access_location": question_helper.ConfirmQuestion(
            "Local or remote access to VMs",
            choices=[utils.LOCAL_ACCESS, utils.REMOTE_ACCESS],
            default_value=utils.LOCAL_ACCESS,
        ),
    }


def ext_net_questions():
    return {
        "cidr": question_helper.PromptQuestion(
            "CIDR of network to use for external networking",
            default_value="10.20.20.0/24",
        ),
        "gateway": question_helper.PromptQuestion(
            "IP address of default gateway for external network", default_value=None
        ),
        "start": question_helper.PromptQuestion(
            "Start of IP allocation range for external network", default_value=None
        ),
        "end": question_helper.PromptQuestion(
            "End of IP allocation range for external network", default_value=None
        ),
        "network_type": question_helper.PromptQuestion(
            "Network type for access to external network",
            choices=["flat", "vlan"],
            default_value="flat",
        ),
        "segmentation_id": question_helper.PromptQuestion(
            "VLAN ID to use for external network", default_value=0
        ),
        "nic": question_helper.PromptQuestion(
            "Free network interface microstack can use for external traffic",
            default_value=get_free_nic(),
        ),
    }


def ext_net_questions_local_only():
    return {
        "cidr": question_helper.PromptQuestion(
            (
                "CIDR of OpenStack external network - arbitrary but must not "
                "be in use"
            ),
            default_value="10.20.20.0/24",
        ),
        "start": question_helper.PromptQuestion(
            "Start of IP allocation range for external network", default_value=None
        ),
        "end": question_helper.PromptQuestion(
            "End of IP allocation range for external network", default_value=None
        ),
        "network_type": question_helper.PromptQuestion(
            "Network type for access to external network",
            choices=["flat", "vlan"],
            default_value="flat",
        ),
        "segmentation_id": question_helper.PromptQuestion(
            "VLAN ID to use for external network", default_value=0
        ),
    }


VARIABLE_DEFAULTS = {
    "user": {
        "username": "demo",
        "cidr": "192.168.122.0/24",
        "security_group_rules": True,
    },
    "external_network": {
        "cidr": "10.20.20.0/24",
        "gateway": None,
        "start": None,
        "end": None,
        "physical_network": "physnet1",
        "network_type": "flat",
        "segmentation_id": 0,
    },
}


def _retrieve_admin_credentials(jhelper: JujuHelper, model: str) -> dict:
    """Retrieve cloud admin credentials.

    Retrieve cloud admin credentials from keystone and
    return as a dict suitable for use with subprocess
    commands.  Variables are prefixed with OS_.
    """
    app = "keystone"
    action_cmd = "get-admin-account"
    action_result = asyncio.get_event_loop().run_until_complete(
        jhelper.run_action(model, app, action_cmd)
    )

    if action_result.get("return-code", 0) > 1:
        _message = "Unable to retrieve openrc from Keystone service"
        raise click.ClickException(_message)

    return {
        "OS_USERNAME": action_result.get("username"),
        "OS_PASSWORD": action_result.get("password"),
        "OS_AUTH_URL": action_result.get("public-endpoint"),
        "OS_USER_DOMAIN_NAME": action_result.get("user-domain-name"),
        "OS_PROJECT_DOMAIN_NAME": action_result.get("project-domain-name"),
        "OS_PROJECT_NAME": action_result.get("project-name"),
        "OS_AUTH_VERSION": action_result.get("api-version"),
        "OS_IDENTITY_API_VERSION": action_result.get("api-version"),
    }


class UserOpenRCStep(BaseStep):
    """Generate openrc for created cloud user."""

    def __init__(self, auth_url: str, auth_version: str, openrc: str, clouds: str):
        super().__init__("Generate user openrc", "Generating openrc for cloud usage")
        self.auth_url = auth_url
        self.auth_version = auth_version
        self.openrc = openrc
        self.clouds = clouds

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def run(self, status: Optional[Status]) -> Result:
        try:
            snap = utils.get_snap()
            terraform = str(snap.paths.snap / "bin" / "terraform")
            cmd = [terraform, "output", "-json"]
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=snap.paths.user_common / "etc" / "configure",
            )
            LOG.debug(
                f"Command finished. stdout={process.stdout}, stderr={process.stderr}"
            )
            tf_output = json.loads(process.stdout)
            self._print_openrc(tf_output)
            self._print_clouds_yaml(tf_output)
            return Result(ResultType.COMPLETED)
        except subprocess.CalledProcessError as e:
            LOG.exception("Error initializing Terraform")
            return Result(ResultType.FAILED, str(e))

    def _print_openrc(self, tf_output: dict) -> None:
        """Print openrc to console and save to disk using provided information"""
        _openrc = f"""# openrc for {tf_output["OS_USERNAME"]["value"]}
export OS_AUTH_URL={self.auth_url}
export OS_USERNAME={tf_output["OS_USERNAME"]["value"]}
export OS_PASSWORD={tf_output["OS_PASSWORD"]["value"]}
export OS_USER_DOMAIN_NAME={tf_output["OS_USER_DOMAIN_NAME"]["value"]}
export OS_PROJECT_DOMAIN_NAME={tf_output["OS_PROJECT_DOMAIN_NAME"]["value"]}
export OS_PROJECT_NAME={tf_output["OS_PROJECT_NAME"]["value"]}
export OS_AUTH_VERSION={self.auth_version}
export OS_IDENTITY_API_VERSION={self.auth_version}"""
        if self.openrc:
            message = f"Writing openrc to {self.openrc} ... "
            console.status(message)
            with open(self.openrc, "w") as f_openrc:
                os.fchmod(f_openrc.fileno(), mode=0o640)
                f_openrc.write(_openrc)
            console.print(f"{message}[green]done[/green]")
        else:
            console.print(_openrc)

    def _print_clouds_yaml(self, tf_output: dict) -> None:
        """Print a clouds.yaml file and save to disk using provided information"""
        _cloudsyaml = f"""
clouds:
  sunbeam:
    auth:
      auth_url: {self.auth_url}
      project_name: {tf_output["OS_PROJECT_NAME"]["value"]}
      username: {tf_output["OS_USERNAME"]["value"]}
      password: {tf_output["OS_PASSWORD"]["value"]}
      user_domain_name: {tf_output["OS_USER_DOMAIN_NAME"]["value"]}
      project_domain_name: {tf_output["OS_PROJECT_DOMAIN_NAME"]["value"]}
    identity_api_version: {self.auth_version}
        """
        if self.clouds:
            message = f"Writing clouds.yaml to {self.clouds} ... "
            console.status(message)
            with open(self.clouds, "w") as f_clouds:
                os.fchmod(f_clouds.fileno(), mode=0o640)
                f_clouds.write(_cloudsyaml)
        else:
            console.print(_cloudsyaml)

class ConfigureCloudStep(BaseStep):
    """Default cloud configuration for all-in-one install."""

    def __init__(
        self,
        tfhelper: TerraformHelper,
        preseed_file: str = None,
        accept_defaults: bool = False,
    ):
        super().__init__(
            "Configure OpenStack cloud", "Configuring OpenStack cloud for use"
        )
        self.accept_defaults = accept_defaults
        self.preseed_file = preseed_file
        self.tfhelper = tfhelper
        self.variables = question_helper.load_answers()
        for section in ["user", "external_network"]:
            if not self.variables.get(section):
                self.variables[section] = {}

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def has_prompts(self) -> bool:
        return True

    def prompt(self, console: Optional[Console] = None) -> None:
        """Prompt the user for basic cloud configuration.

        Prompts the user for required information for cloud configuration.

        :param console: the console to prompt on
        :type console: rich.console.Console (Optional)
        """
        if self.preseed_file:
            preseed = question_helper.read_preseed(self.preseed_file)
        else:
            preseed = {}
        user_bank = question_helper.QuestionBank(
            questions=user_questions(),
            console=console,
            preseed=preseed.get("user"),
            previous_answers=self.variables.get("user"),
            accept_defaults=self.accept_defaults,
        )
        # User configuration
        self.variables["user"]["username"] = user_bank.username.ask()
        self.variables["user"]["password"] = user_bank.password.ask()
        self.variables["user"]["cidr"] = user_bank.cidr.ask()
        self.variables["user"][
            "security_group_rules"
        ] = user_bank.security_group_rules.ask()
        self.variables["user"][
            "remote_access_location"
        ] = user_bank.remote_access_location.ask()

        # External Network Configuration
        if self.variables["user"]["remote_access_location"] == utils.LOCAL_ACCESS:
            ext_net_bank = question_helper.QuestionBank(
                questions=ext_net_questions_local_only(),
                console=console,
                preseed=preseed.get("external_network"),
                previous_answers=self.variables.get("external_network"),
                accept_defaults=self.accept_defaults,
            )
        else:
            ext_net_bank = question_helper.QuestionBank(
                questions=ext_net_questions(),
                console=console,
                preseed=preseed.get("external_network"),
                previous_answers=self.variables.get("external_network"),
                accept_defaults=self.accept_defaults,
            )
        self.variables["external_network"]["cidr"] = ext_net_bank.cidr.ask()
        external_network = ipaddress.ip_network(
            self.variables["external_network"]["cidr"]
        )
        external_network_hosts = list(external_network.hosts())
        default_gateway = self.variables["external_network"].get("gateway") or str(
            external_network_hosts[0]
        )
        if self.variables["user"]["remote_access_location"] == utils.LOCAL_ACCESS:
            self.variables["external_network"]["gateway"] = default_gateway
        else:
            self.variables["external_network"]["nic"] = ext_net_bank.nic.ask()
            self.variables["external_network"]["gateway"] = ext_net_bank.gateway.ask(
                new_default=default_gateway
            )
        default_allocation_range_start = self.variables["external_network"].get(
            "start"
        ) or str(external_network_hosts[1])
        self.variables["external_network"]["start"] = ext_net_bank.start.ask(
            new_default=default_allocation_range_start
        )
        default_allocation_range_end = self.variables["external_network"].get(
            "end"
        ) or str(external_network_hosts[-1])
        self.variables["external_network"]["end"] = ext_net_bank.end.ask(
            new_default=default_allocation_range_end
        )
        self.variables["external_network"]["physical_network"] = VARIABLE_DEFAULTS[
            "external_network"
        ]["physical_network"]

        self.variables["external_network"][
            "network_type"
        ] = ext_net_bank.network_type.ask()
        if self.variables["external_network"]["network_type"] == "vlan":
            self.variables["external_network"][
                "segmentation_id"
            ] = ext_net_bank.segmentation_id.ask()
        else:
            self.variables["external_network"]["segmentation_id"] = 0

        LOG.debug(self.variables)
        question_helper.write_answers(self.variables)

    def run(self, status: Optional[Status]) -> Result:
        """Execute configuration using terraform."""
        try:
            self.tfhelper.apply()
            return Result(ResultType.COMPLETED)
        except TerraformException as e:
            LOG.exception("Error configuring cloud")
            return Result(ResultType.FAILED, str(e))


@click.command()
@click.option("-a", "--accept-defaults", help="Accept all defaults.", is_flag=True)
@click.option("-p", "--preseed", help="Preseed file.")
@click.option("-o", "--openrc", help="Output file for cloud access details.")
@click.option("-c", "--clouds", help="Output file for clouds.yaml")
def configure(
    openrc: str = None, preseed: str = None, accept_defaults: bool = False, clouds: str = None
) -> None:
    """Configure cloud with some sane defaults."""
    snap = utils.get_snap()
    # NOTE: install to user writable location
    src = snap.paths.snap / "etc" / "configure"
    dst = snap.paths.user_common / "etc" / "configure"
    LOG.debug(f"Updating {dst} from {src}...")
    shutil.copytree(src, dst, dirs_exist_ok=True)

    model = snap.config.get("control-plane.model")
    jhelper = JujuHelper()
    models = asyncio.get_event_loop().run_until_complete(jhelper.get_models())
    LOG.debug(f"Juju models: {models}")
    if model not in models:
        LOG.error(f"Expected model {model} missing")
        raise click.ClickException("Please run `microstack bootstrap` first")
    admin_credentials = _retrieve_admin_credentials(jhelper, model)
    tfhelper = TerraformHelper(
        path=snap.paths.user_common / "etc" / "configure", env=admin_credentials
    )
    ext_network_file = (
        snap.paths.user_common / "etc" / "configure" / "terraform.tfvars.json"
    )

    plan = [
        TerraformInitStep(tfhelper=tfhelper),
        ConfigureCloudStep(
            tfhelper=tfhelper,
            preseed_file=preseed,
            accept_defaults=accept_defaults,
        ),
        UserOpenRCStep(
            auth_url=admin_credentials["OS_AUTH_URL"],
            auth_version=admin_credentials["OS_AUTH_VERSION"],
            openrc=openrc,
            clouds=clouds
        ),
        UpdateExternalNetworkConfigStep(ext_network=ext_network_file),
    ]
    for step in plan:
        LOG.debug(f"Starting step {step.name}")
        message = f"{step.description} ... "
        with console.status(message) as status:
            if step.has_prompts():
                status.stop()
                step.prompt(console)
                status.start()

            if step.is_skip():
                LOG.debug(f"Skipping step {step.name}")
                console.print(f"{message}[green]done[/green]")
                continue

            LOG.debug(f"Running step {step.name}")
            result = step.run(status)
            LOG.debug(
                f"Finished running step {step.name}. Result: {result.result_type}"
            )

        if result.result_type == ResultType.FAILED:
            console.print(f"{message}[red]failed[/red]")
            raise click.ClickException(result.message)

        console.print(f"{message}[green]done[/green]")

    asyncio.get_event_loop().run_until_complete(jhelper.disconnect_controller())
