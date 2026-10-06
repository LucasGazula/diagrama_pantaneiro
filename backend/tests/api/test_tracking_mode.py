async def test_price_edit_preserves_balance_and_mode_change_converts(client):
    await client.post(
        "/api/auth/register", json={"email": "mode@example.com", "password": "StrongPass!123"}
    )
    login = await client.post(
        "/api/auth/jwt/login", data={"username": "mode@example.com", "password": "StrongPass!123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        "/api/positions",
        headers=headers,
        json={
            "name": "Tesouro Selic 2029",
            "assetType": "rendafixa",
            "amount": 1000,
            "trackingMode": "balance",
            "strength": 0,
        },
    )
    assert response.status_code == 201
    pid = response.json()["id"]
    path = f"/api/positions/{pid}"
    quote = await client.patch(path, headers=headers, json={"currentPrice": 500})
    assert quote.json()["currentValueBrl"] == 1000
    converted = await client.patch(path, headers=headers, json={"trackingMode": "units"})
    assert converted.json()["amount"] == 2
    assert converted.json()["currentValueBrl"] == 1000
    assert (
        await client.patch(path, headers=headers, json={"currentPrice": None})
    ).status_code == 422
    balance = await client.patch(
        path, headers=headers, json={"trackingMode": "balance", "currentPrice": None}
    )
    assert balance.json()["amount"] == 1000
    assert balance.json()["currentValueBrl"] == 1000
