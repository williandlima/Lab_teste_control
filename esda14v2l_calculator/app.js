import {
  STANDARDS,
  TVS_DEFAULTS,
  maxForStandardMethod,
  computeIpico,
  computeEnergy,
  computeVL,
  computeDIDTFromRiseTime,
  computeAtenuacaoDB,
  buildCombos,
  computeVCLForCombo,
  formatSig,
  autoScaleEnergy,
} from "./calc.js";

const $ = (id) => document.getElementById(id);

const els = {
  norma: $("norma"),
  metodoField: $("metodoField"),
  metodo: $("metodo"),
  metodoHint: $("metodoHint"),
  normaHint: $("normaHint"),
  tensao: $("tensao"),
  tensaoHint: $("tensaoHint"),
  polaridade: $("polaridade"),
  modo: $("modo"),
  VBR: $("VBR"),
  Rd: $("Rd"),
  VF: $("VF"),
  Rdf: $("Rdf"),
  L: $("L"),
  IPPM: $("IPPM"),
  riseTimeField: $("riseTimeField"),
  riseTime: $("riseTime"),
  didtManualField: $("didtManualField"),
  didtManual: $("didtManual"),
  outIpico: $("out-ipico"),
  formulaIpico: $("formula-ipico"),
  outEnergia: $("out-energia"),
  formulaEnergia: $("formula-energia"),
  vclCombos: $("vcl-combos"),
  outVL: $("out-vl"),
  formulaVL: $("formula-vl"),
  atenCombos: $("aten-combos"),
  comparisonTbody: document.querySelector("#comparisonTable tbody"),
  comparisonNote: $("comparisonNote"),
  engineeringNote: $("engineeringNote"),
};

function renderFormula(el, latex) {
  window.katex.render(latex, el, { throwOnError: false, displayMode: true });
}

const OHM = "\\Omega";
function unit(u) {
  return `\\,\\mathrm{${u}}`;
}

function polLabel(pol) {
  return pol === "pos" ? "+" : "−";
}
function modoLabel(modo) {
  return modo === "uni" ? "Unidirecional" : "Bidirecional";
}

function getDidtModeFromInputs() {
  return document.querySelector('input[name="didtMode"]:checked').value;
}

function updateNormaUI() {
  const standard = STANDARDS[els.norma.value];
  if (standard.methods) {
    els.metodoField.hidden = false;
    els.metodo.innerHTML = Object.entries(standard.methods)
      .map(([key, m]) => `<option value="${key}">${m.label} (até ${m.max} kV)</option>`)
      .join("");
    els.metodoHint.textContent =
      "A forma de onda por ar é, na prática, menos repetitiva: depende da velocidade de aproximação do eletrodo.";
  } else {
    els.metodoField.hidden = true;
    els.metodoHint.textContent = "";
  }
  const modelText =
    standard.model === "k"
      ? `dupla exponencial, k = ${standard.k} A/kV (Tabela 3, IEC 61000-4-2)`
      : `modelo RC puro, I = V/R (R = ${standard.R} Ω)`;
  els.normaHint.textContent = `Rede geradora: C = ${standard.C * 1e12} pF, R = ${standard.R} Ω — ${modelText}.`;
}

function currentMaxKV() {
  const standard = STANDARDS[els.norma.value];
  return maxForStandardMethod(standard, els.metodo.value);
}

function clampTensao() {
  const max = currentMaxKV();
  els.tensao.max = String(max);
  els.tensao.min = "0.1";
  let v = parseFloat(els.tensao.value);
  if (!Number.isFinite(v) || v <= 0) v = 0.1;
  if (v > max) v = max;
  els.tensao.value = String(v);
  els.tensaoHint.textContent = `Limite para esta norma/método: até ${formatSig(max)} kV.`;
}

function readParams() {
  return {
    VBR: parseFloat(els.VBR.value),
    Rd: parseFloat(els.Rd.value),
    VF: parseFloat(els.VF.value),
    Rdf: parseFloat(els.Rdf.value),
    L: parseFloat(els.L.value),
    IPPM: parseFloat(els.IPPM.value),
  };
}

function computeDIDT(I) {
  if (getDidtModeFromInputs() === "manual") {
    return parseFloat(els.didtManual.value);
  }
  const tr = parseFloat(els.riseTime.value);
  return computeDIDTFromRiseTime(I, tr);
}

