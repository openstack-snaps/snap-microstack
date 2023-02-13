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
import ipaddress
import json
import logging
import operator
from pathlib import Path
from typing import Optional

import sunbeam.commands.question_helper as question_helper
from sunbeam import utils
from sunbeam.commands.juju import JujuHelper
from sunbeam.jobs.common import BaseStep, InstallSnapStep, Result, ResultType
from sunbeam.ohv_config.client import Client as ohvClient

LOG = logging.getLogger(__name__)


class OHVBaseStep(BaseStep):
    def __init__(self, name: str, description: str):
        super().__init__(name, description)

        self.action_results = []
        self.config_from_snap = None

        self.jhelper = None
        self.model = None
        self.action_results = []
        self.config = None

    def _get_compute_node_ip(self) -> str:
        ip = utils.get_local_ip_by_default_route()

        """
        ip = "127.0.0.1"

        snap = Snap()
        compute_info = snap.config.get("compute.node")

        cn = utils.get_fqdn()
        if cn in compute_info:
            ip = compute_info[cn].get("ip", "127.0.0.1")
        """

        return ip


class EnsureOVHInstalled(InstallSnapStep):
    """Validates the openstack-hypervisor is installed."""

    def __init__(self, channel: str = "latest/stable"):
        super().__init__(snap="openstack-hypervisor", channel=channel)


