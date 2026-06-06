# Aporte Exclude & Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to exclude individual aporte suggestions and instantly rebalance remaining suggestions, with exclusions persisted to the database.

**Architecture:** New `POST /api/aportes/{event_id}/exclude` endpoint marks an allocation as excluded, reloads the portfolio, and re-runs the rebalance algorithm on remaining allocations. Frontend adds an X button per row that triggers instant server-side rebalance. DB gains an `excluded` boolean column on `aporte_allocations`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, SvelteKit 5 (runes), TypeScript, Vitest

---

## File Map

### Backend (create/modify)
| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/aporte_allocation.py` | Modify | Add `excluded` column |
| `backend/alembic/versions/0006_add_excluded_to_allocations.py` | Create | Migration |
| `backend/app/schemas/aporte.py` | Modify | Add `excluded` to output schema, add `ExcludeRequest` input schema |
| `backend/app/services/algorithm.py` | Modify | Add `exclude_ids` param to `compute_suggestions` and all stage functions |
| `backend/app/services/aporte_service.py` | Modify | Add `exclude_allocation` function |
| `backend/app/api/aportes.py` | Modify | Add `POST /{event_id}/exclude` endpoint |
| `backend/tests/services/test_algorithm_exclude.py` | Create | Unit tests for exclude logic in algorithm |
| `backend/tests/api/test_aportes.py` | Modify | Integration tests for exclude endpoint |

### Frontend (create/modify)
| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/lib/types/api.ts` | Modify | Add `excluded` to `AporteAllocationOut` |
| `frontend/src/lib/api/aportes.ts` | Modify | Add `excludeAllocation` function |
| `frontend/src/routes/(app)/aporte/+page.svelte` | Modify | X button, excluded row styling, rebalance display |

---

### Task 1: Add `excluded` column to AporteAllocation model

**Files:**
- Modify: `backend/app/models/aporte_allocation.py:27-28`

- [ ] **Step 1: Add `excluded` boolean column to the model**

In `backend/app/models/aporte_allocation.py`, add after the `applied_quantity` column (line ~33):

```python
    # Exclusion (user chose not to allocate to this asset)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 2: Verify the model imports `Boolean`**

Check line 3 of the file — `Boolean` is already imported in the existing `from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String`. No change needed.

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `cd backend && uv run pytest tests/api/test_aportes.py -v`
Expected: all existing tests PASS (column has default=False, so no migration needed for test DB's `create_all`)

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/models/aporte_allocation.py && git commit -m "feat: add excluded column to AporteAllocation model"
```

---

### Task 2: Alembic migration for `excluded` column

**Files:**
- Create: `backend/alembic/versions/0006_add_excluded_to_allocations.py`

- [ ] **Step 1: Create migration file**

```python
"""add excluded flag to aporte_allocations

Revision ID: a1b2c3d4e5f6
Revises: 9c3b5d72f104
Create Date: 2026-06-06 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9c3b5d72f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("aporte_allocations") as batch:
        batch.add_column(
            sa.Column(
                "excluded",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("aporte_allocations") as batch:
        batch.drop_column("excluded")
```

- [ ] **Step 2: Run migration against dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: Migration applies without error.

- [ ] **Step 3: Commit**

```bash
cd backend && git add alembic/versions/0006_add_excluded_to_allocations.py && git commit -m "feat: migration for aporte_allocations.excluded column"
```

---

### Task 3: Update schemas — add `excluded` to output, add `ExcludeRequest`

**Files:**
- Modify: `backend/app/schemas/aporte.py`

- [ ] **Step 1: Add `excluded` field to `AporteAllocationOut`**

In `backend/app/schemas/aporte.py`, add after `applied_quantity` (line ~22):

```python
    applied_quantity: float | None = None
    excluded: bool = False
```

- [ ] **Step 2: Add `ExcludeRequest` input schema**

Add at the end of the file:

```python
class ExcludeRequest(BaseModel):
    allocation_id: uuid.UUID
```

- [ ] **Step 3: Run existing tests**

