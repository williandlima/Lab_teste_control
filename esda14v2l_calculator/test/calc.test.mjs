// Testes do núcleo de cálculo, sem navegador (node esda14v2l_calculator/test/calc.test.mjs).
// Cobre os critérios de aceitação do prompt de desenvolvimento.

import assert from "node:assert/strict";
import {
  STANDARDS,
  TVS_DEFAULTS,
  computeIpico,
  computeEnergy,
  computeVCLUniPos,
  computeVCLUniNeg,
  computeVCLBiMag,
  computeAtenuacaoDB,
  formatSig,
  autoScaleEnergy,
} from "../calc.js";

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// 1. IEC 61000-4-2, 8 kV -> I_pico = 30 A
test("IEC 8kV -> 30A", () => {
  const { I } = computeIpico(STANDARDS.iec, 8);
  assert.equal(formatSig(I), "30");
});

// 2. ST 30 kV -> I_pico = 112,5 A; V_entrada_pico = 30000 V
test("ST 30kV -> 112.5A, Vin=30000V", () => {
  const { I, V_V } = computeIpico(STANDARDS.st30, 30);
  assert.equal(formatSig(I), "112.5");
  assert.equal(V_V, 30000);
});

// 3. NAV 25 kV -> I_pico = 50A; E ~= 156.25 mJ
test("NAV 25kV -> 50A, E~=156.25mJ", () => {
  const { I } = computeIpico(STANDARDS.nav, 25);
  assert.equal(formatSig(I), "50");
  const E = computeEnergy(STANDARDS.nav, 25);
  const scaled = autoScaleEnergy(E);
  assert.equal(scaled.unit, "mJ");
  assert.equal(formatSig(scaled.value), "156.25");
});

// 4. Unidirecional sempre com V_CL (magnitude) menor que o bidirecional, para várias correntes
test("uni < bi sempre (varias correntes e polaridades)", () => {
  const VBR = TVS_DEFAULTS.VBR.value;
  const Rd = TVS_DEFAULTS.Rd.value;
  const VF = TVS_DEFAULTS.VF.value;
  const Rdf = TVS_DEFAULTS.Rdf.value;
  for (const I of [1, 30, 50, 93.75, 112.5]) {
    const uniPos = Math.abs(computeVCLUniPos(VBR, Rd, I));
    const uniNeg = Math.abs(computeVCLUniNeg(VF, Rdf, I));
    const bi = Math.abs(computeVCLBiMag(VBR, Rd, I));
    assert.ok(uniPos < bi, `uniPos(${uniPos}) < bi(${bi}) falhou para I=${I}`);
    assert.ok(uniNeg < bi, `uniNeg(${uniNeg}) < bi(${bi}) falhou para I=${I}`);
  }
});

// 5. Atenuação coerente: 20*log10(Vin/VCL), positiva quando Vin>>VCL
test("atenuacao positiva e coerente", () => {
  const { I, V_V } = computeIpico(STANDARDS.iec, 8);
  const VCL = computeVCLUniPos(TVS_DEFAULTS.VBR.value, TVS_DEFAULTS.Rd.value, I);
  const aten = computeAtenuacaoDB(V_V, VCL);
  assert.ok(aten > 0, "atenuacao deveria ser positiva");
  const expected = 20 * Math.log10(V_V / VCL);
  assert.equal(aten, expected);
});

console.log(`\n${passed} testes ok`);
