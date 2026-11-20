const JSON_HEADERS = { "Content-Type": "application/json" };

async function handleResponse(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail =
      typeof err.detail === "string"
        ? err.detail
        : Array.isArray(err.detail)
        ? err.detail.map((d) => d.msg).join(", ")
        : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function fetchCatalogProducts(category = "") {
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = await fetch(`/api/catalog/products${query}`);
  return handleResponse(res);
}

export async function evaluateOutfitLook(body, items) {
  const res = await fetch("/api/try-on/look", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ body, items }),
  });
  return handleResponse(res);
}

export async function extractMeasurementsFromPhoto(heightInches, file) {
  const formData = new FormData();
  formData.append("height_inches", String(heightInches));
  formData.append("file", file);

  const res = await fetch("/api/extract-measurements", {
    method: "POST",
    body: formData,
  });
  return handleResponse(res);
}

export async function upsertShopperProfile(externalShopperId, payload) {
  const res = await fetch(
    `/api/shoppers/${encodeURIComponent(externalShopperId)}/profile`,
    {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }
  );
  return handleResponse(res);
}

export async function saveShopperLook(externalShopperId, payload) {
  const res = await fetch(
    `/api/shoppers/${encodeURIComponent(externalShopperId)}/looks`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }
  );
  return handleResponse(res);
}

export async function listShopperLooks(externalShopperId) {
  const res = await fetch(
    `/api/shoppers/${encodeURIComponent(externalShopperId)}/looks`
  );
  return handleResponse(res);
}