Run: `cd backend && uv run pytest tests/api/test_aportes.py -v`
Expected: all PASS (new field has default, existing responses include `excluded: false`)

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/schemas/aporte.py && git commit -m "feat: add excluded to AporteAllocationOut, add ExcludeRequest schema"
```

---

### Task 4: Add `exclude_ids` parameter to `compute_suggestions` and all stages

**Files:**
- Modify: `backend/app/services/algorithm.py`

- [ ] **Step 1: Add `exclude_ids` param to `compute_suggestions`**

Replace the function signature and body (lines ~35-47):

```python
def compute_suggestions(
    portfolio: Portfolio,
    aporte: float,
    exclude_ids: set[str] | None = None,
) -> list[Suggestion]:
    if aporte <= 0:
        return []

    exclude = exclude_ids or set()
    portfolio_total = sum(position_value(a) for a in portfolio.assets)
    new_total = portfolio_total + aporte

    class_share = _stage_one_inter_class(portfolio, new_total, aporte, exclude)
    if not class_share:
        return []

    raw_allocation = _stage_two_intra_class(class_share, portfolio.assets, exclude)
    suggestions = _stage_three_quantize(raw_allocation, portfolio.assets, aporte, new_total)
    return _absorb_residual(suggestions, portfolio.assets, aporte, new_total)
```

- [ ] **Step 2: Add `exclude_ids` to `_stage_one_inter_class`**

Change signature and filter eligible assets:

```python
def _stage_one_inter_class(
    portfolio: Portfolio,
    new_total: float,
    aporte: float,
    exclude_ids: set[str] | None = None,
) -> dict[ClassType, float]:
```

Inside the function, after `assets = portfolio.assets`, add:

```python
    exclude = exclude_ids or set()
    assets = [a for a in portfolio.assets if a.id not in exclude]
```

And change the two references from `portfolio.assets` to `assets`:

```python
    eligible_classes: set[ClassType] = {a.type for a in assets if _is_allocatable(a)}
    # ...
    current_value = sum(position_value(a) for a in assets if a.type == cls)
```

- [ ] **Step 3: Add `exclude_ids` to `_stage_two_intra_class`**

Change signature:

```python
def _stage_two_intra_class(
    class_share: dict[ClassType, float],
    all_assets: list[Asset],
    exclude_ids: set[str] | None = None,
) -> dict[str, float]:
```

Inside the function, filter `all_assets`:

```python
    exclude = exclude_ids or set()
    filtered_assets = [a for a in all_assets if a.id not in exclude]
```

Then replace all references to `all_assets` with `filtered_assets` inside the function body (used in `allocatable` list comprehension and `position_value` sums within the loop).

- [ ] **Step 4: Run existing algorithm tests to verify no regression**

Run: `cd backend && uv run pytest tests/services/test_algorithm_multi_class.py -v`
Expected: all PASS (exclude_ids defaults to None, existing behavior unchanged)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/algorithm.py && git commit -m "feat: add exclude_ids param to compute_suggestions and stage functions"
```

---

### Task 5: Write failing tests for exclude algorithm behavior

**Files:**
- Create: `backend/tests/services/test_algorithm_exclude.py`

- [ ] **Step 1: Write test file with core exclude cases**

