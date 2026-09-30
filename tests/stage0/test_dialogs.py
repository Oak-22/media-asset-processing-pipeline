"""Tests for the Stage 0 questionnaire with a scripted dialog backend."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from scripts.python.stage0.classify import CategoryCandidate
from scripts.python.stage0.config import DEFAULT_CONFIG_PATH, load_config
from scripts.python.stage0.dialogs import OsascriptDialogs, Questionnaire, ShootPrompt
from scripts.python.stage0.taxonomy import TaxonomyReader


CONFIG = load_config(DEFAULT_CONFIG_PATH)
OPTIONS = CONFIG.dialogs.options


class ScriptedDialogs:
    """Answers questions from a queue and records every prompt it saw."""

    def __init__(self, answers: Sequence[str | bool | None]) -> None:
        self.answers = list(answers)
        self.prompts: list[tuple[str, tuple[str, ...], str | None]] = []

    def _next(self) -> str | bool | None:
        if not self.answers:
            raise AssertionError(f"unexpected extra question: {self.prompts[-1]}")
        return self.answers.pop(0)

    def choose(self, prompt: str, choices: Sequence[str], default: str | None = None) -> str | None:
        self.prompts.append((prompt, tuple(choices), default))
        answer = self._next()
        assert answer is None or answer in choices, (answer, choices)
        return answer  # type: ignore[return-value]

    def text(self, prompt: str, default: str = "") -> str | None:
        self.prompts.append((prompt, (), default))
        answer = self._next()
        return default if answer == "<default>" else answer  # type: ignore[return-value]

    def confirm(self, prompt: str, accept: str, decline: str) -> bool:
        self.prompts.append((prompt, (accept, decline), None))
        return bool(self._next())

    def notify(self, message: str) -> None:
        pass


def prompt(**overrides: object) -> ShootPrompt:
    values: dict[str, object] = {
        "shoot_id": "2026-05-10_0900",
        "file_count": 412,
        "time_range": "Sun 10 May 2026, 09:00–12:00",
        "year": 2026,
        "candidates": (
            CategoryCandidate("People", 0.9, 0.7, ("people",)),
            CategoryCandidate("Landscape", 0.4, 0.3, ("mountain",)),
        ),
        "auto_accepted_category": None,
        "location_suggestion": "Sonoma, CA",
    }
    values.update(overrides)
    return ShootPrompt(**values)  # type: ignore[arg-type]


class QuestionnaireTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for relpath in (
            "People/Personal/Family",
            "People/Client Work — SSD/Commercial/Brand Photography/DJ Alx/Mangos 2026/Photo/RAW",
            "Landscape/Lake Tahoe – Eastons Family/Photo/RAW",
        ):
            (self.root / relpath).mkdir(parents=True)
        self.folders = TaxonomyReader(self.root, frozenset({"_Inbox"}))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_people_branch_new_shoot_with_gps_prefill(self) -> None:
        dialogs = ScriptedDialogs(
            [
                "People",
                "Personal",
                "Family",
                OPTIONS["file_here"],
                OPTIONS["new_shoot"],
                "Brandy",
                "Modeling",
                "<default>",
                "<default>",
            ]
        )
        decision = Questionnaire(dialogs, self.folders, CONFIG).run(prompt())
        assert decision is not None
        self.assertEqual(
            decision.relpath,
            PurePosixPath("People/Personal/Family/Brandy – Modeling – Sonoma, CA"),
        )
        self.assertFalse(decision.merge_into_existing)
        self.assertEqual(decision.answers["location_source"], "gps_prefill_confirmed")
        people_branch_choices = dialogs.prompts[1][1]
        self.assertNotIn(OPTIONS["file_here"], people_branch_choices)
        self.assertEqual(people_branch_choices[:2], ("Client Work — SSD", "Personal"))

    def test_existing_client_gets_session_year_folder(self) -> None:
        dialogs = ScriptedDialogs(
            [
                "People",
                "Client Work — SSD",
                "Commercial",
                "Brand Photography",
                OPTIONS["file_here"],
                f"{OPTIONS['existing_prefix']}DJ Alx",
                "Summer Launch",
                "<default>",
            ]
        )
        decision = Questionnaire(dialogs, self.folders, CONFIG).run(prompt())
        assert decision is not None
        self.assertEqual(
            decision.relpath.parts[-2:], ("DJ Alx", "Summer Launch 2026")
        )
        self.assertEqual(decision.answers["client"], "DJ Alx")

    def test_existing_shoot_folder_merges_only_after_confirmation(self) -> None:
        answers = [
            "Landscape",
            OPTIONS["file_here"],
            f"{OPTIONS['existing_prefix']}Lake Tahoe – Eastons Family",
            "<default>",
        ]
        accepted = Questionnaire(ScriptedDialogs([*answers, True]), self.folders, CONFIG).run(prompt())
        assert accepted is not None
        self.assertTrue(accepted.merge_into_existing)
        declined = Questionnaire(ScriptedDialogs([*answers, False]), self.folders, CONFIG).run(prompt())
        self.assertIsNone(declined)

    def test_auto_accepted_category_skips_category_question(self) -> None:
        dialogs = ScriptedDialogs(
            [OPTIONS["file_here"], OPTIONS["new_shoot"], "Mt Tam", "", "", "<default>"]
        )
        decision = Questionnaire(dialogs, self.folders, CONFIG).run(
            prompt(auto_accepted_category="Landscape", location_suggestion=None)
        )
        assert decision is not None
        self.assertEqual(decision.relpath, PurePosixPath("Landscape/Mt Tam"))
        self.assertNotIn("category", decision.answers)

    def test_cancel_at_any_point_returns_none(self) -> None:
        self.assertIsNone(Questionnaire(ScriptedDialogs([None]), self.folders, CONFIG).run(prompt()))
        dialogs = ScriptedDialogs(["People", "Personal", "Family", OPTIONS["file_here"], OPTIONS["new_shoot"], None])
        self.assertIsNone(Questionnaire(dialogs, self.folders, CONFIG).run(prompt()))

    def test_blank_subject_routes_to_inbox(self) -> None:
        dialogs = ScriptedDialogs(
            ["Landscape", OPTIONS["file_here"], OPTIONS["new_shoot"], "  ", "", ""]
        )
        self.assertIsNone(Questionnaire(dialogs, self.folders, CONFIG).run(prompt()))


class OsascriptDialogsTest(unittest.TestCase):
    def fake_runner(self, stdout: str, returncode: int = 0):
        calls: list[list[str]] = []

        def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(command)
            return subprocess.CompletedProcess(command, returncode, stdout.encode(), b"")

        return run, calls

    def test_values_are_passed_as_argv_not_interpolated(self) -> None:
        run, calls = self.fake_runner("OK:Say \"hi\"\n")
        dialogs = OsascriptDialogs("SD Offload", 60, runner=run)
        self.assertEqual(dialogs.text('Name with "quotes"?', default="x"), 'Say "hi"')
        self.assertEqual(calls[0][3:], ['Name with "quotes"?', "SD Offload", "x", "60"])

    def test_cancel_and_errors_return_none(self) -> None:
        run, _calls = self.fake_runner("__CANCELLED__\n")
        self.assertIsNone(OsascriptDialogs("t", 60, runner=run).choose("p", ["a", "b"]))
        run, _calls = self.fake_runner("", returncode=1)
        self.assertIsNone(OsascriptDialogs("t", 60, runner=run).text("p"))

    def test_empty_text_answer_is_not_a_cancel(self) -> None:
        run, _calls = self.fake_runner("OK:\n")
        self.assertEqual(OsascriptDialogs("t", 60, runner=run).text("p"), "")


if __name__ == "__main__":
    unittest.main()
