import React, { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Environment, OrbitControls } from "@react-three/drei";

const ZONE_EASE_SCALE = {
  snug: 1.01,
  true_to_size: 1.045,
  relaxed: 1.09,
  oversized: 1.15,
  dropped: 1.12,
};

const CATEGORY_COLORS = {
  polo: "#15803d",
  shirt: "#2563eb",
  hoodie: "#334155",
  blazer: "#b45309",
  trousers: "#d6c7b2",
  jeans: "#1e3a8a",
};

function ParametricMannequin({ body, selectedProducts, recommendations }) {
  // Normalize measurements against baseline reference proportions
  const dims = useMemo(() => {
    const chestScale = (body.chest_circumference || 38) / 38;
    const shoulderScale = (body.shoulder_width || 18) / 18;
    const waistScale = (body.waist_circumference || 32) / 32;
    const hipScale = (body.hip_circumference || 38) / 38;
    const torsoHeight = ((body.preferred_body_length || 28) / 28) * 1.15;
    const legHeight = ((body.preferred_inseam_length || 32) / 32) * 1.45;
    const armLength = ((body.preferred_sleeve_length || 25) / 25) * 1.05;

    return {
      chestRadius: 0.34 * chestScale,
      waistRadius: 0.27 * waistScale,
      hipRadius: 0.33 * hipScale,
      shoulderHalfSpan: 0.44 * shoulderScale,
      torsoHeight,
      legHeight,
      armLength,
    };
  }, [body]);

  // Map product_sku -> recommendation object
  const recBySku = useMemo(() => {
    const map = {};
    for (const r of recommendations || []) {
      map[r.product_sku] = r;
    }
    return map;
  }, [recommendations]);

  const upperItems = selectedProducts.filter(
    (p) => p.garment_group === "upper_body"
  );
  const lowerItems = selectedProducts.filter(
    (p) => p.garment_group === "lower_body"
  );

  const hipY = dims.legHeight;
  const shoulderY = hipY + dims.torsoHeight;
  const headY = shoulderY + 0.34;

  const skinMat = (
    <meshStandardMaterial color="#e2c6b3" roughness={0.55} metalness={0.05} />
  );

  return (
    <group position={[0, -1.35, 0]}>
      {/* Head & Neck */}
      <mesh position={[0, headY, 0]} castShadow>
        <sphereGeometry args={[0.21, 32, 32]} />
        {skinMat}
      </mesh>
      <mesh position={[0, shoulderY + 0.12, 0]} castShadow>
        <cylinderGeometry args={[0.09, 0.11, 0.22, 24]} />
        {skinMat}
      </mesh>

      {/* Base Torso (Chest -> Waist -> Pelvis) */}
      <mesh position={[0, hipY + dims.torsoHeight * 0.68, 0]} castShadow>
        <cylinderGeometry
          args={[dims.chestRadius, dims.waistRadius, dims.torsoHeight * 0.65, 32]}
        />
        {skinMat}
      </mesh>
      <mesh position={[0, hipY + dims.torsoHeight * 0.22, 0]} castShadow>
        <cylinderGeometry
          args={[dims.waistRadius, dims.hipRadius, dims.torsoHeight * 0.45, 32]}
        />
        {skinMat}
      </mesh>

      {/* Shoulders & Arms */}
      {[-1, 1].map((side) => (
        <group key={side} position={[side * dims.shoulderHalfSpan, shoulderY - 0.05, 0]}>
          <mesh castShadow>
            <sphereGeometry args={[0.11, 24, 24]} />
            {skinMat}
          </mesh>
          <mesh
            position={[side * 0.04, -dims.armLength * 0.48, 0]}
            rotation={[0, 0, side * -0.06]}
            castShadow
          >
            <cylinderGeometry args={[0.085, 0.065, dims.armLength, 24]} />
            {skinMat}
          </mesh>
        </group>
      ))}

      {/* Base Legs */}
      {[-1, 1].map((side) => (
        <mesh
          key={side}
          position={[side * (dims.hipRadius * 0.52), dims.legHeight * 0.5, 0]}
          castShadow
        >
          <cylinderGeometry args={[0.135, 0.095, dims.legHeight, 24]} />
          {skinMat}
        </mesh>
      ))}

      {/* Layered Upper-Body Garments (e.g., Polo underneath Blazer) */}
      {upperItems.map((prod, layerIdx) => {
        const rec = recBySku[prod.external_sku];
        const chestZone = rec?.avatar_fit_zones?.chest || "relaxed";
        const sleeveZone = rec?.avatar_fit_zones?.sleeve_length || "standard";
        const baseEase = ZONE_EASE_SCALE[chestZone] || 1.07;
        const layerOffset = 1 + layerIdx * 0.035;
        const shellScale = baseEase * layerOffset;
        const color = CATEGORY_COLORS[prod.category] || "#475569";
        const sleeveLen =
          prod.category === "polo"
            ? dims.armLength * 0.36
            : dims.armLength * (sleeveZone === "long" ? 0.96 : 0.9);

        return (
          <group key={prod.id}>
            <mesh position={[0, hipY + dims.torsoHeight * 0.5, 0]} castShadow>
              <cylinderGeometry
                args={[
                  dims.chestRadius * shellScale,
                  dims.hipRadius * shellScale,
                  dims.torsoHeight * 1.02,
                  32,
                ]}
              />
              <meshStandardMaterial color={color} roughness={0.75} />
            </mesh>
            {[-1, 1].map((side) => (
              <mesh
                key={side}
                position={[
                  side * (dims.shoulderHalfSpan + 0.02),
                  shoulderY - 0.05 - sleeveLen * 0.48,
                  0,
                ]}
                rotation={[0, 0, side * -0.06]}
                castShadow
              >
                <cylinderGeometry
                  args={[0.1 * shellScale, 0.082 * shellScale, sleeveLen, 24]}
                />
                <meshStandardMaterial color={color} roughness={0.75} />
              </mesh>
            ))}
          </group>
        );
      })}

      {/* Lower-Body Garment (Trousers / Jeans) */}
      {lowerItems.map((prod) => {
        const rec = recBySku[prod.external_sku];
        const hipZone = rec?.avatar_fit_zones?.hips || "regular";
        const inseamZone = rec?.avatar_fit_zones?.inseam || "standard";
        const easeScale = ZONE_EASE_SCALE[hipZone] || 1.05;
        const trouserLen =
          dims.legHeight *
          (inseamZone === "short" ? 0.88 : inseamZone === "long" ? 1.02 : 0.96);
        const color = CATEGORY_COLORS[prod.category] || "#cbd5e1";

        return (
          <group key={prod.id}>
            {/* Pelvis / Waistband */}
            <mesh position={[0, hipY + 0.05, 0]} castShadow>
              <cylinderGeometry
                args={[
                  dims.waistRadius * easeScale,
                  dims.hipRadius * easeScale,
                  0.26,
                  32,
                ]}
              />
              <meshStandardMaterial color={color} roughness={0.8} />
            </mesh>
            {/* Trouser Legs */}
            {[-1, 1].map((side) => (
              <mesh
                key={side}
                position={[
                  side * (dims.hipRadius * 0.52),
                  hipY - trouserLen * 0.5,
                  0,
                ]}
                castShadow
              >
                <cylinderGeometry
                  args={[0.155 * easeScale, 0.125 * easeScale, trouserLen, 24]}
                />
                <meshStandardMaterial color={color} roughness={0.8} />
              </mesh>
            ))}
          </group>
        );
      })}
    </group>
  );
}

export default function MannequinCanvas({
  body,
  selectedProducts,
  recommendations,
}) {
  return (
    <div style={{ width: "100%", height: "100%", minHeight: "540px" }}>
      <Canvas shadows camera={{ position: [0, 0.3, 3.6], fov: 42 }}>
        <color attach="background" args={["#f4f5f7"]} />
        <ambientLight intensity={0.75} />
        <directionalLight position={[4, 6, 4]} intensity={1.1} castShadow />
        <Environment preset="studio" />

        <ParametricMannequin
          body={body}
          selectedProducts={selectedProducts}
          recommendations={recommendations}
        />

        <ContactShadows
          position={[0, -1.35, 0]}
          opacity={0.35}
          scale={6}
          blur={2.2}
        />
        <OrbitControls
          enablePan={false}
          minDistance={2.2}
          maxDistance={5.5}
          target={[0, 0, 0]}
        />
      </Canvas>
    </div>
  );
}