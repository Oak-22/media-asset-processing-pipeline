"""macOS dialog wrappers and the Stage 0 filing questionnaire.

Values are passed to AppleScript through `on run argv`, so prompt text
and folder names never need AppleScript string escaping.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

from scripts.python.stage0.classify import CategoryCandidate
from scripts.python.stage0.config import OffloadConfig
from scripts.python.stage0.taxonomy import (
    FolderListing,
    parse_relpath,
    repeat_client_relpath,
    sanitize_component,
    session_folder_name,
    shoot_folder_name,
)


CANCELLED_MARKER = "__CANCELLED__"
ANSWER_PREFIX = "OK:"

CHOOSE_SCRIPT = """
on run argv
  set promptText to item 1 of argv
  set titleText to item 2 of argv
  set defaultItem to item 3 of argv
  set choices to items 4 thru -1 of argv
  set picked to choose from list choices with title titleText with prompt promptText default items {defaultItem}
  if picked is false then return "__CANCELLED__"
  return "OK:" & (item 1 of picked)
end run
"""

TEXT_SCRIPT = """
on run argv
  set promptText to item 1 of argv
  set titleText to item 2 of argv
  set defaultAnswer to item 3 of argv
  set waitSeconds to (item 4 of argv) as integer
  try
    set reply to display dialog promptText with title titleText default answer defaultAnswer buttons {"Cancel", "OK"} default button "OK" cancel button "Cancel" giving up after waitSeconds
  on error number -128
    return "__CANCELLED__"
  end try
  if gave up of reply then return "__CANCELLED__"
  return "OK:" & (text returned of reply)
end run
"""

CONFIRM_SCRIPT = """
on run argv
  set promptText to item 1 of argv
  set titleText to item 2 of argv
  set acceptLabel to item 3 of argv
  set declineLabel to item 4 of argv
  set waitSeconds to (item 5 of argv) as integer
  set reply to display dialog promptText with title titleText buttons {declineLabel, acceptLabel} default button acceptLabel giving up after waitSeconds
  if gave up of reply then return "__CANCELLED__"
  return "OK:" & (button returned of reply)
end run
"""

NOTIFY_SCRIPT = """
on run argv
  display notification (item 1 of argv) with title (item 2 of argv)
