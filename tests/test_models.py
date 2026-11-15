from datetime import date
import unittest

from pydantic import ValidationError

from app.models import Draft, MatchResult, Posting, Profile


class TestModels(unittest.TestCase):
    def test_profile_defaults_optional_lists_and_notes(self) -> None:
        profile = Profile(
            role="Software Engineering Intern",
            location="Finland",
            work_authorization="Eligible to work in Finland",
        )

        self.assertEqual(profile.skills, [])
        self.assertEqual(profile.languages, [])
        self.assertEqual(profile.extra_notes, "")

    def test_posting_preserves_source_and_optional_deadline(self) -> None:
        posting = Posting(
            company="Example Oy",
            title="Software Engineering Intern",
            source_url="https://example.com/jobs/intern",
        )

        self.assertEqual(str(posting.source_url), "https://example.com/jobs/intern")
        self.assertIsNone(posting.deadline)
        self.assertEqual(posting.requirements, [])

    def test_match_result_rejects_scores_outside_range(self) -> None:
        posting = Posting(
            company="Example Oy",
            title="Software Engineering Intern",
            source_url="https://example.com/jobs/intern",
        )

        with self.assertRaises(ValidationError):
            MatchResult(posting=posting, score=101)

    def test_draft_serializes_dates_and_source_urls(self) -> None:
        posting = Posting(
            company="Example Oy",
            title="Software Engineering Intern",
            deadline=date(2027, 6, 1),
            source_url="https://example.com/jobs/intern",
        )
        draft = Draft(
            posting_id="example-intern",
            text="I am excited to apply.",
            sources_used=[posting.source_url],
        )

        self.assertEqual(
            draft.model_dump(mode="json")["sources_used"],
            ["https://example.com/jobs/intern"],
        )
