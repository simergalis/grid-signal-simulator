import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  CircleHelp,
  LockKeyhole,
  RotateCcw,
  Save,
  ShieldCheck,
  Zap,
} from "lucide-react";

type Tier = "Advisory" | "Supervised" | "Autonomous";
type Authority = "Autonomous" | "Confirm" | "Human only";

const sourceSeed = [
  { id: "BESS-001", type: "Battery energy storage", capacity: "20.0 MW", health: "Nominal", detail: "40 MWh usable · 95% SoC", authority: "Autonomous" as Authority, color: "mint" },
  { id: "GT-1", type: "Gas turbine", capacity: "10.0 MW", health: "Standby", detail: "Warm standby · 0.20 MW/s ramp", authority: "Confirm" as Authority, color: "amber" },
  { id: "Solar PV", type: "Solar generation", capacity: "5.0 MW rated", health: "Read-only", detail: "Dispatchable = false", authority: "Autonomous" as Authority, color: "sky" },
];

const touRows = [
  ["Peak", "12 pm – 6 pm", "$177.02"],
  ["Part-peak", "2–4 pm · 9–11 pm", "$142.27"],
  ["Off-peak", "All other hours", "$114.82"],
];

export function OperationalReadiness() {
  const [tier, setTier] = useState<Tier>("Supervised");
  const [month, setMonth] = useState("August");
  const [sources, setSources] = useState(sourceSeed);
  const [expanded, setExpanded] = useState<string[]>(["sources"]);
  const [step, setStep] = useState<"prepare" | "review">("prepare");
  const [saved, setSaved] = useState(false);
  const [latency, setLatency] = useState(30);
  const [operatorDecision, setOperatorDecision] = useState<"Approve" | "Reject">("Approve");
  const [budgets, setBudgets] = useState({ "Tenant North": "8.5", "Tenant South": "6.0", "Tenant West": "4.5" });

  const readiness = useMemo(() => {
    const checks = [
      tier !== "Autonomous",
      sources[0].authority === "Autonomous",
      sources[1].authority === "Confirm",
      Number(budgets["Tenant North"]) <= 10,
      latency <= 60,
    ];
    return Math.round((checks.filter(Boolean).length / checks.length) * 100);
  }, [tier, sources, budgets, latency]);

  const toggle = (key: string) =>
    setExpanded((items) => (items.includes(key) ? items.filter((item) => item !== key) : [...items, key]));

  const updateAuthority = (id: string, authority: Authority) =>
    setSources((items) => items.map((source) => (source.id === id ? { ...source, authority } : source)));

  const changeBudget = (key: string, value: string) => setBudgets((current) => ({ ...current, [key]: value }));

  return (
    <div className="pms-shell">
      <style>{`
        .pms-shell{min-height:100vh;background:#f5f7f4;color:#17312d;font-family:'DM Sans','Plus Jakarta Sans',ui-sans-serif,sans-serif;padding:22px;letter-spacing:-.01em}
        .pms-shell *{box-sizing:border-box}.pms-frame{max-width:1240px;margin:0 auto;background:#fbfcf9;border:1px solid #dbe5de;border-radius:22px;overflow:hidden;box-shadow:0 18px 55px rgba(39,71,61,.10)}
        .pms-topbar{height:76px;display:flex;align-items:center;justify-content:space-between;padding:0 30px;border-bottom:1px solid #e2eae4;background:#fff}
        .brand{display:flex;align-items:center;gap:11px}.brand-mark{width:32px;height:32px;border-radius:10px;background:#145e53;color:#d6f3df;display:grid;place-items:center}.brand-name{font-family:'Space Mono',monospace;font-size:12px;font-weight:700;letter-spacing:.08em}.brand-sub{font-size:11px;color:#82918a;margin-top:2px}
        .trust{display:flex;align-items:center;gap:8px;color:#3e6a5e;font-size:11px;background:#eff8f1;border:1px solid #cfe7d7;padding:8px 12px;border-radius:999px}.trust svg{width:14px}
        .pms-body{display:grid;grid-template-columns:300px minmax(0,1fr);min-height:700px}.rail{background:#edf4ef;padding:28px 22px;border-right:1px solid #dce8df}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:10px;font-weight:700;color:#668079}.rail h1{font-family:'Bricolage Grotesque','DM Sans',sans-serif;font-size:29px;line-height:1.03;letter-spacing:-.055em;margin:10px 0 10px;color:#123b34}.rail-copy{font-size:12px;color:#6a8178;line-height:1.55;margin-bottom:28px}
        .score{background:#fff;border:1px solid #d8e5dc;border-radius:17px;padding:17px;margin-bottom:26px}.score-head{display:flex;justify-content:space-between;align-items:center}.score-label{font-size:11px;font-weight:700;color:#557069}.score-value{font-family:'Space Mono',monospace;color:#136557;font-size:22px;font-weight:700}.score-track{height:7px;background:#e6eee8;border-radius:8px;margin:14px 0 9px;overflow:hidden}.score-fill{height:100%;background:#40a88b;border-radius:8px;transition:width .2s}.score-note{font-size:10px;color:#7d9089;line-height:1.4}
        .steps{display:grid;gap:4px}.step{display:flex;gap:11px;align-items:center;padding:11px 10px;border-radius:11px;color:#6f827a;font-size:12px;cursor:pointer}.step.active{background:#d8ebe0;color:#185a4e;font-weight:700}.step-num{width:22px;height:22px;display:grid;place-items:center;border:1px solid #bed5c8;border-radius:50%;font-size:10px}.step.active .step-num{background:#166657;color:#fff;border-color:#166657}.step-done{background:#4da183!important;color:#fff!important;border-color:#4da183!important}
        .workspace{padding:28px 32px 34px;background:#fbfcf9}.workspace-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:23px}.workspace h2{font-family:'Bricolage Grotesque',sans-serif;font-size:28px;letter-spacing:-.05em;margin:7px 0 6px;color:#153d36}.workspace-desc{font-size:12px;color:#72867d}.scenario-chip{border:1px solid #d5e3d9;background:#fff;border-radius:10px;padding:9px 12px;font-family:'Space Mono',monospace;font-size:10px;color:#5d756d;white-space:nowrap}.status-banner{display:flex;align-items:center;gap:15px;background:#fff;border:1px solid #cfe3d5;border-left:4px solid #43a687;border-radius:14px;padding:14px 16px;margin-bottom:21px}.status-icon{width:33px;height:33px;border-radius:10px;background:#def2e6;color:#27866b;display:grid;place-items:center;flex:none}.status-title{font-weight:700;font-size:13px}.status-copy{font-size:11px;color:#72867d;margin-top:3px}.status-action{margin-left:auto;color:#267a67;font-size:11px;font-weight:700;white-space:nowrap}
        .section{border:1px solid #dce7df;border-radius:15px;background:#fff;margin-bottom:12px;overflow:hidden}.section-head{display:flex;align-items:center;justify-content:space-between;padding:15px 17px;cursor:pointer}.section-title{display:flex;align-items:center;gap:11px}.section-number{font-family:'Space Mono',monospace;color:#97aaa2;font-size:10px}.section-name{font-size:13px;font-weight:700;color:#24483f}.section-summary{font-size:10px;color:#80918a;margin-top:2px}.section-chevron{color:#8ba098}.section-body{border-top:1px solid #edf1ed;padding:16px 17px}.field-label{font-size:10px;text-transform:uppercase;letter-spacing:.09em;font-weight:700;color:#80918a;margin-bottom:9px}.tier-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.tier{border:1px solid #dce7df;border-radius:11px;padding:12px;cursor:pointer;background:#fbfcfa}.tier.selected{border-color:#49a78b;background:#eff8f1;box-shadow:inset 0 0 0 1px #49a78b}.tier-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}.tier-name{font-size:12px;font-weight:700}.tier-dot{width:8px;height:8px;border-radius:50%;background:#c2d0c9}.selected .tier-dot{background:#3d9e82}.tier-desc{font-size:10px;color:#7d8e87;line-height:1.4}
        .row-inline{display:flex;align-items:center;justify-content:space-between;gap:18px}.select,.number{border:1px solid #ccdcd2;background:#f9fbf9;border-radius:8px;padding:9px 11px;color:#274e44;font:12px 'Space Mono',monospace;outline:none}.select{min-width:190px}.select:focus,.number:focus{border-color:#56a98e}.muted{font-size:11px;color:#7b8e85;line-height:1.45}.pill-row{display:flex;gap:6px;flex-wrap:wrap}.pill{border:1px solid #dae5de;background:#fafcfb;border-radius:7px;padding:7px 9px;color:#71837b;font-size:10px;cursor:pointer}.pill.active{border-color:#54a98e;background:#e8f5ed;color:#1d755f;font-weight:700}.source-list{display:grid;gap:9px}.source-row{display:grid;grid-template-columns:1fr 120px 190px;align-items:center;gap:14px;border:1px solid #e1eae3;border-radius:11px;padding:11px 12px}.source-name{font-family:'Space Mono',monospace;font-size:11px;font-weight:700}.source-type{font-size:10px;color:#83938c;margin-top:3px}.health{font-size:10px;display:flex;align-items:center;gap:5px;color:#347b65}.health-dot{width:6px;height:6px;border-radius:50%;background:#54af8d}.health.amber{color:#a47735}.health.amber .health-dot{background:#d5a246}.health.sky{color:#5d839b}.health.sky .health-dot{background:#79aeca}.authority{display:flex;gap:4px;justify-content:flex-end}.authority button{font:10px 'DM Sans',sans-serif;border:1px solid #dbe6df;border-radius:6px;padding:6px 7px;background:#fff;color:#75867f;cursor:pointer}.authority button.active{background:#e8f5ed;border-color:#54a98e;color:#1e755e;font-weight:700}
        .review-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.review-card{border:1px solid #e0e9e2;border-radius:11px;padding:14px;background:#fbfcfa}.review-card h4{font-size:11px;margin:0 0 11px;color:#47675d}.metric-line{display:flex;justify-content:space-between;font-size:11px;padding:7px 0;border-bottom:1px solid #edf1ed}.metric-line:last-child{border-bottom:0}.metric-line span:last-child{font-family:'Space Mono',monospace;color:#31594e;font-size:10px}.budget{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #edf1ed;padding:7px 0}.budget:last-child{border-bottom:0}.budget-name{font-size:11px}.budget-sub{font-size:10px;color:#8b9a94;margin-top:2px}.budget .number{width:70px;padding:6px 7px;text-align:right;font-size:10px}.footer{display:flex;align-items:center;justify-content:space-between;margin-top:22px;padding-top:17px;border-top:1px solid #dfe8e1}.boundary{display:flex;gap:8px;align-items:flex-start;font-size:10px;color:#70827a;max-width:420px;line-height:1.45}.boundary svg{color:#4d9b82;flex:none;margin-top:1px}.actions{display:flex;gap:8px}.btn{display:flex;align-items:center;gap:7px;border-radius:8px;padding:10px 13px;font:600 11px 'DM Sans',sans-serif;cursor:pointer}.btn-secondary{background:#fff;border:1px solid #d6e2da;color:#6b8077}.btn-primary{background:#146256;border:1px solid #146256;color:#fff;box-shadow:0 5px 12px rgba(20,98,86,.16)}.saved{color:#3e9479;font-size:11px;display:flex;gap:5px;align-items:center}
        @media(max-width:800px){.pms-shell{padding:0}.pms-frame{border-radius:0;border:0}.pms-body{grid-template-columns:1fr}.rail{border-right:0;border-bottom:1px solid #dce8df;padding:22px}.rail h1{font-size:25px}.score{margin-bottom:14px}.steps{grid-template-columns:repeat(2,1fr)}.workspace{padding:22px 17px}.pms-topbar{padding:0 17px}.trust{display:none}.workspace-head{display:block}.scenario-chip{display:inline-block;margin-top:12px}.source-row{grid-template-columns:1fr}.authority{justify-content:flex-start}.tier-grid,.review-grid{grid-template-columns:1fr}.footer{display:block}.actions{margin-top:15px}.status-action{display:none}}
      `}</style>
      <div className="pms-frame">
        <header className="pms-topbar">
          <div className="brand"><div className="brand-mark"><Zap size={17} /></div><div><div className="brand-name">GRIDSIGNAL</div><div className="brand-sub">Power management workspace</div></div></div>
          <div className="trust"><LockKeyhole size={14} /> Advisory boundary active · no southbound writes</div>
        </header>
        <div className="pms-body">
          <aside className="rail">
            <div className="eyebrow">Switchgear / PMS</div>
            <h1>Prepare the site to run.</h1>
            <p className="rail-copy">A guided readiness pass for <strong>demo-solar-peak</strong>. Review the operating guardrails before the simulator receives a scenario.</p>
            <div className="score">
              <div className="score-head"><span className="score-label">RUN READINESS</span><span className="score-value">{readiness}%</span></div>
              <div className="score-track"><div className="score-fill" style={{ width: `${readiness}%` }} /></div>
              <div className="score-note">{readiness >= 100 ? "All checks passed. Safe to save this configuration." : "One or more guardrails still need your attention."}</div>
            </div>
            <div className="eyebrow" style={{ marginBottom: 9 }}>Prepare · review · save</div>
            <div className="steps">
              <div className={`step ${step === "prepare" ? "active" : ""}`} onClick={() => setStep("prepare")}><span className={`step-num ${step === "review" ? "step-done" : ""}`}>{step === "review" ? <Check size={12} /> : "1"}</span>Configure guardrails</div>
              <div className={`step ${step === "review" ? "active" : ""}`} onClick={() => setStep("review")}><span className="step-num">2</span>Review impact</div>
            </div>
            <div style={{ marginTop: 28, fontSize: 10, color: "#82938c", lineHeight: 1.5 }}><CircleHelp size={13} style={{ verticalAlign: "middle", marginRight: 5 }} />Physical switching remains with the PMS and operator at all times.</div>
          </aside>
          <main className="workspace">
            <div className="workspace-head"><div><div className="eyebrow">Operational readiness</div><h2>{step === "prepare" ? "Make the next run legible." : "Review before you commit."}</h2><div className="workspace-desc">{step === "prepare" ? "Start with the few decisions that shape every dispatch advisory." : "Nothing is written southbound. Saving records this setup to the scenario only."}</div></div><div className="scenario-chip">SCENARIO / DEMO-SOLAR-PEAK</div></div>
            <div className="status-banner"><div className="status-icon">{readiness >= 100 ? <ShieldCheck size={18} /> : <AlertTriangle size={18} />}</div><div><div className="status-title">{readiness >= 100 ? "Ready for operator review" : "Configuration needs attention"}</div><div className="status-copy">{readiness >= 100 ? "The dispatch loop has a complete, bounded configuration." : "Resolve the highlighted checks, then move to the impact review."}</div></div><div className="status-action" onClick={() => setStep("review")}>Review impact <ArrowRight size={13} style={{ verticalAlign: "middle" }} /></div></div>
            <section className="section">
              <div className="section-head" onClick={() => toggle("mode")}><div className="section-title"><span className="section-number">01</span><div><div className="section-name">Operating mode</div><div className="section-summary">{tier} · responses within {latency}s</div></div></div><ChevronDown className="section-chevron" size={17} /></div>
              {expanded.includes("mode") && <div className="section-body"><div className="field-label">Site operating tier · ladder A</div><div className="tier-grid">{(["Advisory", "Supervised", "Autonomous"] as Tier[]).map((item) => <div key={item} className={`tier ${tier === item ? "selected" : ""}`} onClick={() => { setTier(item); setSaved(false); }}><div className="tier-top"><span className="tier-name">{item}</span><span className="tier-dot" /></div><div className="tier-desc">{item === "Advisory" ? "Every recommendation waits for human approval." : item === "Supervised" ? "Dispatches within pre-approved limits; deviations ask." : "No per-action approval required; bounded by site limits."}</div></div>)}</div><div style={{ display: "flex", gap: 20, alignItems: "flex-end", marginTop: 17, flexWrap: "wrap" }}><div><div className="field-label">Default operator latency</div><input className="number" type="number" value={latency} min={0} max={300} step={5} onChange={(e) => { setLatency(Number(e.target.value)); setSaved(false); }} /> <span className="muted">seconds</span></div><div><div className="field-label">Default response</div><div className="pill-row"><button className={`pill ${operatorDecision === "Approve" ? "active" : ""}`} onClick={() => setOperatorDecision("Approve")}>Approve</button><button className={`pill ${operatorDecision === "Reject" ? "active" : ""}`} onClick={() => setOperatorDecision("Reject")}>Reject</button></div></div></div></div>}
            </section>
            <section className="section">
              <div className="section-head" onClick={() => toggle("sources")}><div className="section-title"><span className="section-number">02</span><div><div className="section-name">Source coverage</div><div className="section-summary">2 dispatchable sources · Solar excluded from EDL ranking</div></div></div><ChevronDown className="section-chevron" size={17} /></div>
              {expanded.includes("sources") && <div className="section-body"><div className="source-list">{sources.map((source) => <div className="source-row" key={source.id}><div><div className="source-name">{source.id}</div><div className="source-type">{source.type} · {source.capacity}</div></div><div className={`health ${source.color === "amber" ? "amber" : source.color === "sky" ? "sky" : ""}`}><span className="health-dot" />{source.health}<span className="muted">· {source.detail}</span></div><div className="authority">{source.id === "Solar PV" ? <span className="pill active" style={{ cursor: "default" }}>Read-only / excluded</span> : (["Autonomous", "Confirm", "Human only"] as Authority[]).map((item) => <button className={source.authority === item ? "active" : ""} key={item} onClick={() => { updateAuthority(source.id, item); setSaved(false); }}>{item}</button>)}</div></div>)}</div></div>}
            </section>
            <section className="section">
              <div className="section-head" onClick={() => toggle("pricing")}><div className="section-title"><span className="section-number">03</span><div><div className="section-name">Pricing context</div><div className="section-summary">PG&amp;E B-20 · {month} ({month === "August" ? "Summer" : "Winter"}) · energy-only</div></div></div><ChevronDown className="section-chevron" size={17} /></div>
              {expanded.includes("pricing") && <div className="section-body"><div className="row-inline"><div><div className="field-label">TOU calendar month</div><div className="muted">Used by EconomicDispatchLoop for dispatch pricing.</div></div><select className="select" value={month} onChange={(e) => { setMonth(e.target.value); setSaved(false); }}><option>January</option><option>March</option><option>June</option><option>August</option><option>October</option><option>December</option></select></div><div className="review-card" style={{ marginTop: 14 }}><div className="row-inline" style={{ marginBottom: 6 }}><span className="field-label" style={{ margin: 0 }}>Summer reference rates</span><span className="muted">$/MWh</span></div>{touRows.map(([period, hours, rate]) => <div className="metric-line" key={period}><span>{period} <span className="muted">· {hours}</span></span><span>{rate}</span></div>)}<div className="metric-line"><span>BESS marginal cost</span><span>$38.00</span></div></div></div>}
            </section>
            <section className="section">
              <div className="section-head" onClick={() => toggle("limits")}><div className="section-title"><span className="section-number">04</span><div><div className="section-name">Run limits</div><div className="section-summary">Tenant budgets · playback 15-minute intervals</div></div></div><ChevronDown className="section-chevron" size={17} /></div>
              {expanded.includes("limits") && <div className="section-body"><div className="review-grid"><div className="review-card"><h4>Tenant power budgets</h4>{Object.entries(budgets).map(([key, value]) => <div className="budget" key={key}><div><div className="budget-name">{key}</div><div className="budget-sub">Ceiling · MW</div></div><input className="number" value={value} onChange={(e) => { changeBudget(key, e.target.value); setSaved(false); }} /></div>)}</div><div className="review-card"><h4>Playback parameters</h4><div className="metric-line"><span>Duration</span><span>2 h 00 m</span></div><div className="metric-line"><span>Interval</span><span>15 min</span></div><div className="metric-line"><span>Weather profile</span><span>Solar peak / clear</span></div></div></div></div>}
            </section>
            <div className="footer"><div className="boundary"><ShieldCheck size={14} /> GridSignal generates advisories only. It never issues southbound writes; the PMS and operator retain physical switching authority.</div><div className="actions">{saved && <span className="saved"><Check size={14} /> Saved to scenario</span>}<button className="btn btn-secondary" onClick={() => { setTier("Supervised"); setLatency(30); setSaved(false); }}><RotateCcw size={14} /> Reset changes</button><button className="btn btn-primary" onClick={() => { setStep("review"); setSaved(true); }}><Save size={14} /> Save to scenario</button></div></div>
          </main>
        </div>
      </div>
    </div>
  );
}