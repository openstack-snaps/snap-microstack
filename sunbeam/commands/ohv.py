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
import logging
import operator
from typing import Optional

from sunbeam.commands.juju import JujuHelper
from sunbeam.jobs.common import BaseStep, InstallSnapStep, Result, ResultType
from sunbeam.ohv_config.client import Client as ohvClient
from sunbeam.ohv_config.config import (
    IdentityServiceConfig,
    NetworkConfig,
    RabbitMQConfig,
)

LOG = logging.getLogger(__name__)


class OHVBaseStep(BaseStep):
    def __init__(self, name: str, description: str):
        super().__init__(name, description)

        # Default values to None
        self.app = None
        self.action_cmd = None
        self.action_params = {}
        self.config_obj = None
        self.get_config_func_name = None
        self.update_config_func_name = None

        # Mapping of keys from Action result to
        # openstack-hypervisor configuration keys
        self.map_alias = {}

    def is_skip(self, status: Optional["Status"] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """

        # Get configuration from openstack control plane
        self.ohv_client = ohvClient()
        self.action_result = asyncio.get_event_loop().run_until_complete(
            JujuHelper.run_action(self.app, self.action_cmd, self.action_params)
        )
        LOG.debug(
            f"Action result for app {self.app} action {self.action_cmd} "
            f"with params {self.action_params}: {self.action_result}"
        )

        # The keys from action result dict and openstack-hypervisor config
        # might be diferent, so add the mapping keys to action result
        # For eg., if action_result returns 'public-endpoint':'http://localhost:1234'
        # and corresponding openstack-hypervisor key is auth-url, add
        # 'auth-url':'http://localhost:1234' to the action result.
        missing_keys = {
            v: self.action_result[k]
            for k, v in self.map_alias.items()
            if k in self.action_result
        }
        self.action_result.update(missing_keys)

        self.config = self.config_obj.parse_obj(self.action_result)
        LOG.debug(f"Config from openstack control plane: {self.config}")

        # Get configuration from openstack-hypervisor snap
        get_config_func = getattr(self.ohv_client.config, self.get_config_func_name)
        config_from_snap = get_config_func()
        LOG.debug(f"Config from openstack-hypervisor snap: {config_from_snap}")

        # Compare both configs and skip if they are equal
        if operator.eq(self.config.dict(), config_from_snap.dict()):
            return True

        return False

    def run(self, status: Optional["Status"] = None) -> Result:
        """Run the step to completion.

        Invoked when the step is run and returns a ResultType to indicate

        :return:
        """
        if self.action_result.get("return-code", 1) == 1:
            return Result(ResultType.FAILED, "Juju action returned error")

        try:
            config_func = getattr(self.ohv_client.config, self.update_config_func_name)
            result = config_func(self.config)
            LOG.debug(f"Result after updating rabbitmq config: {result}")
        except Exception as e:
            LOG.exception("Error setting config for openstack-hypervisor")
            return Result(ResultType.FAILED, str(e))

        return Result(ResultType.COMPLETED)


class EnsureOVHInstalled(InstallSnapStep):
    """Validates the openstack-hypervisor is installed."""

    def __init__(self, channel: str = "latest/stable"):
        super().__init__(snap="openstack-hypervisor", channel=channel)


class UpdateIdentityServiceConfigStep(OHVBaseStep):
    """Update Identity config for openstack-hypervisor snap"""

    def __init__(self):
        super().__init__(
            "Update Identity Config",
            "Update identity settings to openstack-hypervisor snap",
        )

        self.app = "keystone"
        self.action_cmd = "get-service-account"
        # TODO(hemanth): Username should be modified with hostname of
        # each hypervisor prefixed with nova-
        self.action_params = {"username": "nova-hypervisor"}

        self.config_obj = IdentityServiceConfig()
        self.get_config_func_name = "get_identity_config"
        self.update_config_func_name = "update_identity_config"
        # Map the keys from Action result to openstack-hypervisor config keys
        self.map_alias = {"public-endpoint": "auth-url", "region": "region-name"}


class UpdateRabbitMQConfigStep(OHVBaseStep):
    """Update Rabbitmq Config for openstack-hypervisor snap"""

    def __init__(self):
        super().__init__(
            "Update Rabbitmq Config", "Update rabbitmq url to openstack-hypervisor snap"
        )

        self.app = "rabbitmq"
        self.action_cmd = "get-service-account"
        self.action_params = {"username": "nova", "vhost": "openstack"}

        self.config_obj = RabbitMQConfig()
        self.get_config_func_name = "get_rabbitmq_config"
        self.update_config_func_name = "update_rabbitmq_config"


class UpdateNetworkConfigStep(OHVBaseStep):
    """Update Network Config for openstack-hypervisor snap"""

    def __init__(self):
        super().__init__(
            "Update Network Config", "Update ovn-sb url to openstack-hypervisor snap"
        )

        self.app = "ovn-relay"
        self.action_cmd = "get-southbound-db-url"
        self.action_params = {}

        self.config_obj = NetworkConfig()
        self.get_config_func_name = "get_network_config"
        self.update_config_func_name = "update_network_config"
        self.map_alias = {"url": "ovn-sb-connection"}
