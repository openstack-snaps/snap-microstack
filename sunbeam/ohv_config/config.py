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

import typing
from typing import Optional

from pydantic import AnyUrl, BaseModel, Field, IPvAnyAddress, IPvAnyInterface

from sunbeam.ohv_config import service


class RabbitMQUrl(AnyUrl):
    allowed_schemes = {"rabbit", "amqp"}
    host_required = True


class IdentityServiceConfig(BaseModel):
    """Data Model for Keystone Identity settings for the hypervisor services."""

    auth_url: Optional[AnyUrl] = Field(alias="auth-url", default=None)
    username: Optional[str]
    password: Optional[str]
    user_domain_name: Optional[str] = Field(
        alias="user-domain-name",
        default="service_domain",
    )
    project_name: Optional[str] = Field(
        alias="project-name",
        default="services",
    )
    project_domain_name: Optional[str] = Field(
        alias="project-domain-name",
        default="service_domain",
    )
    region_name: Optional[str] = Field(
        alias="region-name",
        default="RegionOne",
    )


class RabbitMQConfig(BaseModel):
    """Data Model for RabbitMQ configuration settings."""

    url: RabbitMQUrl = Field(
        alias="url",
        default="rabbit://localhost:5672",
    )


class ComputeConfig(BaseModel):
    """Data Model for Nova configuration settings."""

    cpu_mode: str = Field(alias="cpu-mode", default="host-model")
    virt_type: str = Field(alias="virt-type", default="auto")
    cpu_models: Optional[str] = Field(alias="cpu-models")
    spice_proxy_address: Optional[IPvAnyAddress] = Field(alias="spice-proxy-address")


class NetworkConfig(BaseModel):
    """Data Model for network configuration settings."""

    physnet_name: str = Field(alias="physnet-name", default="physnet1")
    external_bridge: str = Field(alias="external-bridge", default="br-ex")
    external_bridge_address: Optional[IPvAnyInterface] = Field(
        alias="external-bridge-address"
    )
    dns_domain = Field(alias="dns-domain", default="openstack.local")
    dns_servers: IPvAnyAddress = Field(alias="dns-servers", default="8.8.8.8")
    ovn_sb_connection: str = Field(
        alias="ovn-sb-connection", default="tcp:127.0.0.1:6642"
    )
    ovn_key: Optional[str] = Field(alias="ovn-key")
    ovn_cert: Optional[str] = Field(alias="ovn-cert")
    ovn_cacert: Optional[str] = Field(alias="ovn-cacert")
    enable_gateway: bool = Field(alias="enable-gateway", default=False)
    ip_address: Optional[IPvAnyAddress] = Field(alias="ip-address")
    gateway_nic: Optional[str] = Field(alias="gateway-nic")


class NodeConfig(BaseModel):
    """Data model for the node configuration settings."""

    fqdn: Optional[str]
    ip_address: Optional[IPvAnyAddress] = Field(alias="ip-address")


class LoggingConfig(BaseModel):
    """Data model for the logging configuration for the hypervisor."""

    debug: bool = Field(default=False)


class ConfigService(service.BaseService):
    """Lists and manages config."""

    def get_identity_config(self) -> IdentityServiceConfig:
        """Returns the identity service configuration."""

        identity_config = self._get("/settings/identity")
        return IdentityServiceConfig.parse_obj(identity_config)

    def update_identity_config(
        self, config: typing.Union[IdentityServiceConfig, dict]
    ) -> IdentityServiceConfig:
        """Updates the configuration for the Identity Service.

        :param config:
        :return:
        """
        if isinstance(config, dict):
            config = IdentityServiceConfig(**config)

        result = self._patch("/settings/identity", data=config.json(by_alias=True))
        return result

    def get_rabbitmq_config(self) -> RabbitMQConfig:
        """Returns the rabbitmq configuration."""

        rabbitmq_config = self._get("/settings/rabbitmq")
        return RabbitMQConfig.parse_obj(rabbitmq_config)

    def update_rabbitmq_config(
        self, config: typing.Union[RabbitMQConfig, dict]
    ) -> RabbitMQConfig:
        """Updates the configuration for the Identity Service.

        :param config:
        :return:
        """
        if isinstance(config, dict):
            config = RabbitMQConfig(**config)

        result = self._patch("/settings/rabbitmq", data=config.json(by_alias=True))
        return result

    def get_network_config(self) -> NetworkConfig:
        """Returns the network configuration."""

        network_config = self._get("/settings/network")
        return NetworkConfig.parse_obj(network_config)

    def update_network_config(
        self, config: typing.Union[NetworkConfig, dict]
    ) -> NetworkConfig:
        """Updates the Network related configuration.

        :param config:
        :return:
        """
        if isinstance(config, dict):
            config = NetworkConfig(**config)

        result = self._patch("/settings/network", data=config.json(by_alias=True))
        return result

    def get_node_config(self) -> NodeConfig:
        """Returns the node configuration."""

        node_config = self._get("/settings/node")
        return NodeConfig.parse_obj(node_config)

    def update_node_config(self, config: typing.Union[NodeConfig, dict]) -> NodeConfig:
        """Updates the Node related configuration.

        :param config:
        :return:
        """
        if isinstance(config, dict):
            config = NodeConfig(**config)

        result = self._patch("/settings/node", data=config.json(by_alias=True))
        return result

    def reset_config(self) -> dict:
        """Resets the hypervisor configuration."""
        result = self._post("/reset")
        return result


class HealthService(service.BaseService):
    """Query Hypervisor health."""

    def get_health(self):
        """Returns the health of the hypervisor snap."""
        return self._get("/health")