```python
"""Tests for compute_suggestions with exclude_ids parameter."""
from __future__ import annotations

from app.services.algorithm import compute_suggestions
from app.services.types import Asset, Portfolio


def _make_asset(
    id: str,
    asset_type: str,
    amount: float,
    strength: int = 1,
    price: float = 100.0,
    name: str = "",
) -> Asset:
    return Asset(
        id=id,
        type=asset_type,
        name=name or id,
        amount=amount,
        strength=strength,
        current_price=price,
    )


def _make_portfolio(assets: list[Asset], targets: dict[str, float]) -> Portfolio:
    return Portfolio(assets=assets, targets=targets, questions=[])


class TestExcludeBasic:
    def test_exclude_one_asset(self):
        """Excluding an asset gives it $0 suggestion and redistributes to others."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
        ]
        targets = {"criptomoedas": 30, "acoes_nacionais": 50, "rendafixa": 20}
        portfolio = _make_portfolio(assets, targets)

        all_suggestions = compute_suggestions(portfolio, 500)
        assert len(all_suggestions) == 3

        excluded = compute_suggestions(portfolio, 500, exclude_ids={"a1"})
        # a1 should not appear in results
        ids = {s.asset_id for s in excluded}
        assert "a1" not in ids
        # Total of remaining suggestions should be close to 500
        total = sum(s.suggestion_value for s in excluded)
        assert total > 490  # allow rounding

    def test_exclude_preserves_total(self):
        """Total of non-excluded suggestions equals aporte (within rounding)."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
            _make_asset("a4", "acoes_internacionais", 5, strength=1, price=200),
            _make_asset("a5", "reits", 3, strength=1, price=150),
        ]
        targets = {
            "criptomoedas": 20,
            "acoes_nacionais": 30,
            "rendafixa": 10,
            "acoes_internacionais": 25,
            "reits": 15,
        }
        portfolio = _make_portfolio(assets, targets)

        for exclude_id in ["a1", "a2", "a3", "a4", "a5"]:
            suggestions = compute_suggestions(portfolio, 1000, exclude_ids={exclude_id})
            total = sum(s.suggestion_value for s in suggestions)
            assert total > 990, f"exclude {exclude_id}: total {total} too low"

    def test_exclude_already_excluded(self):
        """Excluding an asset not in the portfolio is a no-op."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
        ]
        targets = {"criptomoedas": 40, "acoes_nacionais": 60}
        portfolio = _make_portfolio(assets, targets)

        base = compute_suggestions(portfolio, 500)
        with_exclusion = compute_suggestions(portfolio, 500, exclude_ids={"nonexistent"})
        assert len(base) == len(with_exclusion)

    def test_exclude_all_but_one(self):
        """Remaining asset gets essentially the full aporte."""
        assets = [
            _make_asset("a1", "criptomoedas", 0.5, strength=0, price=500),
            _make_asset("a2", "acoes_nacionais", 10, strength=1, price=100),
            _make_asset("a3", "rendafixa", 1000, strength=0, price=None),
        ]
        targets = {"criptomoedas": 30, "acoes_nacionais": 50, "rendafixa": 20}
        portfolio = _make_portfolio(assets, targets)

        suggestions = compute_suggestions(portfolio, 500, exclude_ids={"a1", "a2"})
        assert len(suggestions) == 1
        assert suggestions[0].asset_id == "a3"
        assert suggestions[0].suggestion_value > 490
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/services/test_algorithm_exclude.py -v`
Expected: all 4 tests PASS

- [ ] **Step 3: Commit**

```bash
cd backend && git add tests/services/test_algorithm_exclude.py && git commit -m "test: add algorithm tests for exclude_ids parameter"
```

---

### Task 6: Add `exclude_allocation` service function

**Files:**
- Modify: `backend/app/services/aporte_service.py`

- [ ] **Step 1: Add `exclude_allocation` function**

Add at the end of `backend/app/services/aporte_service.py`:

```python
async def exclude_allocation(
    session: AsyncSession,
    event_id: uuid.UUID,
    allocation_id: uuid.UUID,
) -> AporteEvent:
    """Mark an allocation excluded and rebalance remaining allocations.

    Loads the portfolio, runs compute_suggestions with the excluded asset
    IDs filtered out, then persists updated suggestions to DB.
    """
    # Load event
    event = (
        await session.execute(
            select(AporteEvent).where(AporteEvent.id == event_id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise ValueError("event not found")

    # Load the target allocation
    alloc = (
        await session.execute(
            select(AporteAllocation).where(
                AporteAllocation.id == allocation_id,
                AporteAllocation.aporte_event_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if alloc is None:
        raise ValueError("allocation not found")
    if alloc.applied:
        raise ValueError("allocation already applied")
    if alloc.excluded:
        return event  # idempotent

    # Mark excluded
    alloc.excluded = True

    # Collect all currently-excluded asset IDs (position_id is stored as UUID)
    all_allocs = (
        await session.execute(
            select(AporteAllocation).where(
                AporteAllocation.aporte_event_id == event.id
            )
        )
    ).scalars().all()
    exclude_ids: set[str] = {
        str(a.position_id) for a in all_allocs
        if a.excluded and a.position_id is not None
    }

    # Reload portfolio and recompute
    portfolio = await load_portfolio(session, event.user_id, event.portfolio_id)
    suggestions = compute_suggestions(portfolio, event.aporte_value_brl, exclude_ids)

    # Map suggestions by position_id for quick lookup
    suggestion_map = {s.asset_id: s for s in suggestions}

    # Update existing allocations
    for existing in all_allocs:
        if existing.excluded:
            continue
        if existing.position_id and str(existing.position_id) in suggestion_map:
            s = suggestion_map[str(existing.position_id)]
            existing.suggested_value_brl = s.suggestion_value
            existing.suggested_quantity = s.suggestion_quantity
        else:
            # Asset no longer in suggestions (shouldn't happen, but defensive)
            existing.suggested_value_brl = 0
            existing.suggested_quantity = 0

    await session.flush()
    await session.refresh(event, ["allocations"])
    return event
```

- [ ] **Step 2: Run existing tests**

Run: `cd backend && uv run pytest tests/api/test_aportes.py -v`
Expected: all PASS (new function not called by existing code yet)

- [ ] **Step 3: Commit**

```bash
cd backend && git add app/services/aporte_service.py && git commit -m "feat: add exclude_allocation service function"
```

---

### Task 7: Add `POST /api/aportes/{event_id}/exclude` endpoint

**Files:**
- Modify: `backend/app/api/aportes.py`

- [ ] **Step 1: Add exclude endpoint**

In `backend/app/api/aportes.py`, add after the `apply` endpoint (end of file):

```python
@router.post("/{event_id}/exclude", response_model=AporteEventOut)
async def exclude(
    event_id: uuid.UUID,
    body: ExcludeRequest,
    user: User = Depends(current_active_user),
    portfolio: Portfolio = Depends(get_active_portfolio),
    session: AsyncSession = Depends(get_async_session),
) -> AporteEventOut:
    event = await _get_portfolio_event(session, event_id, portfolio.id)
    try:
        updated = await exclude_allocation(session, event.id, body.allocation_id)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_400_BAD_REQUEST
            if "already applied" in detail
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=code, detail=detail)
    await session.commit()
    fresh = await _get_portfolio_event(session, event.id, portfolio.id)
    return AporteEventOut.model_validate(fresh)
```

- [ ] **Step 2: Update imports in `aportes.py`**

Add `ExcludeRequest` to the imports from `app.schemas.aporte` and add the `exclude_allocation` import:

```python
from app.schemas.aporte import (
    AporteAllocationOut,
    AporteCreate,
    AporteEventOut,
    ApplyRequest,
    ExcludeRequest,
)
from app.services.aporte_service import apply_allocation, create_aporte_event, exclude_allocation
```

- [ ] **Step 3: Run existing tests**

Run: `cd backend && uv run pytest tests/api/test_aportes.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/api/aportes.py && git commit -m "feat: add POST /aportes/{event_id}/exclude endpoint"
```

---

### Task 8: Write integration tests for exclude endpoint

**Files:**
- Modify: `backend/tests/api/test_aportes.py`

- [ ] **Step 1: Add integration tests at the end of the file**