end run
"""

Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class DialogBackend(Protocol):
    """Operator interaction surface; tests inject scripted fakes."""

    def choose(self, prompt: str, choices: Sequence[str], default: str | None = None) -> str | None: ...

    def text(self, prompt: str, default: str = "") -> str | None: ...

    def confirm(self, prompt: str, accept: str, decline: str) -> bool: ...

    def notify(self, message: str) -> None: ...


class FolderSource(Protocol):
    """Read-only taxonomy view (see taxonomy.TaxonomyReader)."""

    def listing(self, relpath: PurePosixPath) -> FolderListing: ...

    def exists(self, relpath: PurePosixPath) -> bool: ...


class OsascriptDialogs:
    """DialogBackend implemented with `osascript`."""

    def __init__(self, title: str, timeout_seconds: int, runner: Runner = subprocess.run) -> None:
        self.title = title
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def _run(self, script: str, *args: str) -> str:
        completed = self._runner(
            ["osascript", "-e", script, *args],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return CANCELLED_MARKER
        return completed.stdout.decode("utf-8", "replace").rstrip("\n")

    @staticmethod
    def _answer(output: str) -> str | None:
        if not output.startswith(ANSWER_PREFIX):
            return None
        return output[len(ANSWER_PREFIX):]

    def choose(self, prompt: str, choices: Sequence[str], default: str | None = None) -> str | None:
        if not choices:
            return None
        selected = default if default in choices else choices[0]
        return self._answer(self._run(CHOOSE_SCRIPT, prompt, self.title, selected, *choices))

    def text(self, prompt: str, default: str = "") -> str | None:
        return self._answer(
            self._run(TEXT_SCRIPT, prompt, self.title, default, str(self.timeout_seconds))
        )

    def confirm(self, prompt: str, accept: str, decline: str) -> bool:
        output = self._run(
            CONFIRM_SCRIPT, prompt, self.title, accept, decline, str(self.timeout_seconds)
        )
        return self._answer(output) == accept

    def notify(self, message: str) -> None:
        self._run(NOTIFY_SCRIPT, message, self.title)


class SilentDialogs:
    """Backend for --no-dialog runs: every question is declined."""

    def choose(self, prompt: str, choices: Sequence[str], default: str | None = None) -> str | None:
        return None

    def text(self, prompt: str, default: str = "") -> str | None:
        return None

    def confirm(self, prompt: str, accept: str, decline: str) -> bool:
        return False

    def notify(self, message: str) -> None:
        print(f"[notification] {message}", flush=True)


@dataclass(frozen=True)
class ShootPrompt:
    """What the questionnaire shows the operator about one shoot."""

    shoot_id: str
    file_count: int
    time_range: str
    year: int
    candidates: tuple[CategoryCandidate, ...]
    auto_accepted_category: str | None
    location_suggestion: str | None


@dataclass(frozen=True)
class FilingDecision:
    """Where a shoot is filed and which answers the operator gave."""

    relpath: PurePosixPath
    filing: str
    merge_into_existing: bool
    answers: dict[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, object]:
        return {
            "filing": self.filing,
            "destination_relpath": str(self.relpath),
            "merge_into_existing": self.merge_into_existing,
            "answers": dict(self.answers),
        }


class QuestionnaireCancelled(Exception):
    """Raised internally when the operator cancels or gives an unusable answer."""


def _require(value: str | None) -> str:
    if value is None:
        raise QuestionnaireCancelled
    return value


class Questionnaire:
    """Ask only the filing questions that cannot be inferred."""

    def __init__(self, dialogs: DialogBackend, folders: FolderSource, config: OffloadConfig) -> None:
        self.dialogs = dialogs
        self.folders = folders
        self.config = config
        self.questions = config.dialogs.questions
        self.options = config.dialogs.options

    def run(self, shoot: ShootPrompt) -> FilingDecision | None:
        """Return the operator-confirmed filing, or None when cancelled."""
        try:
            return self._run(shoot)
        except (QuestionnaireCancelled, ValueError):
            return None

    def _ask(self, key: str, shoot: ShootPrompt, **values: object) -> str:
        return self.questions[key].format(
            shoot_id=shoot.shoot_id,
            file_count=shoot.file_count,
            time_range=shoot.time_range,
            year=shoot.year,
            photo_root=self.config.photo_root,
            **values,
        )

    def _display(self, relpath: PurePosixPath) -> str:
        return str(PurePosixPath(self.config.photo_root) / relpath)

    def _new_folder(self, shoot: ShootPrompt, parent: PurePosixPath) -> str:
        name = _require(self.dialogs.text(self._ask("new_folder", shoot, path=self._display(parent))))
        return sanitize_component(name)

    def _category(self, shoot: ShootPrompt, answers: dict[str, str]) -> str:
        if shoot.auto_accepted_category:
            return shoot.auto_accepted_category
        suggested = [candidate.category for candidate in shoot.candidates[:3]]
        if suggested:
            pick = _require(
                self.dialogs.choose(
                    self._ask("category", shoot),
                    [*suggested, self.options["other_category"]],
                    default=suggested[0],
                )
            )
            if pick != self.options["other_category"]:
                answers["category"] = pick
                return pick
        existing = set(self.folders.listing(PurePosixPath()).subfolders)
        existing.update(self.config.classification.label_map)
        choices = [*sorted(existing), self.options["new_folder"]]
        pick = _require(self.dialogs.choose(self._ask("category_all", shoot), choices))
        if pick == self.options["new_folder"]:
            pick = self._new_folder(shoot, PurePosixPath())
        answers["category"] = pick
        return pick

    def _drill_down(self, shoot: ShootPrompt, category: str) -> PurePosixPath:
        path = PurePosixPath(category)
        people = self.config.classification.people_category
        for depth in range(self.config.max_depth):
            listing = self.folders.listing(path)
            branch_required = depth == 0 and category == people
            choices = [
                *([] if branch_required else [self.options["file_here"]]),
                *listing.subfolders,
                self.options["new_folder"],
            ]
            prompt_key = "people_branch" if branch_required else "subcategory"
            pick = _require(
                self.dialogs.choose(self._ask(prompt_key, shoot, path=self._display(path)), choices, choices[0])
            )
            if pick == self.options["file_here"]:
                break
            if pick == self.options["new_folder"]:
                pick = self._new_folder(shoot, path)
            path = path / pick
        return path

    def _shoot_folder(
        self, shoot: ShootPrompt, parent: PurePosixPath, answers: dict[str, str]
    ) -> PurePosixPath:
        listing = self.folders.listing(parent)
        prefix = self.options["existing_prefix"]
        existing = [*listing.subfolders, *listing.shoot_folders]
        choices = [
            self.options["new_shoot"],
            self.options["new_client_session"],
            *(f"{prefix}{name}" for name in existing),
        ]
        pick = _require(
            self.dialogs.choose(self._ask("shoot_folder", shoot, path=self._display(parent)), choices, choices[0])
        )
        if pick == self.options["new_shoot"]:
            subject = _require(self.dialogs.text(self._ask("subject", shoot)))
            descriptor = _require(self.dialogs.text(self._ask("descriptor", shoot)))
            suggestion = shoot.location_suggestion or ""
            location = _require(self.dialogs.text(self._ask("location", shoot), default=suggestion))
            answers["subject"] = subject.strip()
            if descriptor.strip():
                answers["descriptor"] = descriptor.strip()
            if location.strip():
                answers["location"] = location.strip()
                answers["location_source"] = (
                    "gps_prefill_confirmed"
                    if suggestion and location.strip() == suggestion
                    else "operator_entered"
                )
            return parent / shoot_folder_name(subject, descriptor, location)
        if pick == self.options["new_client_session"]:
            client = _require(self.dialogs.text(self._ask("client", shoot)))
            session = _require(self.dialogs.text(self._ask("session", shoot)))
            answers["client"] = client.strip()
            answers["session"] = session.strip()
            return parent / repeat_client_relpath(client, session, shoot.year)
        name = pick.removeprefix(prefix)
        if name in listing.shoot_folders:
            answers["existing_shoot_folder"] = name
            return parent / name
        session = _require(self.dialogs.text(self._ask("session", shoot)))
        answers["client"] = name
        answers["session"] = session.strip()
        return parent / name / session_folder_name(session, shoot.year)

    def _run(self, shoot: ShootPrompt) -> FilingDecision:
        answers: dict[str, str] = {}
        category = self._category(shoot, answers)
        folder = self._drill_down(shoot, category)
        answers["folder_path"] = str(folder)
        proposed = self._shoot_folder(shoot, folder, answers)
        edited = _require(self.dialogs.text(self._ask("confirm", shoot), default=str(proposed)))
        relpath = parse_relpath(edited)
        if relpath.parts[0] == self.config.inbox_folder:
            raise QuestionnaireCancelled
        answers["confirmed_destination"] = str(relpath)
        merge = self.folders.exists(relpath)
        if merge:
            accepted = self.dialogs.confirm(
                self._ask("merge", shoot, path=relpath),
                self.options["merge"],
                self.options["inbox"],
            )
            if not accepted:
                raise QuestionnaireCancelled
            answers["merge_confirmed"] = "yes"
        return FilingDecision(
            relpath=relpath,
            filing="operator_confirmed",
            merge_into_existing=merge,
            answers=answers,
        )
