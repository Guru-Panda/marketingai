"""
Run this once to insert sample leads for the first user in the database.
Usage:  python -m backend.seed_demo
"""
import uuid
from backend.database import SessionLocal
from backend.model import Lead, User

_DEMO_LEADS = [
    {
        "source_platform": "reddit",
        "content": (
            "Hey everyone, our startup is scaling fast and we desperately need a reliable "
            "B2B SaaS CRM tool. Currently using spreadsheets but it's getting out of hand "
            "with 50+ leads. Budget is around $200/month. Any recommendations? "
            "We're a 15-person team in fintech."
        ),
        "content_summary": (
            "Fintech startup (15 people) actively seeking a B2B SaaS CRM to replace "
            "spreadsheets. Budget $200/mo, 50+ leads. High purchase intent."
        ),
        "intent_score": 0.92,
        "keywords": ["CRM", "B2B SaaS", "fintech startup", "lead management", "scaling"],
        "source_url": "https://www.reddit.com/r/startups/comments/demo_arjun",
        "author_name": "Arjun Mehta",
        "author_username": "arjun_builds",
        "author_url": "https://www.reddit.com/user/arjun_builds",
        "author_location": "Bangalore, India",
    },
    {
        "source_platform": "linkedin",
        "content": (
            "We're a Series A startup looking for outbound sales automation tools. "
            "Our SDR team is manually prospecting 200+ accounts a week and we need "
            "something that integrates with HubSpot. Would love recommendations from "
            "founders who've solved this. Email me at priya@techstartup.in"
        ),
        "content_summary": (
            "Series A startup SDR team needs outbound sales automation integrating "
            "with HubSpot. Actively evaluating tools. Contact provided."
        ),
        "intent_score": 0.87,
        "keywords": ["outbound sales", "sales automation", "HubSpot integration", "SDR"],
        "source_url": "https://www.linkedin.com/posts/priya-sharma-demo",
        "author_name": "Priya Sharma",
        "author_username": "priya-sharma-founder",
        "author_url": "https://www.linkedin.com/in/priya-sharma-founder",
        "author_email": "priya@techstartup.in",
        "author_location": "Mumbai, India",
    },
    {
        "source_platform": "reddit",
        "content": (
            "Looking for a marketing automation tool for our e-commerce brand. "
            "We have ~10k email subscribers and need abandoned cart flows, post-purchase "
            "sequences, and SMS. Klaviyo feels too expensive at our stage — "
            "open to alternatives. DM or reach out at rohan@mystore.com, +91-98765-43210"
        ),
        "content_summary": (
            "E-commerce founder seeking affordable marketing automation with email + SMS. "
            "Shared email and phone number. Comparing against Klaviyo."
        ),
        "intent_score": 0.85,
        "keywords": ["marketing automation", "email marketing", "SMS", "e-commerce", "Klaviyo"],
        "source_url": "https://www.reddit.com/r/ecommerce/comments/demo_rohan",
        "author_name": "Rohan Das",
        "author_username": "rohan_ecom",
        "author_url": "https://www.reddit.com/user/rohan_ecom",
        "author_email": "rohan@mystore.com",
        "author_phone": "+91-98765-43210",
        "author_location": "Delhi, India",
    },
    {
        "source_platform": "discord",
        "content": (
            "Anyone using AI tools for lead generation in the SaaS space? "
            "We're trying to identify companies that are actively hiring sales roles — "
            "usually a signal they need better tooling. Looking for something that can "
            "monitor job boards and social media automatically and score intent."
        ),
        "content_summary": (
            "SaaS founder looking for AI-powered lead gen that monitors job boards "
            "and social for buying signals. High fit for this product."
        ),
        "intent_score": 0.78,
        "keywords": ["AI lead generation", "SaaS", "job board monitoring", "buying signals"],
        "source_url": None,
        "author_name": "Sneha Iyer",
        "author_username": "sneha_saas",
        "author_location": "Hyderabad, India",
    },
]


def seed(user_id: int | None = None) -> int:
    db = SessionLocal()
    try:
        if user_id is None:
            first_user = db.query(User).order_by(User.id).first()
            if not first_user:
                print("No users found in the database. Sign up first.")
                return 0
            user_id = first_user.id
            print(f"Seeding leads for user id={user_id} ({first_user.email})")

        created = 0
        for demo in _DEMO_LEADS:
            external_id = f"demo-{uuid.uuid4().hex[:10]}"
            exists = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.source_platform == demo["source_platform"],
                Lead.content_summary == demo["content_summary"],
            ).first()
            if exists:
                continue
            lead = Lead(user_id=user_id, external_id=external_id, **demo)
            db.add(lead)
            created += 1

        db.commit()
        print(f"Inserted {created} demo lead(s).")
        return created
    finally:
        db.close()


if __name__ == "__main__":
    seed()
