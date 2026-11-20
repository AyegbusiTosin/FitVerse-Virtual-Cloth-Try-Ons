import React, { useEffect, useMemo, useState } from "react";
import {
  Camera,
  Check,
  Save,
  Shirt,
  Sliders,
  Sparkles,
} from "lucide-react";
import MannequinCanvas from "./components/MannequinCanvas";
import {
  evaluateOutfitLook,
  extractMeasurementsFromPhoto,
  fetchCatalogProducts,
  listShopperLooks,
  saveShopperLook,
  upsertShopperProfile,
} from "./api/fitverseApi";
import "./App.css";

const AVATAR_PRESETS = {
  slim: {
    chest_circumference: 35.0,
    shoulder_width: 16.5,
    preferred_body_length: 27.0,
    preferred_sleeve_length: 24.5,
    waist_circumference: 29.0,
    hip_circumference: 35.0,
    preferred_inseam_length: 32.0,
  },
  athletic: {
    chest_circumference: 40.0,
    shoulder_width: 19.0,
    preferred_body_length: 28.0,
    preferred_sleeve_length: 25.0,
    waist_circumference: 32.0,
    hip_circumference: 38.0,
    preferred_inseam_length: 32.0,
  },
  average: {
    chest_circumference: 38.0,
    shoulder_width: 18.0,
    preferred_body_length: 28.0,
    preferred_sleeve_length: 25.0,
    waist_circumference: 32.0,
    hip_circumference: 38.0,
    preferred_inseam_length: 32.0,
  },
  curvy: {
    chest_circumference: 39.0,
    shoulder_width: 16.5,
    preferred_body_length: 26.5,
    preferred_sleeve_length: 23.5,
    waist_circumference: 31.0,
    hip_circumference: 42.0,
    preferred_inseam_length: 30.0,
  },
  broad: {
    chest_circumference: 44.0,
    shoulder_width: 20.5,
    preferred_body_length: 29.5,
    preferred_sleeve_length: 26.0,
    waist_circumference: 36.0,
    hip_circumference: 42.0,
    preferred_inseam_length: 32.0,
  },
};

const SLIDER_SPECS = [
  { key: "chest_circumference", label: "Chest", min: 28, max: 56, step: 0.5 },
  { key: "shoulder_width", label: "Shoulders", min: 13, max: 25, step: 0.5 },
  { key: "preferred_body_length", label: "Torso Length", min: 22, max: 35, step: 0.5 },
  { key: "preferred_sleeve_length", label: "Sleeve Length", min: 20, max: 32, step: 0.5 },
  { key: "waist_circumference", label: "Waist", min: 24, max: 50, step: 0.5 },
  { key: "hip_circumference", label: "Hips", min: 30, max: 56, step: 0.5 },
  { key: "preferred_inseam_length", label: "Inseam", min: 25, max: 38, step: 0.5 },
];