function vclFormulaLatex(combo, params, I, VCL) {
  if (combo.modo === "uni" && combo.pol === "pos") {
    return `V_{CL}^{+} = V_{BR} + R_d \\cdot I = ${formatSig(params.VBR)}${unit("V")} + ${formatSig(
      params.Rd
    )}${unit(OHM)} \\times ${formatSig(I)}${unit("A")} = ${formatSig(VCL)}${unit("V")}`;
  }
  if (combo.modo === "uni" && combo.pol === "neg") {
    return `V_{CL}^{-} = -(V_F + R_{df} \\cdot I) = -(${formatSig(params.VF)}${unit("V")} + ${formatSig(
      params.Rdf
    )}${unit(OHM)} \\times ${formatSig(I)}${unit("A")}) = ${formatSig(VCL)}${unit("V")}`;
  }
  const sign = combo.pol === "pos" ? "+" : "-";
  return `V_{CL}^{${combo.pol === "pos" ? "+" : "-"}} = ${sign}(2V_{BR} + 2R_d \\cdot I) = ${sign}(2\\times ${formatSig(
    params.VBR
  )}${unit("V")} + 2\\times ${formatSig(params.Rd)}${unit(OHM)} \\times ${formatSig(I)}${unit(
    "A"
  )}) = ${formatSig(VCL)}${unit("V")}`;
}

function atenFormulaLatex(Vin_V, VCL, aten) {
  return `\\mathrm{Aten}_{dB} = 20\\log_{10}\\!\\left(\\frac{V_{in}}{|V_{CL}|}\\right) = 20\\log_{10}\\!\\left(\\frac{${formatSig(
    Vin_V
  )}${unit("V")}}{${formatSig(Math.abs(VCL))}${unit("V")}}\\right) = ${formatSig(aten)}${unit("dB")}`;
}