class UpdateIdentityServiceConfigStep(OHVBaseStep):
    """Update Identity config for openstack-hypervisor snap"""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__(
            "Update Identity Config",
            "Updating hypervisor identity configuration",
        )
        self.jhelper = jhelper
        self.model = model

        self.ohv_client = ohvClient()

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        skip = True

        # Get configuration from openstack-hypervisor snap
        self.config = self.ohv_client.config.get_identity_config()
        LOG.debug(f"Config from openstack-hypervisor snap: {self.config}")

        hostname = utils.get_hostname()

        # Retrieve config from juju actions
        app = "keystone"
        action_cmd = "get-service-account"
        action_params = {"username": hostname}
        action_result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.run_action(self.model, app, action_cmd, action_params)
        )
        self.action_results.append(action_result)
        LOG.debug(
            f"Action result for app {app} action {action_cmd} "
            f"with params {action_params}: {action_result}"
        )

        auth_url = action_result.get("public-endpoint", None)
        if not operator.eq(self.config.auth_url, auth_url):
            self.config.auth_url = auth_url
            skip = False
        username = action_result.get("username", None)
        if not operator.eq(self.config.username, username):
            self.config.username = username
            skip = False
        password = action_result.get("password", None)
        if not operator.eq(self.config.password, password):
            self.config.password = password
            skip = False
        user_domain_name = action_result.get("user-domain-name", None)
        if not operator.eq(self.config.user_domain_name, user_domain_name):
            self.config.username = user_domain_name
            skip = False
        project_name = action_result.get("project-name", None)
        if not operator.eq(self.config.project_name, project_name):
            self.config.project_name = project_name
            skip = False
        project_domain_name = action_result.get("project-domain-name", None)
        if not operator.eq(self.config.project_domain_name, project_domain_name):
            self.config.project_name = project_domain_name
            skip = False
        region_name = action_result.get("region", None)
        if not operator.eq(self.config.region_name, region_name):
            self.config.region_name = region_name
            skip = False

        return skip

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        for action_result in self.action_results:
            if action_result.get("return-code", 1) == 1:
                return Result(ResultType.FAILED, "Juju action returned error")

        try:
            LOG.debug(f"Config to apply on openstack-hypervisor snap: {self.config}")
            result = self.ohv_client.config.update_identity_config(self.config)
            LOG.debug(f"Result after updating identity config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class UpdateRabbitMQConfigStep(OHVBaseStep):
    """Update Rabbitmq Config for openstack-hypervisor snap"""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__(
            "Update RabbitMQ Config", "Updating hypervisor RabbitMQ configuration"
        )

        self.jhelper = jhelper
        self.model = model

        self.ohv_client = ohvClient()

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        skip = True

        # Get configuration from openstack-hypervisor snap
        self.config = self.ohv_client.config.get_rabbitmq_config()
        LOG.debug(f"Config from openstack-hypervisor snap: {self.config}")

        # Retrieve config from juju actions
        app = "rabbitmq"
        action_cmd = "get-service-account"
        action_params = {"username": "nova", "vhost": "openstack"}
        action_result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.run_action(self.model, app, action_cmd, action_params)
        )
        self.action_results.append(action_result)
        LOG.debug(
            f"Action result for app {app} action {action_cmd} "
            f"with params {action_params}: {action_result}"
        )

        url = action_result.get("url", None)
        if not operator.eq(self.config.url, url):
            self.config.url = url
            skip = False

        return skip

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        for action_result in self.action_results:
            if action_result.get("return-code", 1) == 1:
                return Result(ResultType.FAILED, "Juju action returned error")

        try:
            LOG.debug(f"Config to apply on openstack-hypervisor snap: {self.config}")
            result = self.ohv_client.config.update_rabbitmq_config(self.config)
            LOG.debug(f"Result after updating rabbitmq config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class UpdateNetworkConfigStep(OHVBaseStep):
    """Update Network Config for openstack-hypervisor snap"""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__(
            "Update Network Config", "Updating hypervisor OVN configuration"
        )

        self.jhelper = jhelper
        self.model = model
        self.action_results = []

        self.ohv_client = ohvClient()

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        skip = True

        # Get configuration from openstack-hypervisor snap
        self.config = self.ohv_client.config.get_network_config()
        LOG.debug(f"Config from openstack-hypervisor snap: {self.config}")

        # Get required info for juju actions
        # TODO(hemanth): cn needs to be updated from cluster
        sans = ""
        cn = utils.get_fqdn()
        sans = utils.get_local_ip_addresses()
        sans = " ".join(sans)

        """
        snap = Snap()
        self.compute_info = snap.config.get("compute.node")
        if cn in self.compute_info:
            sans = self.compute_info[cn]["sans"]
        """

        # Retrieve config from juju actions
        app = "ovn-relay"
        action_cmd = "get-southbound-db-url"
        action_params = {}
        action_result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.run_action(self.model, app, action_cmd, action_params)
        )
        self.action_results.append(action_result)
        LOG.debug(
            f"Action result for app {app} action {action_cmd} "
            f"with params {action_params}: {action_result}"
        )

        url = action_result.get("url", None)
        if not operator.eq(self.config.ovn_sb_connection, url):
            self.config.ovn_sb_connection = url
            skip = False

        app = "certificate-authority"
        action_cmd = "generate-self-signed-certificate"
        action_params = {"common-name": cn, "sans": sans}
        action_result = asyncio.get_event_loop().run_until_complete(
            self.jhelper.run_action(self.model, app, action_cmd, action_params)
        )
        self.action_results.append(action_result)
        LOG.debug(
            f"Action result for app {app} action {action_cmd} "
            f"with params {action_params}: {action_result}"
        )

        # Encode TLS keys to base64
        action_result["ovn_key"] = utils.encode_tls(action_result["private-key"])
        action_result["ovn_cert"] = utils.encode_tls(action_result["certificate"])
        action_result["ovn_cacert"] = utils.encode_tls(action_result["issuing-ca"])

        for attrib in ["ovn_key", "ovn_cert", "ovn_cacert"]:
            value_from_snap = vars(self.config).get(attrib)
            value_from_action = action_result.get(attrib)
            if not operator.eq(value_from_snap, value_from_action):
                setattr(self.config, attrib, value_from_action)
                skip = False

        return skip

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        for action_result in self.action_results:
            if action_result.get("return-code", 1) == 1:
                return Result(ResultType.FAILED, "Juju action returned error")

        try:
            LOG.debug(f"Config to apply on openstack-hypervisor snap: {self.config}")
            result = self.ohv_client.config.update_network_config(self.config)
            LOG.debug(f"Result after updating network config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class UpdateExternalNetworkConfigStep(OHVBaseStep):
    """Update External Network Config for openstack-hypervisor snap"""

    IPVANYNETWORK_UNSET = "0.0.0.0/0"

    def __init__(self, ext_network: Path):
        super().__init__(
            "Update Network Config",
            "Updating hypervisor external network configuration",
        )

        # File path with external_network details in json format
        self.ext_network_file = ext_network
        self.ext_network = {}

        self.ohv_client = ohvClient()

    def has_prompts(self) -> bool:
        return True

    def prompt(self, console: Optional["Console"] = None) -> None:
        """Prompt the user for local hypervisor externalnetworking.

        Prompts the user for required information for configuration of the
        local node with host only access to instances.

        :param console: the console to prompt on
        :type console: rich.console.Console (Optional)
        """
        # Get configuration from openstack-hypervisor snap
        self.config = self.ohv_client.config.get_network_config()
        LOG.debug(f"Config from openstack-hypervisor snap: {self.config}")

        # Read previously collected information about external network subnet
        with open(self.ext_network_file, "r") as fp:
            _config = json.load(fp)
            self.ext_network = _config.get("external_network", {})
            self.user = _config.get("user", {})

        answers = question_helper.load_answers()
        try:
            remote_access_location = answers["user"]["remote_access_location"]
        except KeyError:
            LOG.warning("Failed to find external_network.remote_access_location answer")
            remote_access_location = (
                str(self.config.external_bridge_address) != self.IPVANYNETWORK_UNSET
            )
        if remote_access_location == utils.LOCAL_ACCESS:
            external_network = ipaddress.ip_network(self.ext_network.get("cidr"))
            bridge_interface = (
                f"{self.ext_network.get('gateway')}/{external_network.prefixlen}"
            )
            self.config.external_bridge_address = bridge_interface
        else:
            self.config.external_bridge_address = self.IPVANYNETWORK_UNSET
            self.config.external_nic = self.ext_network.get("nic")

        self.config.physnet_name = self.ext_network.get("physical_network")

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            LOG.debug(f"Config to apply on openstack-hypervisor snap: {self.config}")
            result = self.ohv_client.config.update_network_config(self.config)
            LOG.debug(f"Result after updating network config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class UpdateNodeConfigStep(OHVBaseStep):
    """Update Node Config for openstack-hypervisor snap"""

    def __init__(self, jhelper: JujuHelper, model: str):
        super().__init__("Update Node Config", "Updating hypervisor Node configuration")

        self.jhelper = jhelper
        self.model = model

        self.ohv_client = ohvClient()

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        skip = True

        # Get configuration from openstack-hypervisor snap
        self.config = self.ohv_client.config.get_node_config()
        LOG.debug(f"Config from openstack-hypervisor snap: {self.config}")

        # Retrieve config from microstack snap
        ip = self._get_compute_node_ip()

        # Skip update if config is same
        if not operator.eq(str(self.config.ip_address), ip):
            self.config.ip_address = ip
            skip = False

        return skip

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            LOG.debug(f"Config to apply on openstack-hypervisor snap: {self.config}")
            result = self.ohv_client.config.update_node_config(self.config)
            LOG.debug(f"Result after updating node config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class ResetConfigStep(OHVBaseStep):
    """Rest Config for openstack-hypervisor snap"""

    def __init__(self):
        super().__init__(
            "Resetting hypervisor ",
            "Resetting openstack-hypervisor configuration to defaults",
        )

        self.ohv_client = ohvClient()

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        try:
            LOG.debug("Reseting configuration on openstack-hypervisor snap")
            result = self.ohv_client.config.reset_config()
            LOG.debug(f"Result after reset {result}")
        except Exception as e:
            LOG.exception("Error resetting configuration for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)
