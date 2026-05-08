"""merge heads system_prompt_overrides and allowed_tools

Revision ID: 061b4ffa97bb
Revises: c969b5f63428, 73d6e838c5aa
Create Date: 2026-05-08 18:00:00.000000

Empty merge migration combining the two independent feature heads
introduced on the fork:

- ``c969b5f63428``: ``add system prompt overrides to agent_custom_provider``
  (``feat/ai-action-system-prompt-overrides``)
- ``73d6e838c5aa``: ``add allowed_tools to agent_custom_provider``
  (``feat/ai-action-allowed-tools-control``)

Both descend from the same upstream parent ``d0b32dce7f81`` so Alembic
sees two heads. This migration is a no-op DDL-wise; it only joins the
two branches so ``alembic upgrade head`` can resolve a single head on
``deploy/mytracecat``.

Lives only on the integration branch — feature branches keep their own
single head so each can be re-proposed upstream independently.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "061b4ffa97bb"
down_revision: tuple[str, str] | str | None = ("c969b5f63428", "73d6e838c5aa")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No DDL — both parent migrations have already applied their
    column additions."""


def downgrade() -> None:
    """No-op — splitting back into two heads is handled by reverting
    each parent migration individually."""
