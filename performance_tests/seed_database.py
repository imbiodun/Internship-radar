from app.models import MatchResult, Posting, Profile
from app.store import Store
import random
import argparse

def seed_database(count: int ) -> int:

    store = Store("performance.db")
    rng= random.Random(42)

    profile = Profile(
        role="Software Engineer",
        location="Finland",
        work_authorization="Eligible",
    )

    

    for i in range(count):
        
        posting_id = f"synthetic_{i}"
        posting = Posting(
            company = f"Company {i}",
            source_url = f"https://example.com/posting_{i}",
            title = f"Software Engineer {i}",
        )


        match_result = MatchResult(
            posting=posting,
            score= rng.randint(50, 100),
        )

        store.save_match(
            posting_id= posting_id,
            profile=profile,
            match=match_result,
        )

    return len(store.list_saved())


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Generate synthetic internship postings"
    )

    parser.add_argument("--count", type=int, required=True)

    args = parser.parse_args()

    if args.count < 0:
        parser.error("Count must be non-negative")

    actual_count = seed_database(args.count)

    print(f"Requested postings: {args.count}")
    print(f"Total saved postings: {actual_count}")

    if actual_count != args.count:
        raise SystemExit("Dataset size mismatch")