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
import pathlib
import subprocess
from unittest.mock import ANY, MagicMock

import pytest

import sunbeam.commands.terraform as terraform
from sunbeam.jobs.common import ResultType


class TestTerraform:
    """Unit tests for sunbeam terraform helper."""

    def test_terraform_helper_init(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(path=pathlib.Path("/foo/bar"))

        tfhelper.init()

        run.assert_called_once_with(
            [
                f"{snap.paths.snap}/bin/terraform",
                "init",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=tfhelper.path,
            env={"TF_LOG": "INFO", "TF_LOG_PATH": ANY},
        )

    def test_terraform_helper_init_with_env(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(
            path=pathlib.Path("/foo/bar"),
            env={"foo": "bar"},
        )

        tfhelper.init()

        run.assert_called_once_with(
            [
                f"{snap.paths.snap}/bin/terraform",
                "init",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=tfhelper.path,
            env={"TF_LOG": "INFO", "TF_LOG_PATH": ANY, "foo": "bar"},
        )

    def test_terraform_helper_init_with_exception(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(path=pathlib.Path("/foo/bar"))

        run.side_effect = subprocess.CalledProcessError(returncode=1, cmd="foobar")

        with pytest.raises(terraform.TerraformException):
            tfhelper.init()

    def test_terraform_helper_apply(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(path=pathlib.Path("/foo/bar"))

        tfhelper.apply()

        run.assert_called_once_with(
            [f"{snap.paths.snap}/bin/terraform", "apply", "-auto-approve"],
            capture_output=True,
            text=True,
            check=True,
            cwd=tfhelper.path,
            env={"TF_LOG": "INFO", "TF_LOG_PATH": ANY},
        )

    def test_terraform_helper_apply_with_env(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(
            path=pathlib.Path("/foo/bar"),
            env={"foo": "bar"},
        )

        tfhelper.apply()

        run.assert_called_once_with(
            [f"{snap.paths.snap}/bin/terraform", "apply", "-auto-approve"],
            capture_output=True,
            text=True,
            check=True,
            cwd=tfhelper.path,
            env={"TF_LOG": "INFO", "TF_LOG_PATH": ANY, "foo": "bar"},
        )

    def test_terraform_helper_apply_with_parallelism(self, mocker, run, snap, environ):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        environ.copy.return_value = {}
        tfhelper = terraform.TerraformHelper(
            path=pathlib.Path("/foo/bar"), parallelism=1
        )

        tfhelper.apply()

        run.assert_called_once_with(
            [
                f"{snap.paths.snap}/bin/terraform",
                "apply",
                "-auto-approve",
                "-parallelism=1",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=tfhelper.path,
            env=ANY,
        )

    def test_terraform_helper_apply_with_exception(self, mocker, run, snap):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        tfhelper = terraform.TerraformHelper(path=pathlib.Path("/foo/bar"))

        run.side_effect = subprocess.CalledProcessError(returncode=1, cmd="foobar")

        with pytest.raises(terraform.TerraformException):
            tfhelper.apply()

    def test_terraform_write_tfvars(self, mocker, snap):
        mocker.patch.object(terraform, "Snap", return_value=snap)
        mock_file = mocker.patch("builtins.open", mocker.mock_open())
        tfhelper = terraform.TerraformHelper(path=pathlib.Path("/foo/bar"))

        tfhelper.write_tfvars({"foo": "bar"})

        mock_file.assert_called_once_with(
            pathlib.Path("/foo/bar/terraform.tfvars.json"), "w"
        )
        mock_file_handle = mock_file()
        mock_file_handle.write.assert_called_once_with(json.dumps({"foo": "bar"}))


class TestTerraformSteps:
    """Unit tests for sunbeam terraform steps."""

    def test_init_step(self):
        tfhelper = MagicMock()
        init_step = terraform.TerraformInitStep(tfhelper)
        result = init_step.run()
        assert result.result_type == ResultType.COMPLETED
        tfhelper.init.assert_called_once_with()

    def test_init_step_with_error(self):
        tfhelper = MagicMock()
        init_step = terraform.TerraformInitStep(tfhelper)
        tfhelper.init.side_effect = terraform.TerraformException("init failed")
        result = init_step.run()
        assert result.result_type == ResultType.FAILED
        tfhelper.init.assert_called_once_with()

    def test_apply_step(self):
        tfhelper = MagicMock()
        apply_step = terraform.TerraformApplyStep(tfhelper)
        result = apply_step.run()
        assert result.result_type == ResultType.COMPLETED
        tfhelper.apply.assert_called_once_with()

    def test_apply_step_with_error(self):
        tfhelper = MagicMock()
        apply_step = terraform.TerraformApplyStep(tfhelper)
        tfhelper.apply.side_effect = terraform.TerraformException("apply failed")
        result = apply_step.run()
        assert result.result_type == ResultType.FAILED
        tfhelper.apply.assert_called_once_with()
