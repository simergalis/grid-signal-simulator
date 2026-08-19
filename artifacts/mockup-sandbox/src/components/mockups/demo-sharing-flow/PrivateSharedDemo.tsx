import { useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Clipboard,
  Cloud,
  Cpu,
  Gauge,
  LockKeyhole,
  Network,
  Play,
  RotateCcw,
  ShieldCheck,
  Users,
  Zap,
} from "lucide-react";

export function PrivateSharedDemo() {
  const [mode, setMode] = useState<"private" | "shared">("private");
  const [inviteCode, setInviteCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [started, setStarted] = useState(false);
  const [showPrevious, setShowPrevious] = useState(false);

  const copyCode = () => {
    navigator.clipboard?.writeText("SJ1-7K4Q");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <main className="gs-shell">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
        .gs-shell { min-height:100vh; color:#e7f0ee; background:#0b1718; font-family:'DM Sans',sans-serif; overflow:hidden; position:relative; }
        .gs-shell::before { content:""; position:absolute; inset:0; opacity:.15; pointer-events:none; background-image:linear-gradient(rgba(157,208,196,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(157,208,196,.07) 1px,transparent 1px); background-size:48px 48px; mask-image:linear-gradient(to bottom,black,transparent 80%); }
        .gs-shell::after { content:""; position:absolute; width:500px; height:500px; right:-170px; top:-230px; border-radius:50%; background:#16453e; filter:blur(90px); opacity:.46; pointer-events:none; }
        .gs-frame { position:relative; z-index:1; width:min(1160px,calc(100% - 48px)); min-height:100vh; margin:auto; display:flex; flex-direction:column; }
        .gs-topbar { height:76px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid rgba(178,211,202,.15); }
        .gs-brand { display:flex; align-items:center; gap:12px; letter-spacing:-.02em; font-family:'Space Grotesk',sans-serif; font-weight:600; }
        .gs-mark { width:30px; height:30px; border:1px solid #72dbbe; border-radius:8px; display:grid; place-items:center; color:#78e1c1; background:#11332f; box-shadow:0 0 24px rgba(75,222,180,.15); }
        .gs-mark svg { width:16px; }
        .gs-brand span { color:#78e1c1; }
        .gs-status { display:flex; align-items:center; gap:9px; font-size:12px; color:#9bb4b0; }
        .gs-status i { display:block; width:7px; height:7px; border-radius:50%; background:#74d9b8; box-shadow:0 0 0 4px rgba(116,217,184,.11); }
        .gs-content { flex:1; display:grid; grid-template-columns:1.03fr .97fr; align-items:center; gap:88px; padding:58px 0 64px; }
        .gs-eyebrow { display:flex; align-items:center; gap:10px; color:#75d9bb; font-size:11px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; margin-bottom:23px; }
        .gs-eyebrow b { width:28px; height:1px; background:#75d9bb; }
        h1 { font-family:'Space Grotesk',sans-serif; font-size:clamp(37px,4vw,58px); line-height:1.05; letter-spacing:-.055em; margin:0; max-width:580px; font-weight:600; }
        .gs-lede { color:#a7bcba; line-height:1.65; font-size:16px; max-width:500px; margin:22px 0 29px; }
        .gs-context { display:flex; align-items:center; gap:13px; color:#d4e4df; font-size:13px; padding-top:18px; border-top:1px solid rgba(178,211,202,.14); max-width:500px; }
        .gs-context .context-icon { width:33px;height:33px; display:grid;place-items:center; background:#163330;border:1px solid rgba(111,213,184,.24);border-radius:9px;color:#77ddbe; }
        .gs-context strong { font-weight:600; color:#e1ede9; display:block; margin-bottom:3px; }
        .gs-context small { color:#78918e; font-size:12px; }
        .gs-panel { background:rgba(18,38,38,.87); border:1px solid rgba(154,203,193,.2); border-radius:18px; padding:9px; box-shadow:0 24px 70px rgba(0,0,0,.25), inset 0 1px rgba(255,255,255,.035); }
        .gs-tabs { display:grid; grid-template-columns:1fr 1fr; gap:6px; padding:5px; background:#0d2222; border-radius:12px; }
        .gs-tab { border:0; background:transparent; color:#75918e; text-align:left; padding:13px 14px; border-radius:8px; font:600 13px 'DM Sans'; cursor:pointer; transition:all .2s ease; }
        .gs-tab.active { color:#ddf5ed; background:#1a3c39; box-shadow:inset 0 0 0 1px rgba(116,217,184,.22); }
        .gs-tab small { display:block; font-weight:400; color:#7faaa1; font-size:11px; margin-top:4px; }
        .gs-form { padding:28px 23px 22px; }
        .gs-form-title { display:flex; gap:13px; align-items:flex-start; margin-bottom:24px; }
        .gs-form-title .big-icon { width:38px;height:38px; flex:none; border-radius:11px; background:#d79a54; color:#182321; display:grid;place-items:center; }
        .gs-form-title .big-icon.shared { background:#83c9b7; }
        .gs-form-title h2 { font:600 19px 'Space Grotesk'; letter-spacing:-.025em; margin:0 0 5px; color:#eaf5f1; }
        .gs-form-title p { color:#87a5a0; font-size:12px; line-height:1.4; margin:0; }
        .gs-label { color:#bcd0cc; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.1em; display:block; margin-bottom:8px; }
        .gs-input-wrap { position:relative; }
        .gs-input { width:100%; box-sizing:border-box; background:#0e2424; border:1px solid #2d504c; border-radius:9px; color:#e9f6f1; height:48px; padding:0 45px 0 14px; outline:none; font:600 14px 'Space Grotesk'; letter-spacing:.14em; transition:border .2s; }
        .gs-input:focus { border-color:#79d6b9; box-shadow:0 0 0 3px rgba(121,214,185,.1); }
        .gs-input::placeholder { color:#57736e; letter-spacing:.04em; font-family:'DM Sans'; font-weight:400; }
        .gs-input-wrap .input-icon { position:absolute;right:15px;top:15px;color:#71918b;width:18px; }
        .gs-details { display:grid; grid-template-columns:1fr 1fr; gap:9px; margin:19px 0; }
        .gs-detail { background:#102b2a; border:1px solid rgba(140,196,184,.12); padding:12px; border-radius:9px; }
        .gs-detail span { color:#779691; font-size:10px; text-transform:uppercase; letter-spacing:.09em; display:block; margin-bottom:6px; }
        .gs-detail strong { color:#d7e8e3; font-size:12px; font-weight:600; }
        .gs-reassurance { display:flex; gap:10px; align-items:flex-start; padding:13px; background:rgba(215,154,84,.09); border:1px solid rgba(215,154,84,.21); border-radius:9px; color:#d9c3a7; font-size:11px; line-height:1.45; margin:4px 0 18px; }
        .gs-reassurance svg { color:#e3ac69; flex:none; margin-top:1px; }
        .gs-primary { width:100%; height:47px; border:0; border-radius:9px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:10px; background:#d79a54; color:#192421; font:700 13px 'DM Sans'; transition:transform .2s,background .2s; }
        .gs-primary:hover { transform:translateY(-2px); background:#edb16c; }
        .gs-primary.shared-action { background:#83c9b7; }
        .gs-primary.shared-action:hover { background:#9bdfcd; }
        .gs-footnote { text-align:center; color:#6e8d88; font-size:11px; margin:14px 0 0; }
        .gs-previous { margin:0 23px 17px; border-top:1px solid rgba(178,211,202,.12); padding-top:15px; }
        .gs-previous-toggle { width:100%; border:0; background:none; color:#92b6af; display:flex; align-items:center; justify-content:space-between; padding:0; cursor:pointer; font:600 12px 'DM Sans'; }
        .gs-previous-toggle svg { transition:transform .2s; } .gs-previous-toggle.open svg { transform:rotate(180deg); }
        .gs-last { margin-top:13px; background:#0d2524; border:1px solid rgba(143,199,187,.14); border-radius:8px; padding:11px 12px; display:flex; align-items:center; justify-content:space-between; }
        .gs-last strong { display:block; color:#d4e5e0; font-size:12px; margin-bottom:3px; }.gs-last small { color:#6f8d89; font-size:10px; }
        .gs-last button { border:0; background:none; color:#7ed9bd; font-size:11px; font-weight:700; cursor:pointer; }
        .gs-confirm { padding:24px 24px 27px; text-align:center; }.gs-confirm .success { width:50px;height:50px;border-radius:50%;display:grid;place-items:center;background:#1f5849;color:#8ae7c6;margin:0 auto 15px; }.gs-confirm h2 { font:600 22px 'Space Grotesk';margin:0 0 8px }.gs-confirm p { color:#94b2ad;font-size:13px;line-height:1.5;margin:0 auto 21px;max-width:285px }.gs-code { color:#e7c28e; font:700 18px 'Space Grotesk'; letter-spacing:.16em; background:#0d2725;border:1px dashed #6b634e;border-radius:8px;padding:13px;margin-bottom:18px;display:flex;justify-content:center;gap:10px;align-items:center }.gs-code button { border:0;background:none;color:#8dcabd;cursor:pointer;display:grid;place-items:center }.gs-reset { background:none;border:0;color:#8ab4ac;cursor:pointer;font:600 12px 'DM Sans';display:inline-flex;gap:7px;align-items:center; }.gs-reset:hover {color:#c8e5dc}\n+        @media (max-width: 800px) { .gs-frame{width:min(100% - 30px,560px)} .gs-content{grid-template-columns:1fr;gap:34px;padding:45px 0}.gs-content h1{font-size:42px}.gs-context{margin-bottom:5px}.gs-status{display:none} }\n+      `}</style>
      <div className="gs-frame">
        <header className="gs-topbar">
          <div className="gs-brand"><div className="gs-mark"><Network /></div><div>GridSignal <span>Simulator</span></div></div>
          <div className="gs-status"><i /> Demo environment ready</div>
        </header>
        <section className="gs-content">
          <div>
            <div className="gs-eyebrow"><b /> Welcome to your control room</div>
            <h1>Choose how you want to run this demo.</h1>
            <p className="gs-lede">Explore the SJ-1 GPU Colo Center with a private run, or step into a live session with your team. You’ll see exactly where you’re going before anything starts.</p>
            <div className="gs-context">
              <div className="context-icon"><Cpu size={17} /></div>
              <div><strong>SJ-1 GPU Colo Center</strong><small>30.0 MW facility demand · San Jose, California · Operations scenario</small></div>
            </div>
          </div>
          <div className="gs-panel">
            {started ? (
              <div className="gs-confirm">
                <div className="success"><Check size={25} /></div>
                <h2>{mode === "private" ? "Private demo is ready" : "You joined the shared demo"}</h2>
                <p>{mode === "private" ? "This run is separate from other people's demos. You can explore freely without changing anyone else's view." : "You're now viewing the live SJ-1 scenario with your team. Changes are visible to everyone in this session."}</p>
                {mode === "private" && <div className="gs-code">SJ1-7K4Q <button onClick={copyCode} aria-label="Copy invite code">{copied ? <Check size={16} /> : <Clipboard size={16} />}</button></div>}
                <button className="gs-reset" onClick={() => setStarted(false)}><RotateCcw size={14} /> Return to demo selection</button>
              </div>
            ) : (
              <>
                <div className="gs-tabs">
                  <button className={`gs-tab ${mode === "private" ? "active" : ""}`} onClick={() => setMode("private")}>Start a new demo<small>Private to this browser</small></button>
                  <button className={`gs-tab ${mode === "shared" ? "active" : ""}`} onClick={() => setMode("shared")}>Join a shared demo<small>Use an invite code</small></button>
                </div>
                <div className="gs-form">
                  <div className="gs-form-title">
                    <div className={`big-icon ${mode === "shared" ? "shared" : ""}`}>{mode === "private" ? <LockKeyhole size={19} /> : <Users size={20} />}</div>
                    <div><h2>{mode === "private" ? "Start a new demo" : "Join a shared demo"}</h2><p>{mode === "private" ? "A clean, private workspace for your walkthrough." : "Enter the invite code your teammate shared with you."}</p></div>
                  </div>
                  {mode === "shared" && <><label className="gs-label" htmlFor="invite">Invite code</label><div className="gs-input-wrap"><input id="invite" className="gs-input" value={inviteCode} onChange={e => setInviteCode(e.target.value.toUpperCase())} placeholder="e.g. SJ1-7K4Q" /><Zap className="input-icon" /></div></>}
                  <div className="gs-details">
                    <div className="gs-detail"><span>Scenario</span><strong>SJ-1 GPU Colo Center</strong></div>
                    <div className="gs-detail"><span>Starting state</span><strong><span style={{display:"inline",color:"#75d9bb",fontSize:12,letterSpacing:0,textTransform:"none"}}>●</span> Ready to run</strong></div>
                  </div>
                  {mode === "private" && <div className="gs-reassurance"><ShieldCheck size={16} /><div><strong style={{color:"#efd2a7"}}>Your new demo is separate.</strong><br />It will not open, change, or share state with other people’s demos in another browser.</div></div>}
                  <button className={`gs-primary ${mode === "shared" ? "shared-action" : ""}`} disabled={mode === "shared" && !inviteCode.trim()} onClick={() => setStarted(true)}>{mode === "private" ? <><Play size={16} fill="currentColor" /> Start private demo</> : <><ArrowRight size={17} /> Join shared demo</>}</button>
                  <p className="gs-footnote">{mode === "private" ? "You can invite others after the demo starts." : "Everyone in the shared demo sees the same live state."}</p>
                </div>
                <div className="gs-previous">
                  <button className={`gs-previous-toggle ${showPrevious ? "open" : ""}`} onClick={() => setShowPrevious(!showPrevious)}>Continue a previous demo <ChevronDown size={15} /></button>
                  {showPrevious && <div className="gs-last"><div><strong>SJ-1 · Load shifting review</strong><small>Last opened today at 09:42 · Private</small></div><button onClick={() => setStarted(true)}>Continue <ArrowRight size={13} /></button></div>}
                </div>
              </>
            )}
          </div>
        </section>
        <footer style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"0 0 24px",color:"#587673",fontSize:11}}>
          <span>GridSignal Operations Suite</span><span style={{display:"flex",gap:8,alignItems:"center"}}><Gauge size={13} /> Simulation state is local to this demo</span>
        </footer>
      </div>
    </main>
  );
}