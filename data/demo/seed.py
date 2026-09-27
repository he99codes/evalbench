"""Seed the EvalBench demo data.

Inserts one demo project, the default 8-criterion rubric and the refund example
evaluation (data/demo/refund_example.json).

Usage (inside the backend container, where /data is mounted):
    docker compose exec backend python /data/demo/seed.py            # idempotent
    docker compose exec backend python /data/demo/seed.py --reset    # drop + recreate demo project
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEMO_FILE = Path(__file__).with_name("refund_example.json")

# Make the backend package importable whether run from the container (/app)
# or from the repo root on the host (backend/).
for candidate in (Path("/app"), Path(__file__).resolve().parents[2] / "backend"):
    if (candidate / "app").is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import Criterion, Evaluation, EvaluationCriterion, Project  # noqa: E402


def load_demo() -> dict:
    return json.loads(DEMO_FILE.read_text(encoding="utf-8"))


def seed_demo(db: Session, *, reset: bool = False) -> Project:
    """Create the demo project, criteria and evaluation. Returns the project.

    Idempotent: if the demo project already exists it is returned unchanged,
    unless reset=True, in which case it is deleted (cascade) and recreated.
    """
    demo = load_demo()
    existing = db.scalar(select(Project).where(Project.name == demo["project"]["name"]))
    if existing is not None:
        if not reset:
            return existing
        db.delete(existing)
        db.flush()

    project = Project(**demo["project"])
    db.add(project)
    db.flush()

    criteria = [
        Criterion(project_id=project.id, scale_min=1, scale_max=5, enabled=True, **spec)
        for spec in demo["criteria"]
    ]
    db.add_all(criteria)
    db.flush()

    evaluation = Evaluation(project_id=project.id, **demo["evaluation"])
    db.add(evaluation)
    db.flush()

    # The demo evaluation uses every criterion, with per-evaluation weight overrides.
    overrides = demo.get("evaluation_weight_overrides", {})
    db.add_all(
        EvaluationCriterion(
            evaluation_id=evaluation.id, criterion_id=c.id, weight=overrides.get(c.name, c.weight)
        )
        for c in criteria
    )
    db.commit()
    return project


def run_demo_pipeline(db: Session, evaluation: Evaluation) -> None:
    """Populate the demo evaluation by running the real pipeline with MockLLMProvider.

    Results, evidence and the run row are produced by the pipeline itself (nothing is
    hand-written), and the mock is always used here regardless of LLM_PROVIDER.
    """
    from app.core.database import SessionLocal
    from app.providers.mock_provider import MockLLMProvider
    from app.services import evaluation_service

    provider = MockLLMProvider()
    run = evaluation_service.start_run(db, evaluation.id, provider=provider)
    evaluation_service.execute_run(run.id, provider, session_factory=SessionLocal)
    db.refresh(evaluation)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete and recreate the demo project")
    parser.add_argument(
        "--no-run", action="store_true", help="leave the demo evaluation as DRAFT (skip the mock pipeline)"
    )
    args = parser.parse_args()

    from app.core.database import SessionLocal
    from app.models import EvaluationStatus

    with SessionLocal() as db:
        project = seed_demo(db, reset=args.reset)
        evaluation = project.evaluations[0]
        if not args.no_run and evaluation.status == EvaluationStatus.DRAFT:
            run_demo_pipeline(db, evaluation)
        print(f"Demo project:    {project.name} ({project.id})")
        print(f"Criteria:        {len(project.criteria)}")
        print(f"Demo evaluation: {evaluation.title} ({evaluation.id}) status={evaluation.status}")
        if evaluation.overall_score_a is not None:
            print(
                f"Scores:          A={evaluation.overall_score_a}%  B={evaluation.overall_score_b}%  "
                f"preferred={evaluation.preferred_response}"
            )


if __name__ == "__main__":
    main()
