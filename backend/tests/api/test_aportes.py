from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _register_login_seed(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass!123"},
    )
    r = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": "StrongPass!123"},
    )
    token = r.json()["access_token"]
    await client.get("/api/positions", headers={"Authorization": f"Bearer {token}"})
    return token


async def test_create_aporte_requires_auth(client: AsyncClient) -> None:
    r = await client.post("/api/aportes", json={"value": 500})
    assert r.status_code == 401


async def test_create_aporte_returns_event_with_allocations(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "ap1@example.com")
    r = await client.post(
        "/api/aportes",
        json={"value": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["aporteValueBrl"] == 500
    assert len(body["allocations"]) == 3
    for a in body["allocations"]:
        assert a["applied"] is False
        assert a["suggestedValueBrl"] > 0


async def test_create_aporte_with_non_positive_value_rejected(
    client: AsyncClient,
) -> None:
    token = await _register_login_seed(client, "ap2@example.com")
    r = await client.post(
        "/api/aportes",
        json={"value": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_get_aporte_by_id_returns_detail(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "ap3@example.com")
    created = await client.post(
        "/api/aportes",
        json={"value": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    event_id = created.json()["id"]
    r = await client.get(
        f"/api/aportes/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == event_id


async def test_apply_allocation_marks_applied_and_updates_position(
    client: AsyncClient,
) -> None:
    token = await _register_login_seed(client, "ap4@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/api/aportes", json={"value": 500}, headers=headers)
    event = created.json()
    alloc = event["allocations"][0]

    r = await client.post(
        f"/api/aportes/{event['id']}/allocations/{alloc['id']}/apply",
        json={},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True
    assert body["appliedAt"] is not None


async def test_list_aportes_newest_first(client: AsyncClient) -> None:
    token = await _register_login_seed(client, "history@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Empty list initially
    r = await client.get("/api/aportes", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    # Create 3 aportes with different values
    for v in [500, 1000, 2500]:
        await client.post("/api/aportes", json={"value": v}, headers=headers)

    r = await client.get("/api/aportes", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 3
    # Newest first: 2500 was last created
    values_in_order = [e["aporteValueBrl"] for e in events]
    assert values_in_order == [2500, 1000, 500]


async def test_list_aportes_is_user_scoped(client: AsyncClient) -> None:
    token_a = await _register_login_seed(client, "list-a@example.com")
    await client.post(
        "/api/aportes", json={"value": 777}, headers={"Authorization": f"Bearer {token_a}"}
    )

    token_b = await _register_login_seed(client, "list-b@example.com")
    r = await client.get("/api/aportes", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    # B hasn't created any aportes
    assert r.json() == []


async def test_apply_cannot_cross_user_boundary(client: AsyncClient) -> None:
    """User A creates an aporte; user B cannot apply its allocations."""
    token_a = await _register_login_seed(client, "owner@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    created = await client.post("/api/aportes", json={"value": 500}, headers=headers_a)
    event = created.json()
    alloc = event["allocations"][0]

    token_b = await _register_login_seed(client, "intruder@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = await client.post(
        f"/api/aportes/{event['id']}/allocations/{alloc['id']}/apply",
        json={},
        headers=headers_b,
    )
    assert r.status_code == 404


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