```python
async def test_exclude_marks_excluded_and_rebalances(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "ex1@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/aportes", json={"value": 500}, headers=headers)
    event = created.json()
    alloc = event["allocations"][0]

    r = await client.post(
        f"/api/aportes/{event['id']}/exclude",
        json={"allocation_id": alloc["id"]},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    excluded_allocs = [a for a in body["allocations"] if a["excluded"]]
    non_excluded = [a for a in body["allocations"] if not a["excluded"]]
    assert len(excluded_allocs) == 1
    assert excluded_allocs[0]["id"] == alloc["id"]
    assert excluded_allocs[0]["suggestedValueBrl"] == 0
    # Remaining allocations have redistributed values
    total_remaining = sum(a["suggestedValueBrl"] for a in non_excluded)
    assert total_remaining > 490


async def test_exclude_already_applied_returns_400(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "ex2@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/aportes", json={"value": 500}, headers=headers)
    event = created.json()
    alloc = event["allocations"][0]

    # Apply first
    await client.post(
        f"/api/aportes/{event['id']}/allocations/{alloc['id']}/apply",
        json={},
        headers=headers,
    )

    # Then try to exclude
    r = await client.post(
        f"/api/aportes/{event['id']}/exclude",
        json={"allocation_id": alloc["id"]},
        headers=headers,
    )
    assert r.status_code == 400


async def test_exclude_nonexistent_allocation_returns_404(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "ex3@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/aportes", json={"value": 500}, headers=headers)
    event = created.json()

    r = await client.post(
        f"/api/aportes/{event['id']}/exclude",
        json={"allocation_id": "00000000-0000-0000-0000-000000000000"},
        headers=headers,
    )
    assert r.status_code == 404


async def test_exclude_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        "/api/aportes/00000000-0000-0000-0000-000000000000/exclude",
        json={"allocation_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 401


async def test_exclude_cross_user_boundary_returns_404(client: AsyncClient) -> None:
    """User A creates an aporte; user B cannot exclude its allocations."""
    token_a = await _register_login_seed(client, "owner-ex@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    created = await client.post("/api/aportes", json={"value": 500}, headers=headers_a)
    event = created.json()
    alloc = event["allocations"][0]

    token_b = await _register_login_seed(client, "intruder-ex@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = await client.post(
        f"/api/aportes/{event['id']}/exclude",
        json={"allocation_id": alloc["id"]},
        headers=headers_b,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run all aporte tests**

Run: `cd backend && uv run pytest tests/api/test_aportes.py -v`
Expected: all PASS (including the 5 new tests)

- [ ] **Step 3: Commit**

```bash
cd backend && git add tests/api/test_aportes.py && git commit -m "test: add integration tests for exclude endpoint"
```

---

### Task 9: Update frontend types and API client

**Files:**
- Modify: `frontend/src/lib/types/api.ts`
- Modify: `frontend/src/lib/api/aportes.ts`

- [ ] **Step 1: Add `excluded` to `AporteAllocationOut`**

In `frontend/src/lib/types/api.ts`, add after `appliedQuantity` (line ~48):

```typescript
  appliedQuantity: number | null;
  excluded: boolean;
```

- [ ] **Step 2: Add `excludeAllocation` to API client**

In `frontend/src/lib/api/aportes.ts`, add at the end of the file:

```typescript
export const excludeAllocation = (eventId: string, allocationId: string) =>
  apiRequest<AporteEventOut>(`/aportes/${eventId}/exclude`, {
    method: "POST",
    body: JSON.stringify({ allocation_id: allocationId }),
  });
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/lib/types/api.ts src/lib/api/aportes.ts && git commit -m "feat: add excluded type and excludeAllocation API client"
```

---

### Task 10: Update aporte page — X button, excluded styling, rebalance

**Files:**
- Modify: `frontend/src/routes/(app)/aporte/+page.svelte`

- [ ] **Step 1: Import `excludeAllocation`**

In the `<script>` tag, update the import (line ~4):

```typescript
  import { createAporte, applyAllocation, excludeAllocation } from "$lib/api/aportes";
```

- [ ] **Step 2: Add state variable for excluding**

Add after `let applyingId` (line ~26):

```typescript
  let excludingId = $state<string | null>(null);
```

- [ ] **Step 3: Add `handleExclude` function**

Add after the `handleAportar` function:

```typescript
  async function handleExclude(allocationId: string) {
    if (!event) return;
    excludingId = allocationId;
    error = null;
    try {
      const updated = await excludeAllocation(event.id, allocationId);
      event = updated;
      positions = await listPositions();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      excludingId = null;
    }
  }
