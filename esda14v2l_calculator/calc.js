// Núcleo de cálculo da calculadora ESDA14V2L — sem dependências de DOM,
// para poder ser testado isoladamente (Node) e usado pela UI (navegador).

export const STANDARDS = {
  iec: {
    label: "IEC 61000-4-2:2008",
    C: 150e-12,
    R: 330,
    model: "k",
    k: 3.75,
    methods: { contact: { max: 8, label: "Contato" }, air: { max: 15, label: "Ar" } },
  },
  cs118: {
    label: "MIL-STD-461G CS118",
    C: 150e-12,
    R: 330,
    model: "k",
    k: 3.75,
    methods: { contact: { max: 8, label: "Contato" }, air: { max: 15, label: "Ar" } },
  },
  hbm: {
    label: "JEDEC JESD22-A114F (HBM)",
    C: 100e-12,
    R: 1500,
    model: "rc",
    methods: null,
    singleMax: 8,
  },
  nav: {
    label: "NAV 25 kV (interna)",
    C: 500e-12,
    R: 500,
    model: "rc",
    methods: { contact: { max: 25, label: "Contato" }, air: { max: 25, label: "Ar" } },
  },
  st30: {
    label: "ST ESDA14V2L 30 kV",
    C: 150e-12,
    R: 330,
    model: "k",
    k: 3.75,
    methods: { contact: { max: 30, label: "Contato" }, air: { max: 30, label: "Ar" } },
  },
};

// Parâmetros oficiais do ESDA14V2L (datasheet ST DocID7058 Rev 5).
export const TVS_DEFAULTS = {
  VBR: { value: 15, source: "fonte" }, // V (nominal; faixa 14,2-15,8 @ I_R=1mA)
  Rd: { value: 0.65, source: "fonte" }, // Ω
  VF: { value: 1.25, source: "fonte" }, // V
  Rdf: { value: 0.5, source: "aconf" }, // Ω
  L: { value: 1.5, source: "aconf" }, // nH
  IPPM: { value: 14, source: "fonte" }, // A (8/20 µs)
};

export function maxForStandardMethod(standard, method) {
  if (!standard.methods) return standard.singleMax;
  const m = standard.methods[method] || Object.values(standard.methods)[0];
  return m.max;
}

export function computeIpico(standard, V_kV) {
  const V_V = V_kV * 1000;
  if (standard.model === "k") {
    return { I: standard.k * V_kV, V_V, model: "k" };
  }
  return { I: V_V / standard.R, V_V, model: "rc" };
}

export function computeEnergy(standard, V_kV) {
  const V_V = V_kV * 1000;
  return 0.5 * standard.C * V_V * V_V; // Joules
}

export function computeVCLUniPos(VBR, Rd, I) {
  return VBR + Rd * I;
}

export function computeVCLUniNeg(VF, Rdf, I) {
  return -(VF + Rdf * I);
}

export function computeVCLBiMag(VBR, Rd, I) {
  return 2 * VBR + 2 * Rd * I;
}

export function computeVL(L_nH, dIdt_A_per_ns) {
  return L_nH * dIdt_A_per_ns; // Volts (nH * A/ns = V)
}

export function computeDIDTFromRiseTime(I_A, riseTime_ns) {
  return I_A / riseTime_ns; // A/ns
}

export function computeAtenuacaoDB(Vin_V, VCL_V) {
  return 20 * Math.log10(Vin_V / Math.abs(VCL_V));
}

export function buildCombos(modo, polaridade) {
  const modos = modo === "cmp" ? ["uni", "bi"] : [modo];
  const pols = polaridade === "both" ? ["pos", "neg"] : [polaridade];
  const combos = [];
  for (const m of modos) {
    for (const p of pols) {
      combos.push({ modo: m, pol: p });
    }
  }
  return combos;
}

export function computeVCLForCombo(combo, params, I) {
  if (combo.modo === "uni") {
    if (combo.pol === "pos") {
      return computeVCLUniPos(params.VBR, params.Rd, I);
    }
    return computeVCLUniNeg(params.VF, params.Rdf, I);
  }
  const mag = computeVCLBiMag(params.VBR, params.Rd, I);
  return combo.pol === "pos" ? mag : -mag;
}

export function formatSig(x, sig = 5) {
  if (x === 0) return "0";
  const sign = x < 0 ? "-" : "";
  const ax = Math.abs(x);
  let s = ax.toPrecision(sig);
  if (s.indexOf("e") === -1) {
    if (s.indexOf(".") !== -1) {
      s = s.replace(/0+$/, "").replace(/\.$/, "");
    }
  } else {
    let [mant, exp] = s.split("e");
    if (mant.indexOf(".") !== -1) {
      mant = mant.replace(/0+$/, "").replace(/\.$/, "");
    }
    s = mant + "e" + exp;
  }
  return sign + s;
}

export function autoScaleEnergy(joules) {
  const ranges = [
    [1, "J", 1],
    [1e-3, "mJ", 1e3],
    [1e-6, "µJ", 1e6],
    [1e-9, "nJ", 1e9],
  ];
  const aj = Math.abs(joules);
  for (const [thresh, unit, mult] of ranges) {
    if (aj >= thresh) return { value: joules * mult, unit };
  }
  return { value: joules * 1e9, unit: "nJ" };
}
