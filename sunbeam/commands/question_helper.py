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
from typing import Any, Callable

import pwgen
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from snaphelpers import Snap

LOG = logging.getLogger(__name__)


class Question:
    """A Question to be resolved."""

    def __init__(
        self,
        question: str,
        default_function: Callable = None,
        default_value: Any = None,
        choices: list = None,
    ):
        """Setup question.

        :param question: The string to display to the user
        :param default_function: A function to use to generate a default value,
                                 for example a password generating function.
        :param default_value: A value to use as the default for the question
        :param choices: A list of choices for the user to choose from
        :param console: the console to prompt on
        """
        self.preseed = None
        self.console = None
        self.previous_answer = None
        self.answer = None
        self.question = question
        self.default_function = default_function
        self.default_value = default_value
        self.choices = choices
        self.accept_defaults = False

    @property
    def question_function(self):
        raise NotImplementedError

    def calculate_default(self, new_default: Any = None) -> Any:
        """Find the value to should be presented to the user as the default.

        This is order of preference:
           1) The users previous answer
           2) A default supplied when the question was asked
           3) The result of the default_function
           4) The default_value for the question.

        :param new_default: The new default for the question.
        """
        default = None
        if self.previous_answer:
            default = self.previous_answer
        elif new_default:
            default = new_default
        elif self.default_function:
            default = self.default_function()
            LOG.debug("Value from default function {}".format(default))
        elif self.default_value:
            default = self.default_value
        return default

    def ask(self, new_default=None) -> Any:
        """Ask a question if needed.

        If a preseed has been supplied for this question then do not ask the
        user.

        :param new_default: The new default for the question. The idea here is
                            that previous answers may impact the value of a
                            sensible default so the original default can be
                            overriden at the point of prompting the user.
        """
        if self.preseed:
            self.answer = self.preseed
        else:
            default = self.calculate_default(new_default=new_default)
            if self.accept_defaults:
                self.answer = default
            else:
                self.answer = self.question_function(
                    self.question,
                    default=default,
                    console=self.console,
                    choices=self.choices,
                )
        return self.answer


class PromptQuestion(Question):
    """Ask the user a question."""

    @property
    def question_function(self):
        return Prompt.ask


class ConfirmQuestion(Question):
    """Ask the user a simple yes / no question."""

    @property
    def question_function(self):
        return Confirm.ask


class QuestionBank:
    """A bank of questions.


    For example:

        class UserQuestions(QuestionBank):

            questions = {
                "username": PromptQuestion(
                    "Username to use for access to OpenStack",
                    default_value="demo"
                ),
                "password": PromptQuestion(
                    "Password to use for access to OpenStack",
                    default_function=generate_password,
                ),
                "cidr": PromptQuestion(
                    "Network range to use for project network",
                    default_value="192.168.122.0/24"
                ),
                "security_group_rules": ConfirmQuestion(
                    "Setup security group rules for SSH and ICMP ingress",
                    default_value=True
                ),
            }

        user_questions = UserQuestions(
            console=console,
            preseed=preseed.get("user"),
            previous_answers=self.variables.get("user"),
        )
        username = user_questions.username.ask()
        password = user_questions.password.ask()
    """

    def __init__(
        self,
        questions: dict,
        console: Console,
        preseed: dict = None,
        previous_answers: dict = None,
        accept_defaults: bool = False,
    ):
        """Apply preseed and previous answers to questions in bank.

        :param questions: dictionary of questions
        :param console: the console to prompt on
        :param preseed: dict of answers to questions.
        :param previous_answers: Previous answers to the questions in the
                                 bank.
        """
        self.questions = questions
        self.preseed = preseed or {}
        self.previous_answers = previous_answers or {}
        for key in self.questions.keys():
            self.questions[key].console = console
            self.questions[key].accept_defaults = accept_defaults
        for key, value in self.preseed.items():
            if self.questions.get(key) is not None:
                self.questions[key].preseed = value
        for key, value in self.previous_answers.items():
            if self.previous_answers.get(key) is not None:
                if self.questions.get(key) is not None:
                    self.questions[key].previous_answer = value

    def __getattr__(self, attr):
        return self.questions[attr]


def read_preseed(preseed_file: str) -> dict:
    """Read the preseed file."""
    with open(preseed_file, "r") as f:
        preseed_data = yaml.safe_load(f)
    return preseed_data


def generate_password() -> str:
    """Generate a password."""
    return pwgen.pwgen(12)


def answer_file() -> str:
    """Location of answer file."""
    terraform_tfvars = (
        Snap().paths.user_common / "etc" / "configure" / "terraform.tfvars.json"
    )
    return terraform_tfvars


def load_answers(file_name: str = None) -> dict:
    """Read answers from answer file."""
    terraform_tfvars = file_name or answer_file()
    variables = {}
    if terraform_tfvars.exists():
        with open(terraform_tfvars, "r") as tfvars:
            variables = json.loads(tfvars.read())
    return variables


def write_answers(answers, file_name: str = None):
    """Write answers to answer file."""
    terraform_tfvars = file_name or answer_file()
    with open(terraform_tfvars, "w") as tfvars:
        os.fchmod(tfvars.fileno(), mode=0o640)
        tfvars.write(json.dumps(answers))