```

- [ ] **Step 4: Add `excluded` to `EnrichedRow` type and mapping**

In the `EnrichedRow` type (line ~121), add:

```typescript
    appliedValueBrl: number | null;
    excluded: boolean;
```

In the `rows` derived block, add `excluded` to the mapping:

```typescript
              appliedValueBrl: a.appliedValueBrl,
              excluded: a.excluded,
```

- [ ] **Step 5: Update row styling for excluded**

Change the `<tr>` element (line ~241) to handle excluded state:

```svelte
            <tr
              class="border-b border-slate-100 last:border-0"
              class:opacity-60={r.applied}
              class:opacity-40={r.excluded}
            >
```

- [ ] **Step 6: Add strikethrough to ticker for excluded**

Change the ticker `<td>` (line ~253):

```svelte
              <td class="px-3 py-2 font-medium" class:line-through={r.excluded}>{r.name}</td>
```

- [ ] **Step 7: Add X button column — update the header**

Add a new `<th>` after the "Aportar!" header:

```svelte
            <th class="px-3 py-2"></th>
```

- [ ] **Step 8: Add X button in the row — after the Aportar cell**

After the existing Aportar/aplicado `<td>`, add:

```svelte
              <td class="px-3 py-2 text-right">
                {#if r.excluded}
                  <span class="text-xs text-slate-400">excluído</span>
                {:else if r.applied}
                  <!-- no action needed -->
                {:else}
                  <button
                    onclick={() => handleExclude(r.id)}
                    disabled={excludingId !== null || applyingId !== null}
                    class="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-30"
                    title="Excluir sugestão"
                  >
                    {#if excludingId === r.id}
                      <span class="inline-block animate-spin text-xs">⏳</span>
                    {:else}
                      ✕
                    {/if}
                  </button>
                {/if}
              </td>
```

- [ ] **Step 9: Update `totalSuggested` to exclude excluded allocations**

Change the `totalSuggested` derived (line ~113):

```typescript
  let totalSuggested = $derived(
    event
      ? event.allocations
          .filter((a) => !a.excluded)
          .reduce((s, a) => s + a.suggestedValueBrl, 0)
      : 0,
  );
```

- [ ] **Step 10: Update `classSuggested` to exclude excluded allocations**

In the `classSuggested` derived block, change the accumulation loop:

```typescript
      for (const a of event.allocations) {
        if (a.excluded) continue;
        out[a.assetTypeSnapshot] = (out[a.assetTypeSnapshot] ?? 0) + a.suggestedValueBrl;
      }
```

- [ ] **Step 11: Update `rows` to exclude excluded from sorting and filtering (optional)**

Keep excluded rows in the list (for display), but sort them to the bottom:

In the `.sort()` call, update to push excluded to bottom:

```typescript
          .sort((a, b) => {
            if (a.excluded !== b.excluded) return a.excluded ? 1 : -1;
            return b.suggestedValueBrl - a.suggestedValueBrl;
          })
```

- [ ] **Step 12: Add visual feedback for the freed amount in summary**

After the "Total sugerido" summary item, add a freed amount indicator:

```svelte
      {#if event.allocations.some((a) => a.excluded)}
        {@const freed = event.allocations
          .filter((a) => a.excluded)
          .reduce((s, a) => s + a.suggestedValueBrl, 0)}
        <div>
          <span class="text-xs uppercase tracking-wide text-slate-500">Liberado</span>
          <p class="text-lg font-bold text-amber-700">{fmtBRL(freed)}</p>
        </div>
      {/if}
```

- [ ] **Step 13: Commit**

```bash
cd frontend && git add src/routes/\(app\)/aporte/+page.svelte && git commit -m "feat: add exclude button and rebalance UI to aporte page"
```

---

### Task 11: Frontend component tests for exclude

**Files:**
- Create: `frontend/tests/components/AporteExclude.test.ts`

- [ ] **Step 1: Create test file**

```typescript
import { render, screen, fireEvent } from "@testing-library/svelte";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Page from "+/routes/(app)/aporte/+page.svelte";

// Mock the API modules
vi.mock("$lib/api/aportes", () => ({
  createAporte: vi.fn(),
  applyAllocation: vi.fn(),
  excludeAllocation: vi.fn(),
}));
vi.mock("$lib/api/positions", () => ({
  listPositions: vi.fn().mockResolvedValue([]),
}));

import { createAporte, excludeAllocation } from "$lib/api/aportes";

const mockEvent = {
  id: "evt-1",
  aporteValueBrl: 500,
  createdAt: "2026-01-01T00:00:00Z",
  allocations: [
    {
      id: "alloc-1", positionId: "p1", positionNameSnapshot: "PETR4",
      assetTypeSnapshot: "acoes_nacionais", priceAtAporteBrl: 28.5,
      suggestedValueBrl: 200, suggestedQuantity: 7,
      applied: false, appliedAt: null, appliedValueBrl: null, appliedQuantity: null,
      excluded: false,
    },
    {
      id: "alloc-2", positionId: "p2", positionNameSnapshot: "AAPL",
      assetTypeSnapshot: "acoes_internacionais", priceAtAporteBrl: 180,
      suggestedValueBrl: 200, suggestedQuantity: 1.1,
      applied: false, appliedAt: null, appliedValueBrl: null, appliedQuantity: null,
      excluded: false,
    },
    {
      id: "alloc-3", positionId: "p3", positionNameSnapshot: "BTC",
      assetTypeSnapshot: "criptomoedas", priceAtAporteBrl: 50000,
      suggestedValueBrl: 100, suggestedQuantity: 0.002,
      applied: false, appliedAt: null, appliedValueBrl: null, appliedQuantity: null,
      excluded: false,
    },
  ],
};

const mockExcludedEvent = {
  ...mockEvent,
  allocations: [
    { ...mockEvent.allocations[0], excluded: true, suggestedValueBrl: 0, suggestedQuantity: 0 },
    { ...mockEvent.allocations[1], suggestedValueBrl: 300, suggestedQuantity: 1.67 },
    { ...mockEvent.allocations[2], suggestedValueBrl: 200, suggestedQuantity: 0.004 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  (createAporte as any).mockResolvedValue(mockEvent);
  (excludeAllocation as any).mockResolvedValue(mockExcludedEvent);
});

describe("Aporte exclude button", () => {
  it("renders X button for each non-applied, non-excluded row", async () => {
    render(Page);
    await fireEvent.click(screen.getByText("Calcular"));
    const xButtons = screen.getAllByText("✕");
    expect(xButtons.length).toBe(3);
  });

  it("calls excludeAllocation and updates table on click", async () => {
    render(Page);
    await fireEvent.click(screen.getByText("Calcular"));
    const xButtons = screen.getAllByText("✕");
    await fireEvent.click(xButtons[0]);
    expect(excludeAllocation).toHaveBeenCalledWith("evt-1", "alloc-1");
    // After rebalance, total sugerido should reflect non-excluded allocations
    expect(screen.getByText("R$ 500,00")).toBeTruthy();
  });

  it("shows excluded label on excluded rows", async () => {
    (createAporte as any).mockResolvedValue(mockExcludedEvent);
    render(Page);
    await fireEvent.click(screen.getByText("Calcular"));
    expect(screen.getByText("excluído")).toBeTruthy();
  });

  it("displays freed amount when exclusion exists", async () => {
    (createAporte as any).mockResolvedValue(mockExcludedEvent);
    render(Page);
    await fireEvent.click(screen.getByText("Calcular"));
    expect(screen.getByText("Liberado")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && npm test`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
cd frontend && git add tests/components/AporteExclude.test.ts && git commit -m "test: add frontend component tests for aporte exclude feature"
```

---
### Task 12: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

Run: `cd backend && uv run pytest -v`
Expected: all PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd frontend && npm run check`
Expected: no errors

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npm test`
Expected: all PASS

- [ ] **Step 4: Run lint**

Run: `cd backend && uv run ruff check .`
Expected: no errors

- [ ] **Step 5: Final commit if any lint fixes needed**

```bash
git add -A && git commit -m "fix: lint and type-check fixes"
```
