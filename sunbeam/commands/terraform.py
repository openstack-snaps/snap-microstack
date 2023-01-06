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

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from snaphelpers import Snap

from sunbeam.jobs.common import BaseStep, Result, ResultType, Status

LOG = logging.getLogger(__name__)


class TerraformException(Exception):
    """Terraform related exceptions"""

    def __init__(self, message):
        super().__init__()
        self.message = message

    def __str__(self) -> str:
        return self.message


class TerraformHelper:
    """Helper for interaction with Terraform"""

    def __init__(
        self, path: Path, env: Optional[dict] = None, parallelism: Optional[int] = None
    ):
        self.snap = Snap()
        self.path = path
        self.env = env
        self.parallelism = parallelism
        self.terraform = str(self.snap.paths.snap / "bin" / "terraform")

    def write_tfvars(self, vars: dict) -> None:
        """Write terraform variables file"""
        with open(self.path / "terraform.tfvars.json", "w") as tfvars:
            tfvars.write(json.dumps(vars))

    def init(self) -> None:
        """terraform init"""
        os_env = os.environ.copy()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        tf_log = str(self.path / f"terraform-init-{timestamp}.log")
        os_env.update({"TF_LOG": "INFO", "TF_LOG_PATH": tf_log})
        if self.env:
            os_env.update(self.env)
        try:
            cmd = [self.terraform, "init"]
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=self.path,
                env=os_env,
            )
            LOG.debug(
                f"Command finished. stdout={process.stdout}, stderr={process.stderr}"
            )
        except subprocess.CalledProcessError as e:
            LOG.error(f"terraform init failed: {e.output}")
            raise TerraformException(str(e))

    def apply(self):
        """terraform apply"""
        os_env = os.environ.copy()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        tf_log = str(self.path / f"terraform-apply-{timestamp}.log")
        os_env.update({"TF_LOG": "INFO", "TF_LOG_PATH": tf_log})
        if self.env:
            os_env.update(self.env)
        try:
            cmd = [self.terraform, "apply", "-auto-approve"]
            if self.parallelism is not None:
                cmd.append(f"-parallelism={self.parallelism}")
            LOG.debug(f'Running command {" ".join(cmd)}')
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=self.path,
                env=os_env,
            )
            LOG.debug(
                f"Command finished. stdout={process.stdout}, stderr={process.stderr}"
            )
        except subprocess.CalledProcessError as e:
            LOG.error(f"terraform apply failed: {e.output}")
            raise TerraformException(str(e))


class TerraformInitStep(BaseStep):
    """Initialize Terraform with required providers."""

    def __init__(self, tfhelper: TerraformHelper):
        super().__init__(
            "Initialize Terraform", "Initializing Terraform from provider mirror"
        )
        self.tfhelper = tfhelper

    def is_skip(self, status: Optional[Status] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def run(self, status: Optional[Status] = None) -> Result:
        """Initialise Terraform configuration from provider mirror,"""
        try:
            self.tfhelper.init()
            return Result(ResultType.COMPLETED)
        except TerraformException as e:
            return Result(ResultType.FAILED, str(e))


class TerraformApplyStep(BaseStep):
    """Apply Terraform configuration using installed providers."""

    def __init__(self, tfhelper: TerraformHelper):
        super().__init__("Apply Terraform", "Apply Terraform from provider mirror")
        self.tfhelper = tfhelper

    def is_skip(self, status: Optional[Status] = None):
        """Determines if the step should be skipped or not.

        :return: True if the Step should be skipped, False otherwise
        """
        return False

    def run(self, status: Optional[Status] = None) -> Result:
        """Initialise Terraform configuration from provider mirror,"""
        try:
            self.tfhelper.apply()
            return Result(ResultType.COMPLETED)
        except TerraformException as e:
            return Result(ResultType.FAILED, str(e))
