# Aporte Exclude & Rebalance Design

## Overview

Allow users to exclude individual aporte suggestions from the table and instantly rebalance the remaining suggestions. Excluded amounts are redistributed to remaining assets, trying to respect target allocation goals. Exclusions are persisted to the database.

## User Flow

```
Page loads → user enters amount → POST /api/aportes → shows N suggestions
→ user clicks X on a row → POST /api/aportes/{id}/exclude { allocation_id }
→ response has updated allocations (1 excluded, values redistributed)
→ table updates, excluded row grayed out
→ user can repeat exclusion or click "Aportar" on remaining
```

## Backend

### New Endpoint

**`POST /api/aportes/{event_id}/exclude`**

Request body:
```json
{ "allocation_id": "uuid" }
```

Response: `AporteEventOut` (same shape as create, with updated allocations)

Status codes:
- `200 OK` — exclusion applied, rebalanced allocations returned
- `400 Bad Request` — allocation already applied, or allocation not part of this event
- `404 Not Found` — event does not exist or belongs to different portfolio

### Rebalance Logic

Approach B enhanced — proportional redistribution that tries to respect targets:

1. Load event + allocations from DB
2. Validate: allocation exists, belongs to this event, is not already applied
3. Mark allocation as `excluded = true`
4. Compute freed amount = excluded allocation's `suggested_value_brl`
5. Compute adjusted total = original `aporte_value_brl` − freed amount
6. For each remaining asset class with eligible allocations:
   - Compute `gap = max(0, target_value(adjusted_total) - current_value)`
7. Distribute freed amount proportionally to gaps (same logic as Stage 1 of `compute_suggestions`)
8. Within each class receiving a share, split by existing strength/value weights (same logic as Stage 2)
9. Quantize to purchasable units (same logic as Stage 3)
10. Absorb residual via best absorber candidate
11. Persist updated allocations to DB
12. Return full updated event

### DB Changes

Add `excluded` boolean column to `aporte_allocations` table:
- Default: `false`
- Alembic migration (new version file)

### Schema Changes

Add `excluded` field to `AporteAllocationOut`:
```python
excluded: bool = False
```

### Service Layer

New function in `aporte_service.py`:
```python
async def exclude_allocation(
    session, event_id: UUID, allocation_id: UUID
) -> AporteEvent:
```

This function:
- Loads event and allocations
- Validates the allocation
- Runs rebalance logic (extracted into a pure helper for testability)
- Persists and returns

### Algorithm Reuse

The rebalance helper reuses existing logic from `algorithm.py`:
- `_stage_one_inter_class` pattern for gap-proportional distribution
- `_stage_two_intra_class` pattern for within-class splitting
- `_stage_three_quantize` pattern for unit conversion
- `_absorb_residual` for leftover handling

These are not modified — the rebalance helper calls them with adjusted inputs.

## Frontend

### Changes to Aporte Page

File: `frontend/src/routes/(app)/aporte/+page.svelte`

1. **X button per row** — Added to each suggestion row, right-aligned
   - Icon: small `X` or trash icon
   - Triggers `POST /api/aportes/{event_id}/exclude` with allocation ID
   - While request is in-flight: spinner on X, all other X buttons disabled

2. **Excluded row styling**
   - `opacity-40` applied to the row
   - Ticker gets strikethrough text
   - X button disappears or becomes disabled checkmark
   - "Aportar" button disabled

3. **Summary bar update**
   - `Total sugerido` recalculates from non-excluded allocations
   - Show freed amount: "(R$ X liberados)" when any exclusion exists

4. **Error handling**
   - Toast/alert on API failure
   - Row stays as-is (no visual change)

5. **Loading state**
   - All X buttons disabled during any exclude request
   - Prevents race conditions from rapid exclusions

### API Client

New function in `frontend/src/lib/api/aportes.ts`:
```typescript
export const excludeAllocation = (eventId: string, allocationId: string) =>
  apiRequest<AporteEventOut>(`/aportes/${eventId}/exclude`, {
    method: "POST",
    body: JSON.stringify({ allocation_id: allocationId }),
  });
```

### Types

Add `excluded: boolean` to `AporteAllocationOut` in `frontend/src/lib/types/api.ts`.

## Testing

### Backend Tests

File: `tests/services/test_aporte_exclude.py` (new)

- **Basic exclude:** 5 allocations, exclude 1 → 4 remaining, total = original − excluded value
- **Redistribution respects targets:** excluded asset was overweight → freed amount goes to underweight assets
- **Exclude all but 1:** remaining asset gets full adjusted amount
- **Exclude zero-value allocation:** no-op, no change to other allocations
- **Exclude already-applied:** returns 400
- **Exclude non-existent allocation:** returns 404

File: `tests/api/test_aportes.py` (extend)

- **Integration test:** POST exclude via `httpx.AsyncClient`, verify response shape, allocation states, excluded flag

### Frontend Tests

File: `tests/components/AporteExclude.test.ts` (new)

- Render suggestions with X button
- Click X → mock API called with correct IDs
- Response updates allocations, excluded row has correct styling
- Summary bar reflects new total

## Edge Cases

| Case | Handling |
|------|----------|
| Exclude while another exclude in-flight | Disable all X buttons during request |
| Exclude last remaining suggestion | Show message: "adicione pelo menos uma sugestão" |
| Exclude event not found | 404, toast error |
| Exclude allocation from wrong portfolio | 404 (portfolio guard in deps) |
| User refreshes page mid-exclusion | Re-fetch event on mount, shows current state |