function recompute() {
  updateNormaUI();
  clampTensao();

  const standard = STANDARDS[els.norma.value];
  const V_kV = parseFloat(els.tensao.value);
  const params = readParams();

  // 1. Corrente de pico
  const { I, V_V } = computeIpico(standard, V_kV);
  els.outIpico.textContent = `${formatSig(I)} A`;
  const ipicoLatex =
    standard.model === "k"
      ? `I_{pico} = k \\cdot V = ${standard.k}${unit("A/kV")} \\times ${formatSig(V_kV)}${unit(
          "kV"
        )} = ${formatSig(I)}${unit("A")}`
      : `I_{pico} = \\dfrac{V}{R} = \\dfrac{${formatSig(V_V)}${unit("V")}}{${standard.R}${unit(
          OHM
        )}} = ${formatSig(I)}${unit("A")}`;
  renderFormula(els.formulaIpico, ipicoLatex);

  // 2. Energia do gerador
  const E = computeEnergy(standard, V_kV);
  const scaled = autoScaleEnergy(E);
  els.outEnergia.textContent = `${formatSig(scaled.value)} ${scaled.unit}`;
  const energiaLatex = `E = \\tfrac12 C V^2 = \\tfrac12 \\times ${formatSig(
    standard.C * 1e12
  )}${unit("pF")} \\times (${formatSig(V_V)}${unit("V")})^2 = ${formatSig(scaled.value)}${unit(
    scaled.unit
  )}`;
  renderFormula(els.formulaEnergia, energiaLatex);

  // 3. V_CL para os combos selecionados (modo x polaridade)
  const combos = buildCombos(els.modo.value, els.polaridade.value);
  els.vclCombos.innerHTML = "";
  els.atenCombos.innerHTML = "";
  combos.forEach((combo) => {
    const VCL = computeVCLForCombo(combo, params, I);
    const aten = computeAtenuacaoDB(V_V, VCL);

    const vclBlock = document.createElement("div");
    vclBlock.className = "combo-block";
    vclBlock.innerHTML = `<div class="combo-label">${modoLabel(combo.modo)} · polaridade ${polLabel(
      combo.pol
    )}</div><div class="result-value">${formatSig(VCL)} V</div><div class="formula"></div>`;
    els.vclCombos.appendChild(vclBlock);
    renderFormula(vclBlock.querySelector(".formula"), vclFormulaLatex(combo, params, I, VCL));

    const atenBlock = document.createElement("div");
    atenBlock.className = "combo-block";
    atenBlock.innerHTML = `<div class="combo-label">${modoLabel(combo.modo)} · polaridade ${polLabel(
      combo.pol
    )}</div><div class="result-value">${formatSig(aten)} dB</div><div class="formula"></div>`;
    els.atenCombos.appendChild(atenBlock);
    renderFormula(atenBlock.querySelector(".formula"), atenFormulaLatex(V_V, VCL, aten));
  });

  // 4. Termo indutivo V_L
  const dIdt = computeDIDT(I);
  const VL = computeVL(params.L, dIdt);
  els.outVL.textContent = `${formatSig(VL)} V`;
  const vlLatex = `V_L = L \\cdot \\dfrac{dI}{dt} = ${formatSig(params.L)}${unit("nH")} \\times ${formatSig(
    dIdt
  )}${unit("A/ns")} = ${formatSig(VL)}${unit("V")}`;
  renderFormula(els.formulaVL, vlLatex);

  // 5. Comparação Unidirecional x Bidirecional (sempre, no rodapé)
  const cmpPols = els.polaridade.value === "both" ? ["pos", "neg"] : [els.polaridade.value];
  els.comparisonTbody.innerHTML = "";
  let anyUniLess = true;
  cmpPols.forEach((pol) => {
    const uniCombo = { modo: "uni", pol };
    const biCombo = { modo: "bi", pol };
    const VCLuni = computeVCLForCombo(uniCombo, params, I);
    const VCLbi = computeVCLForCombo(biCombo, params, I);
    const atenUni = computeAtenuacaoDB(V_V, VCLuni);
    const atenBi = computeAtenuacaoDB(V_V, VCLbi);
    if (Math.abs(VCLuni) >= Math.abs(VCLbi)) anyUniLess = false;

    [
      ["Unidirecional", VCLuni, atenUni],
      ["Bidirecional", VCLbi, atenBi],
    ].forEach(([label, vcl, aten]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${polLabel(pol)}</td><td>${label}</td><td>${formatSig(vcl)}</td><td>${formatSig(
        aten
      )}</td>`;
      els.comparisonTbody.appendChild(tr);
    });
  });
  els.comparisonNote.textContent = anyUniLess
    ? "Confirmado: o modo Unidirecional clampa em tensão residual menor (maior atenuação) que o Bidirecional, pois usa uma única célula referenciada à carcaça em vez de duas em série."
    : "Atenção: combinação de parâmetros não usuais — verifique os valores de V_BR/R_d/V_F/R_df inseridos.";

  // 6. Leitura de engenharia automática
  const ratio = I / params.IPPM;
  const regimeNote =
    "As formas de onda 8/20 µs (datasheet) e ESD (subida ~1 ns) são regimes diferentes — esta comparação de corrente de pico é apenas indicativa.";
  if (ratio > 1) {
    els.engineeringNote.classList.add("warn");
    els.engineeringNote.textContent = `Aviso: I_pico (${formatSig(I)} A) excede a especificação de catálogo I_PPM (${formatSig(
      params.IPPM
    )} A) em ${formatSig(ratio)}× — em qualquer modo do pino 3, a solicitação de pico está acima da especificação do componente. ${regimeNote}`;
  } else {
    els.engineeringNote.classList.remove("warn");
    els.engineeringNote.textContent = `I_pico (${formatSig(I)} A) está dentro da especificação de catálogo I_PPM (${formatSig(
      params.IPPM
    )} A), razão ${formatSig(ratio)}×. ${regimeNote}`;
  }
}

function updateDidtModeUI() {
  const mode = getDidtModeFromInputs();
  els.riseTimeField.hidden = mode !== "risetime";
  els.didtManualField.hidden = mode !== "manual";
}

function onNormaChange() {
  updateNormaUI();
  recompute();
}

[
  els.tensao,
  els.polaridade,
  els.modo,
  els.VBR,
  els.Rd,
  els.VF,
  els.Rdf,
  els.L,
  els.IPPM,
  els.riseTime,
  els.didtManual,
].forEach((el) => el.addEventListener("input", recompute));

els.metodo.addEventListener("change", recompute);
els.norma.addEventListener("change", onNormaChange);
document.querySelectorAll('input[name="didtMode"]').forEach((el) =>
  el.addEventListener("change", () => {
    updateDidtModeUI();
    recompute();
  })
);

updateNormaUI();
updateDidtModeUI();
recompute();