export default function App() {
  // Path A vs Path B -> Everything leads to bodyProfile + 3D mannequin
  const [inputTab, setInputTab] = useState("mannequin"); // "mannequin" | "photo"
  const [avatarPreset, setAvatarPreset] = useState("average");
  const [measurementSource, setMeasurementSource] = useState("MANUAL_MANNEQUIN");
  const [bodyProfile, setBodyProfile] = useState(AVATAR_PRESETS.average);

  // Photo extraction state
  const [heightInches, setHeightInches] = useState(68);
  const [photoFile, setPhotoFile] = useState(null);
  const [extracting, setExtracting] = useState(false);

  // Catalog & My Look outfit state
  const [catalog, setCatalog] = useState([]);
  const [selectedMap, setSelectedMap] = useState({}); // { [productId]: fit_preference }
  const [recommendations, setRecommendations] = useState([]);
  const [evaluating, setEvaluating] = useState(false);

  // Shopper Save Look state
  const [shopperEmail, setShopperEmail] = useState("demo.shopper@fitverse.ng");
  const [lookName, setLookName] = useState("Lagos Gallery Look");
  const [savedLooks, setSavedLooks] = useState([]);
  const [savingLook, setSavingLook] = useState(false);

  const [errorMsg, setErrorMsg] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  // 1. Load storefront catalog on mount & pre-select seeded items
  useEffect(() => {
    fetchCatalogProducts()
      .then((products) => {
        setCatalog(products);
        const initialSelection = {};
        for (const p of products) {
          initialSelection[p.id] = p.category === "blazer" ? "relaxed" : "regular";
        }
        setSelectedMap(initialSelection);
      })
      .catch((err) => setErrorMsg(err.message));
  }, []);

  // 2. Re-evaluate outfit live whenever bodyProfile or selected garments change
  useEffect(() => {
    const items = Object.entries(selectedMap).map(([productId, fit_preference]) => ({
      product_id: Number(productId),
      fit_preference,
    }));

    if (items.length === 0) {
      setRecommendations([]);
      return;
    }

    let cancelled = false;
    setEvaluating(true);
    evaluateOutfitLook(bodyProfile, items)
      .then((res) => {
        if (!cancelled) {
          setRecommendations(res.recommendations || []);
          setErrorMsg("");
        }
      })
      .catch((err) => {
        if (!cancelled) setErrorMsg(err.message);
      })
      .finally(() => {
        if (!cancelled) setEvaluating(false);
      });

    return () => {
      cancelled = true;
    };
  }, [bodyProfile, selectedMap]);

  const selectedProducts = useMemo(
    () => catalog.filter((p) => Boolean(selectedMap[p.id])),
    [catalog, selectedMap]
  );

  const recBySku = useMemo(() => {
    const map = {};
    for (const r of recommendations) {
      map[r.product_sku] = r;
    }
    return map;
  }, [recommendations]);

  function handlePresetSelect(presetKey) {
    setAvatarPreset(presetKey);
    setBodyProfile({ ...AVATAR_PRESETS[presetKey] });
    setMeasurementSource("MANUAL_MANNEQUIN");
    setStatusMsg("");
  }

  function handleSliderChange(key, value) {
    setBodyProfile((prev) => ({ ...prev, [key]: Number(value) }));
    setMeasurementSource("MANUAL_MANNEQUIN");
  }

  async function handlePhotoExtract(e) {
    e.preventDefault();
    if (!photoFile) {
      setErrorMsg("Please select a front-facing photo first.");
      return;
    }
    setExtracting(true);
    setErrorMsg("");
    setStatusMsg("");

    try {
      const data = await extractMeasurementsFromPhoto(heightInches, photoFile);
      setBodyProfile(data.body_profile_draft);
      setAvatarPreset(data.suggested_avatar_preset);
      setMeasurementSource("ESTIMATED_FROM_PHOTO");
      setInputTab("mannequin"); // Transition straight to the morphed 3D mannequin!
      setStatusMsg(
        `3D mannequin morphed from photo (${data.suggested_avatar_preset} build). Fine-tune any slider below.`
      );
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setExtracting(false);
    }
  }

  function toggleProduct(productId) {
    setSelectedMap((prev) => {
      const next = { ...prev };
      if (next[productId]) {
        delete next[productId];
      } else {
        next[productId] = "regular";
      }
      return next;
    });
  }

  function updateProductFit(productId, fitPref) {
    setSelectedMap((prev) => ({
      ...prev,
      [productId]: fitPref,
    }));
  }

  async function handleSaveLook() {
    const items = Object.entries(selectedMap).map(([productId, fit_preference]) => ({
      product_id: Number(productId),
      fit_preference,
    }));
    if (items.length === 0) {
      setErrorMsg("Select at least one garment before saving a look.");
      return;
    }
    setSavingLook(true);
    setErrorMsg("");
    setStatusMsg("");

    try {
      await upsertShopperProfile(shopperEmail, {
        display_name: shopperEmail.split("@")[0],
        avatar_preset: avatarPreset,
        height_inches: Number(heightInches),
        body: bodyProfile,
      });

      await saveShopperLook(shopperEmail, {
        look_name: lookName || "Untitled Look",
        notes: `Source: ${measurementSource}`,
        items,
      });

      const updatedLooks = await listShopperLooks(shopperEmail);
      setSavedLooks(updatedLooks);
      setStatusMsg(`Saved "${lookName}" to your profile!`);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setSavingLook(false);
    }
  }

  function handleLoadSavedLook(look) {
    const nextSelection = {};
    for (const item of look.items) {
      nextSelection[item.product_id] = item.fit_preference;
    }
    setSelectedMap(nextSelection);
    setLookName(look.look_name);
    setStatusMsg(`Loaded "${look.look_name}" onto your 3D mannequin.`);
  }

  return (
    <div className="studio-shell">
      <header className="topbar">
        <div className="brand">
          <Sparkles size={20} color="#0f766e" />
          <span>FitVerse Studio</span>
          <span className="brand-pill">3D Virtual Try-On POC</span>
        </div>
        <div style={{ fontSize: "0.82rem", color: "#64748b" }}>
          {evaluating ? "Updating fit drape..." : `${selectedProducts.length} garments on mannequin`}
        </div>
      </header>

      <main className="studio-grid">
        {/* LEFT PANEL: Two-Way Body Input (Manual Mannequin OR Photo -> Mannequin) */}
        <section className="panel">
          <div className="tab-row">
            <button
              type="button"
              className={`tab-btn ${inputTab === "mannequin" ? "active" : ""}`}
              onClick={() => setInputTab("mannequin")}
            >
              <Sliders size={15} /> 3D Mannequin
            </button>
            <button
              type="button"
              className={`tab-btn ${inputTab === "photo" ? "active" : ""}`}
              onClick={() => setInputTab("photo")}
            >
              <Camera size={15} /> From Photo
            </button>
          </div>

          {inputTab === "mannequin" ? (
            <>
              <div>
                <h3 className="section-title" style={{ marginBottom: "0.5rem" }}>
                  Body Shape Preset
                </h3>
                <div className="preset-grid">
                  {Object.keys(AVATAR_PRESETS).map((presetKey) => (
                    <button
                      key={presetKey}
                      type="button"
                      className={`preset-chip ${avatarPreset === presetKey ? "active" : ""}`}
                      onClick={() => handlePresetSelect(presetKey)}
                    >
                      {presetKey}
                    </button>
                  ))}
                </div>
              </div>

              <div className="slider-group">
                <h3 className="section-title">Custom Measurements (inches)</h3>
                {SLIDER_SPECS.map((spec) => (
                  <div key={spec.key} className="slider-row">
                    <div className="slider-label">
                      <span>{spec.label}</span>
                      <strong>{bodyProfile[spec.key]} in</strong>
                    </div>
                    <input
                      type="range"
                      min={spec.min}
                      max={spec.max}
                      step={spec.step}
                      value={bodyProfile[spec.key] ?? spec.min}
                      onChange={(e) => handleSliderChange(spec.key, e.target.value)}
                    />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <form className="upload-box" onSubmit={handlePhotoExtract}>
              <h3 className="section-title">Generate Mannequin from Photo</h3>
              <p style={{ margin: 0, fontSize: "0.78rem", color: "#64748b" }}>
                Your photo is processed strictly in memory—never saved—and converted directly into your 3D mannequin proportions.
              </p>

              <label style={{ fontSize: "0.8rem", fontWeight: 600 }}>
                Your Height (inches)
                <input
                  type="number"
                  className="text-input"
                  min={48}
                  max={90}
                  step={0.5}
                  value={heightInches}
                  onChange={(e) => setHeightInches(Number(e.target.value))}
                  style={{ marginTop: "0.25rem" }}
                />
              </label>

              <label style={{ fontSize: "0.8rem", fontWeight: 600 }}>
                Front-Facing Full-Body Photo
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setPhotoFile(e.target.files?.[0] || null)}
                  style={{ marginTop: "0.3rem", fontSize: "0.8rem" }}
                />
              </label>

              <button type="submit" className="primary-btn" disabled={extracting}>
                <Camera size={16} />
                {extracting ? "Extracting Proportions..." : "Build 3D Mannequin"}
              </button>
            </form>
          )}
        </section>

        {/* CENTER STAGE: Interactive Three.js Parametric Mannequin */}
        <section className="stage-panel">
          <div className="stage-banner">
            <span className="source-chip">
              Build: <strong style={{ textTransform: "capitalize" }}>{avatarPreset}</strong>
            </span>
            <span className="source-chip">
              {measurementSource === "ESTIMATED_FROM_PHOTO"
                ? "Source: Photo-Derived (Editable)"
                : "Source: Privacy-First 3D Sliders"}
            </span>
          </div>

          <MannequinCanvas
            body={bodyProfile}
            selectedProducts={selectedProducts}
            recommendations={recommendations}
          />
        </section>

        {/* RIGHT SIDEBAR: Storefront Catalog, Size Recommendations & Save Look */}
        <aside className="panel">
          {errorMsg && <div className="error-banner">{errorMsg}</div>}
          {statusMsg && <div className="success-banner">{statusMsg}</div>}

          <div>
            <h3 className="section-title" style={{ marginBottom: "0.55rem" }}>
              <Shirt size={16} style={{ verticalAlign: "text-bottom", marginRight: "0.35rem" }} />
              My Look — Garment Catalog
            </h3>

            <div className="catalog-list">
              {catalog.map((prod) => {
                const isSelected = Boolean(selectedMap[prod.id]);
                const activeFit = selectedMap[prod.id] || "regular";
                const rec = recBySku[prod.external_sku];

                return (
                  <div
                    key={prod.id}
                    className={`garment-card ${isSelected ? "selected" : ""}`}
                  >
                    <div className="garment-header">
                      <div>
                        <div className="garment-name">{prod.name}</div>
                        <div className="garment-meta">
                          {prod.category} • {prod.garment_group.replace("_", " ")}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="preset-chip"
                        onClick={() => toggleProduct(prod.id)}
                      >
                        {isSelected ? (
                          <>
                            <Check size={13} style={{ verticalAlign: "middle" }} /> Wearing
                          </>
                        ) : (
                          "+ Try On"
                        )}
                      </button>
                    </div>

                    {isSelected && (
                      <>
                        <div className="fit-pills">
                          {["regular", "relaxed", "oversized"].map((fit) => (
                            <button
                              key={fit}
                              type="button"
                              className={`fit-pill ${activeFit === fit ? "active" : ""}`}
                              onClick={() => updateProductFit(prod.id, fit)}
                            >
                              {fit}
                            </button>
                          ))}
                        </div>

                        {rec && (
                          <div>
                            <div className="rec-badge">
                              <span>
                                {rec.status === "success"
                                  ? "Recommended Size"
                                  : rec.shopper_message}
                              </span>
                              {rec.recommended_size && (
                                <span className="size-pill">{rec.recommended_size}</span>
                              )}
                            </div>

                            {rec.avatar_fit_zones && (
                              <div className="zone-tags">
                                {Object.entries(rec.avatar_fit_zones).map(([zone, label]) => (
                                  <span key={zone} className="zone-tag">
                                    {zone.replace("_", " ")}: <strong>{label.replaceAll("_", " ")}</strong>
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <h3 className="section-title">Save Look to Profile</h3>
            <input
              type="email"
              className="text-input"
              placeholder="Shopper email"
              value={shopperEmail}
              onChange={(e) => setShopperEmail(e.target.value)}
            />
            <input
              type="text"
              className="text-input"
              placeholder="Look name (e.g., Lagos Gallery Look)"
              value={lookName}
              onChange={(e) => setLookName(e.target.value)}
            />
            <button
              type="button"
              className="primary-btn"
              onClick={handleSaveLook}
              disabled={savingLook}
            >
              <Save size={15} />
              {savingLook ? "Saving Look..." : "Save Look"}
            </button>

            {savedLooks.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginTop: "0.35rem" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#64748b" }}>
                  Saved Outfits ({savedLooks.length})
                </span>
                {savedLooks.map((look) => (
                  <button
                    key={look.id}
                    type="button"
                    className="preset-chip"
                    style={{ textAlign: "left", borderRadius: "8px" }}
                    onClick={() => handleLoadSavedLook(look)}
                  >
                    {look.look_name} ({look.items.length} items)
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}