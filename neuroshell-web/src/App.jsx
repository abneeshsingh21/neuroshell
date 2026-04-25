import React, { useState, useRef, useEffect, useCallback } from 'react';
import { TerminalSquare, Activity, Shield, HelpCircle, Settings, Play, Server, HardDrive, Cpu, Zap, Box, Send, Radio, Command, ArrowRight, Terminal, Search, FileCode2, Maximize, Clock, LogOut, RotateCcw, Network } from 'lucide-react';
import TerminalComponent from './components/TerminalComponent';

function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [shell, setShell] = useState('PowerShell');
  const [mode, setMode] = useState('Builder');
  const [swarmMode, setSwarmMode] = useState(false);
  const [input, setInput] = useState('');
  
  const terminalRef = useRef(null);
  const agentFeedRef = useRef(null);
  const deployFeedRef = useRef(null);

  const [agentLogs, setAgentLogs] = useState([{ time: new Date().toLocaleTimeString(), msg: "agent feed online", type: "system" }]);
  const [telemetry, setTelemetry] = useState({ latency: "8ms", reliability: "100%", throughput: "12/min" });

  // Command History tracking
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // System Monitor (HUD)
  const [sysmon, setSysmon] = useState({ cpu: 0, mem: 0, disk: 0, procs: [] });

  // Command Palette & Modals
  const [showPalette, setShowPalette] = useState(false);
  const [paletteSearch, setPaletteSearch] = useState("");
  const [showMonitor, setShowMonitor] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [dashData, setDashData] = useState(null);

  // Themes
  const THEMES = ['dark', 'ocean', 'matrix', 'light'];
  const [theme, setTheme] = useState('dark');
  const cycleTheme = () => {
    const nextTheme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
  };

  const PALETTE_COMMANDS = [
    { label: "Beginner Guide", cmd: "help" },
    { label: "System Dashboard", cmd: "dashboard" },
    { label: "Clear Terminal", cmd: "clear" },
    { label: "Fix Last Error", cmd: "fix" },
    { label: "Policy Snapshot", cmd: "policy" },
    { label: "Deploy Status", cmd: "deploy status" },
    { label: "Smart Suggestions", cmd: "suggest" },
    { label: "Search History", cmd: "history" }
  ];

  // Global Keybindings
  useEffect(() => {
    const handleGlobalKey = (e) => {
      // Ctrl+Shift+P
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        setShowPalette(p => {
          if (!p) setPaletteSearch("");
          return true;
        });
      }
      if (e.key === 'Escape') {
        setShowPalette(false);
        setShowMonitor(false);
        setShowDashboard(false);
      }
    };
    window.addEventListener('keydown', handleGlobalKey);
    return () => window.removeEventListener('keydown', handleGlobalKey);
  }, []);

  // Connect Telemetry Socket
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/telemetry');
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const timeStr = new Date().toLocaleTimeString();
        
        if (data.type === 'swarm_update') {
          setAgentLogs(prev => [...prev, { time: timeStr, msg: data.payload, type: "swarm" }]);
        } else if (data.type === 'gc_update') {
          setAgentLogs(prev => [...prev, { time: timeStr, msg: data.payload, type: "gc" }]);
        }
      } catch (e) {
        console.error("Telemetry parse error", e);
      }
    };
    return () => ws.close();
  }, []);

  // Connect Sysmon Socket
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/sysmon');
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setSysmon({
          cpu: data.cpu || 0,
          mem: data.mem || 0,
          disk: data.disk || 0,
          procs: data.procs || []
        });
      } catch (e) {}
    };
    return () => ws.close();
  }, []);

  // Fetch Dashboard API data
  useEffect(() => {
    if (showDashboard) {
       fetch('http://localhost:8000/api/dashboard')
         .then(res => res.json())
         .then(setDashData)
         .catch(console.error);
    }
  }, [showDashboard, history.length]);

  // Auto-scroll Agent Feed
  useEffect(() => {
    if (agentFeedRef.current) {
      agentFeedRef.current.scrollTop = agentFeedRef.current.scrollHeight;
    }
  }, [agentLogs]);

  const handleSend = () => {
    if (!input.trim()) return;
    
    // Command interception mapping
    let finalCommand = input.trim();
    if (finalCommand.toLowerCase() === 'show help') finalCommand = 'help';
    if (finalCommand.toLowerCase() === 'clear screen') finalCommand = 'clear';
    if (finalCommand.toLowerCase() === 'show dashboard') setShowDashboard(true);
    if (finalCommand.toLowerCase() === 'toggle theme') cycleTheme();
    
    // Semantic mappings for raw short-hand texts that cause AI translator ambiguity
    if (finalCommand.toLowerCase() === 'github') finalCommand = 'git status && git log -n 3';
    if (finalCommand.toLowerCase() === 'audit') finalCommand = 'run security audit';
    if (finalCommand.toLowerCase() === 'drift') finalCommand = 'check deployment drift';
    if (finalCommand.toLowerCase() === 'deploy') finalCommand = 'deploy status';

    terminalRef.current?.sendCommand(finalCommand);
    
    // Update history tracker
    setHistory(prev => [...prev, finalCommand]);
    setHistoryIndex(-1);
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSend();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length > 0) {
        const nextIdx = historyIndex === -1 ? history.length - 1 : Math.max(0, historyIndex - 1);
        setHistoryIndex(nextIdx);
        setInput(history[nextIdx]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex !== -1) {
        const nextIdx = historyIndex + 1;
        if (nextIdx >= history.length) {
          setHistoryIndex(-1);
          setInput('');
        } else {
          setHistoryIndex(nextIdx);
          setInput(history[nextIdx]);
        }
      }
    }
  };

  const fireCommand = (cmd) => {
    if (cmd === 'show dashboard') setShowDashboard(true);
    else if (cmd === 'toggle theme') cycleTheme();
    else if (terminalRef.current) {
      terminalRef.current.sendCommand(cmd);
    }
  };

  const toggleSwarm = (enabled) => {
    setSwarmMode(enabled);
    if (terminalRef.current) {
      terminalRef.current.sendConfig({ force_swarm: enabled });
    }
  };

  const executePaletteCmd = (cmd) => {
    setShowPalette(false);
    fireCommand(cmd);
    setHistory(prev => [...prev, cmd]);
  };

  return (
    <div className="flex flex-col h-screen w-full theme-bg text-[var(--text-main)] overflow-hidden font-sans relative">
      
      {/* Command Palette Overlay */}
      {showPalette && (
        <div 
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm"
          onClick={() => setShowPalette(false)}
        >
          <div 
            className="w-full max-w-2xl bg-[#161b22] border border-[#30363d] rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-100"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-3 border-b border-[#30363d] flex items-center gap-3">
              <Command size={18} className="text-gray-400" />
              <input 
                 autoFocus
                 type="text" 
                 placeholder="> Type a command to run..."
                 className="flex-1 bg-transparent border-none outline-none text-white text-lg placeholder-gray-500 font-mono"
                 value={paletteSearch}
                 onChange={(e) => setPaletteSearch(e.target.value)}
                 onKeyDown={(e) => {
                   if (e.key === 'Enter') {
                      const filtered = PALETTE_COMMANDS.filter(c => c.label.toLowerCase().includes(paletteSearch.toLowerCase()));
                      if (filtered.length > 0) {
                         executePaletteCmd(filtered[0].cmd);
                      }
                   }
                   if (e.key === 'Escape') {
                      setShowPalette(false);
                   }
                 }}
              />
            </div>
            <div className="max-h-[350px] overflow-y-auto p-2">
              {PALETTE_COMMANDS.filter(c => c.label.toLowerCase().includes(paletteSearch.toLowerCase())).length === 0 ? (
                <div className="p-4 text-center text-gray-500">No matching commands found.</div>
              ) : (
                PALETTE_COMMANDS.filter(c => c.label.toLowerCase().includes(paletteSearch.toLowerCase())).map((c, i) => (
                  <button
                    key={i}
                    className="w-full text-left px-4 py-3 rounded-lg text-gray-300 hover:bg-[#21262d] hover:text-white flex items-center justify-between group transition-colors"
                    onClick={() => executePaletteCmd(c.cmd)}
                  >
                    <span className="font-medium">{c.label}</span>
                    <span className="text-xs font-mono text-cyan-500 opacity-0 group-hover:opacity-100 transition-opacity flex items-center">
                      Execute {c.cmd} <ArrowRight size={14} className="ml-2" />
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* System Process Monitor Modal */}
      {showMonitor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowMonitor(false)}>
           <div className="w-[600px] bg-[#0d1117] border border-[#30363d] rounded-xl shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/10">
                 <div className="flex items-center gap-2 text-sm font-medium"><Server size={14} className="text-[#38bdf8]"/> Process Monitor</div>
                 <button onClick={() => setShowMonitor(false)} className="text-gray-400 hover:text-white">&times;</button>
              </div>
              <div className="p-6 overflow-y-auto max-h-[70vh]">
                 <h2 className="text-center text-[#00ff41] text-xl font-bold mb-6">System Process Monitor</h2>
                 <div className="bg-[#161b22] rounded-xl p-5 space-y-5 border border-white/5">
                    <div>
                      <div className="flex justify-between text-xs text-[#00ff41] mb-1"><span>CPU: {sysmon.cpu.toFixed(1)}%</span></div>
                      <div className="w-full bg-[#2a2a2a] h-2 rounded-full overflow-hidden"><div className="bg-[#00ff41] h-full transition-all" style={{width: `${sysmon.cpu}%`}}></div></div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs text-[#38bdf8] mb-1"><span>RAM: {sysmon.mem.toFixed(1)}%</span></div>
                      <div className="w-full bg-[#2a2a2a] h-2 rounded-full overflow-hidden"><div className="bg-[#38bdf8] h-full transition-all" style={{width: `${sysmon.mem}%`}}></div></div>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs text-orange-400 mb-1"><span>Disk: {sysmon.disk.toFixed(1)}%</span></div>
                      <div className="w-full bg-[#2a2a2a] h-2 rounded-full overflow-hidden"><div className="bg-orange-400 h-full transition-all" style={{width: `${sysmon.disk}%`}}></div></div>
                    </div>
                 </div>
                 
                 <div className="mt-6 px-1">
                    <div className="grid grid-cols-12 text-xs text-[#00ff41] uppercase font-mono tracking-wider border-b border-[#00ff41]/30 pb-2 mb-2">
                       <div className="col-span-2">PID</div>
                       <div className="col-span-6">Name</div>
                       <div className="col-span-2 text-right">CPU%</div>
                       <div className="col-span-2 text-right">MEM%</div>
                    </div>
                    <div className="space-y-1">
                       {sysmon.procs?.map(p => (
                         <div key={p.pid} className="grid grid-cols-12 text-xs text-[#00ff41] font-mono hover:bg-white/5 py-1 px-1 rounded">
                           <div className="col-span-2">{p.pid}</div>
                           <div className="col-span-6 truncate pr-2">{p.name || '?'}</div>
                           <div className="col-span-2 text-right">{p.cpu.toFixed(1)}</div>
                           <div className="col-span-2 text-right">{p.mem.toFixed(1)}</div>
                         </div>
                       ))}
                    </div>
                 </div>
              </div>
           </div>
        </div>
      )}

      {/* Dashboard Modal */}
      {showDashboard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md" onClick={() => setShowDashboard(false)}>
           <div className="w-[700px] bg-[#0a0a0a] border border-[#222] rounded-xl shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-4 py-2 bg-[#111] border-b border-[#222]">
                 <div className="flex items-center gap-2 text-sm font-medium"><Activity size={14} className="text-[#38bdf8]"/> NeuroShell Dashboard</div>
                 <button onClick={() => setShowDashboard(false)} className="text-gray-400 hover:text-white">&times;</button>
              </div>
              <div className="p-8 overflow-y-auto max-h-[80vh]">
                 <div className="text-center mb-10">
                   <h1 className="text-3xl font-bold text-[#00ff41] flex items-center justify-center gap-3"><Terminal size={28}/> NeuroShell</h1>
                   <p className="text-gray-500 mt-1">Dashboard</p>
                 </div>
                 
                 <div className="grid grid-cols-2 gap-4 mb-6">
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><Server size={14}/> Session</div>
                       <div className="text-[#00ff41] font-mono text-lg">{dashData?.session_id || 'WS-Active'}</div>
                    </div>
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><Terminal size={14}/> Commands</div>
                       <div className="text-[#00ff41] font-mono text-lg">{dashData?.commands || history.length}</div>
                    </div>
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><Box size={14}/> Shell</div>
                       <div className="text-[#00ff41] font-mono text-lg">{dashData?.shell || 'Powershell'}</div>
                    </div>
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><HardDrive size={14}/> CWD</div>
                       <div className="text-[#00ff41] font-mono text-sm truncate">{dashData?.cwd || '~'}</div>
                    </div>
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><Clock size={14}/> Uptime</div>
                       <div className="text-[#00ff41] font-mono text-lg">{dashData?.uptime || 'Active'}</div>
                    </div>
                    <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                       <div className="text-gray-500 text-sm mb-3 flex items-center gap-2"><FileCode2 size={14}/> History</div>
                       <div className="text-[#00ff41] font-mono text-lg">{history.length} commands</div>
                    </div>
                 </div>

                 <div className="bg-[#111] border border-[#222] rounded-xl p-5">
                    <div className="flex justify-between text-xs text-[#00ff41] mb-2"><span>CPU: {sysmon.cpu.toFixed(1)}%</span></div>
                    <div className="w-full bg-[#2a2a2a] h-1.5 rounded-full overflow-hidden"><div className="bg-[#00ff41] h-full transition-all" style={{width: `${sysmon.cpu}%`}}></div></div>
                 </div>
              </div>
           </div>
        </div>
      )}

      {/* 1. TOP HEADER ACTION BAR */}
      <header className={`h-[65px] theme-glass border-b theme-border flex items-center justify-between px-6 shrink-0 shadow-lg relative z-20 transition-all duration-300 ${(showPalette || showMonitor || showDashboard) ? 'blur-sm scale-[0.99] opacity-80' : ''}`}>
        
        {/* Left: Branding & Shell Toggles */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
             <div className="h-8 w-8 rounded bg-gradient-to-br from-[#00ff41] to-[#38bdf8] flex items-center justify-center shadow-[0_0_15px_rgba(0,255,65,0.3)] border border-white/20 relative group">
                <TerminalSquare size={16} className="text-[#0d1117]" />
             </div>
             <div>
               <h1 className="font-bold text-[15px] tracking-wide flex items-center gap-2 text-white">
                 NeuroShell
                 <span className="px-1.5 py-0.5 rounded text-[9px] font-black bg-[#2e0916] text-[#ff0055] border border-[#ff0055]/30 uppercase tracking-widest hidden sm:inline-block">Web</span>
               </h1>
               <p className="text-[10px] text-gray-400 font-mono tracking-widest uppercase">Deepmind // V5.2</p>
             </div>
          </div>

          <div className="h-4 w-px bg-white/10"></div>

          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-black/40 backdrop-blur-md border border-white/5 shadow-inner">
            <ToggleButton active={shell === 'PowerShell'} onClick={() => setShell('PowerShell')} label="PowerShell" />
            <ToggleButton active={shell === 'CMD'} onClick={() => setShell('CMD')} label="CMD" />
          </div>

          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-black/40 backdrop-blur-md border border-white/5 shadow-inner">
            <ToggleButton active={mode === 'Builder'} onClick={() => setMode('Builder')} label="Builder" color="cyan" />
            <ToggleButton active={mode === 'Ops'} onClick={() => setMode('Ops')} label="Ops" />
            <ToggleButton active={mode === 'Guided'} onClick={() => setMode('Guided')} label="Guided" color="green" />
            <ToggleButton active={mode === 'Expert'} onClick={() => setMode('Expert')} label="Expert" />
          </div>

          <div className="h-4 w-px bg-white/10"></div>
          
          {/* Swarm Mode Toggle - Parity Feature */}
          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-gradient-to-r from-black/60 to-black/40 backdrop-blur-md border border-[#8b5cf6]/30 shadow-[inset_0_0_10px_rgba(139,92,246,0.1)]">
            <ToggleButton active={!swarmMode} onClick={() => toggleSwarm(false)} label="Fast LLM" color="cyan" />
            <ToggleButton active={swarmMode} onClick={() => toggleSwarm(true)} label="Swarm (Deep)" color="accent" />
          </div>
        </div>

        {/* Center/Right: Metrics & Actions */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-4 text-xs font-mono font-medium drop-shadow-md">
            <span className="text-[#38bdf8] flex items-center gap-1"><Activity size={12}/> {telemetry.latency}</span>
            <span className="text-[#3fb950] flex items-center gap-1"><Shield size={12}/> {telemetry.reliability}</span>
            <span className="text-[#d29922] flex items-center gap-1"><Zap size={12}/> {telemetry.throughput}</span>
          </div>

          <div className="h-4 w-px bg-white/10"></div>

          <div className="flex theme-glass rounded-lg p-1 border theme-border">
            <button onClick={() => setShowDashboard(true)} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2">
              <Activity size={12} /> Dash
            </button>
            <button onClick={() => setShowPalette(true)} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2">
              <Search size={12} /> Search
            </button>
            <button onClick={() => setShowMonitor(true)} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2">
              <Server size={12} /> Monitor
            </button>
            <button onClick={cycleTheme} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2 group relative">
              <Settings size={12} /> Theme
              <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 bg-black text-white px-2 py-1 rounded text-[10px] opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity">
                {theme.toUpperCase()}
              </span>
            </button>
            <button onClick={() => terminalRef.current?.clear()} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2">
              <Terminal size={12} /> Clear
            </button>
            <button onClick={() => document.documentElement.requestFullscreen()} className="px-4 py-1.5 text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-md transition-all flex items-center gap-2">
              <Maximize size={12} /> Full
            </button>
          </div>
        </div>
      </header>

      {/* THREE COLUMN WORKSPACE */}
      <div className="flex-1 overflow-hidden flex relative z-10 p-4 gap-4">
        
        {/* 2. LEFT SIDEBAR (QUICK PANEL) */}
        <aside className="w-[260px] theme-glass border theme-border rounded-xl flex flex-col overflow-y-auto shrink-0 custom-scrollbar shadow-2xl shadow-black/50 select-none">
          
          {/* Group 1: Starter Missions */}
          <div className="px-5 py-4 border-b theme-border bg-gradient-to-b from-white/[0.02] to-transparent">
            <h3 className="text-[14px] font-bold theme-success mb-3 flex items-center gap-2 tracking-wide font-sans mt-1">
              <Play size={14} className="fill-current" /> Starter Missions
            </h3>
            <p className="text-[11px] text-gray-500 mb-4 leading-tight opacity-80">If a command fails, run 'fix' to get automated recovery help.</p>
            <div className="space-y-[4px]">
              <button onClick={() => fireCommand('help')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><FileCode2 size={13}/> Learn Basics</button>
              <button onClick={() => fireCommand('show dashboard')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Activity size={13}/> Dashboard</button>
              <button onClick={() => fireCommand('policy')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Shield size={13}/> Safety Check</button>
              <button onClick={() => fireCommand('deploy status')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Zap size={13}/> Deploy Ready</button>
              <div className="pt-2">
                 <button onClick={() => fireCommand('help')} className="w-full text-left px-3 py-2 text-[12px] theme-success bg-white/5 hover:bg-white/10 rounded flex items-center gap-3 transition-colors font-medium border theme-border border-opacity-50 shadow-inner"><Box size={13} className="fill-current"/> Beginner Guide</button>
              </div>
            </div>
          </div>

          {/* Group 2: Quick Commands */}
          <div className="px-5 py-4 border-b theme-border border-opacity-30">
            <h3 className="text-[14px] font-bold theme-primary mb-3 flex items-center gap-2 tracking-wide font-sans">
              <LogOut size={14} className="rotate-90" /> Quick Commands
            </h3>
            <div className="space-y-[4px]">
              <button onClick={() => fireCommand('show dashboard')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Activity size={13}/> Dashboard</button>
              <button onClick={() => fireCommand('help')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><HelpCircle size={13}/> Help</button>
              <button onClick={() => fireCommand('fix')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Settings size={13} className="rotate-45"/> Fix Error</button>
              <button onClick={() => fireCommand('explain')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Search size={13}/> Explain</button>
              <button onClick={() => fireCommand('undo')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><RotateCcw size={13}/> Undo</button>
              <button onClick={() => fireCommand('bookmarks')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Terminal size={13}/> Bookmarks</button>
              <button onClick={() => fireCommand('suggest')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><HelpCircle size={13}/> Suggest</button>
              <button onClick={() => fireCommand('pipelines')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Network size={13}/> Pipelines</button>
            </div>
          </div>

          {/* Group 3: Automation Deck */}
          <div className="px-5 py-4 border-b theme-border border-opacity-30">
            <h3 className="text-[14px] font-bold theme-warning mb-3 flex items-center gap-2 tracking-wide font-sans">
              <Settings size={14} className="rotate-45" /> Automation Deck
            </h3>
            <div className="space-y-[4px]">
              <button onClick={() => fireCommand('run safety policy check')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Shield size={13}/> Safety</button>
              <button onClick={() => fireCommand('run security audit')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Box size={13}/> Audit</button>
              <button onClick={() => fireCommand('deploy status')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Zap size={13}/> Deploy</button>
              <button onClick={() => fireCommand('check deployment drift')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Network size={13} className="rotate-45"/> Drift</button>
              <button onClick={() => fireCommand('git status && git log -n 3')} className="w-full text-left px-2 py-1.5 text-[12px] text-gray-400 hover:theme-text hover:bg-white/5 rounded flex items-center gap-3 transition-colors"><Box size={13}/> GitHub</button>
            </div>
          </div>
          
          {/* Bookmarks */}
          <div className="px-5 py-6">
            <h3 className="text-[14px] font-bold theme-warning mb-3 flex items-center gap-2 tracking-wide font-sans">
              <Terminal size={14} className="rotate-45" /> Bookmarks
            </h3>
            <div className="py-6 text-center">
              <p className="text-[12px] text-gray-600">No bookmarks yet</p>
            </div>
          </div>

        </aside>

        {/* 3. CENTER CONSOLE (TERMINAL) */}
        <main className="flex-1 flex flex-col glass-panel rounded-xl relative min-w-[500px] shadow-2xl shadow-black/50 overflow-hidden">
          {/* Terminal Viewport */}
          <div className="flex-1 p-4 pb-0 relative bg-black/40">
             <TerminalComponent ref={terminalRef} onConnected={() => setIsConnected(true)} onDisconnected={() => setIsConnected(false)} />
          </div>

          {/* Bottom Custom Input Bar */}
          <div className="h-[75px] shrink-0 p-4 bg-gradient-to-t from-black/80 to-transparent flex items-center justify-center z-20">
            <div className="relative w-full max-w-4xl flex items-center group">
               <div className="absolute left-4 text-[#38bdf8] transition-transform group-focus-within:scale-110">
                 <TerminalSquare size={16} />
               </div>
               <input 
                 type="text" 
                 value={input}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                 placeholder="Type a command or ask NeuroShell in English..."
                 className="w-full glass-input text-[#f4f4f5] text-sm font-mono pl-12 pr-14 py-3.5 rounded-xl focus:outline-none focus:border-[#38bdf8]/50 focus:shadow-[0_0_15px_rgba(56,189,248,0.2)] transition-all placeholder-[#52525b]"
                 autoFocus
               />
               <button 
                 onClick={handleSend}
                 className="absolute right-2 w-10 h-10 rounded-lg bg-[#38bdf8]/10 hover:bg-[#38bdf8]/20 text-[#38bdf8] flex items-center justify-center transition-all hover:scale-105 active:scale-95"
               >
                 <Send size={16} />
               </button>
            </div>
          </div>
        </main>

        {/* 4. RIGHT SIDEBAR (NEURAL COCKPIT) */}
        <aside className="w-[320px] glass-panel rounded-xl flex flex-col overflow-y-auto shrink-0 custom-scrollbar shadow-2xl shadow-black/50">
          
          <div className="p-4 border-b border-white/5 bg-gradient-to-b from-white/[0.02] to-transparent">
             <h2 className="text-[11px] font-bold text-[#39d2c0] uppercase tracking-wider mb-4 flex items-center gap-2 drop-shadow-lg"><Radio size={12}/> Neural Cockpit</h2>
             <div className="font-mono text-[10px] space-y-2 text-[#a1a1aa] glass-input p-3 rounded-lg">
                <div className="flex justify-between items-center"><span className="opacity-70">Ping:</span> <span className="text-[#39d2c0] drop-shadow-md">///// [8ms]</span></div>
                <div className="flex justify-between items-center"><span className="opacity-70">Loss:</span> <span className="text-[#3fb950] drop-shadow-md">////////// [0]</span></div>
                <div className="flex justify-between items-center"><span className="opacity-70">Swarm:</span> <span className={swarmMode ? "text-[#a78bfa] drop-shadow-md font-bold" : "text-[#d29922]"}>{swarmMode ? "ACTIVE" : "STANDBY"}</span></div>
             </div>
          </div>

          <div className="p-4 border-b border-white/5 flex-1 min-h-[250px] flex flex-col">
             <h2 className="text-[11px] font-bold text-[#bc8cff] uppercase tracking-wider mb-3 flex items-center gap-2 drop-shadow-lg"><Box size={12}/> Agent Activity</h2>
             <div ref={agentFeedRef} className="glass-input rounded-lg p-3 flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed custom-scrollbar">
                {agentLogs.map((log, idx) => (
                  <div key={idx} className={`agent-log mb-1.5 ${log.type === 'system' ? 'text-[#3fb950]' : (log.type === 'gc' ? 'text-[#d29922] font-semibold' : 'text-[#e6edf3]')}`}>
                    <span className="opacity-50 text-[10px] mr-2">[{log.time}]</span>
                    {log.msg}
                  </div>
                ))}
             </div>
          </div>

          <div className="p-4 h-[180px] flex flex-col shrink-0">
             <h2 className="text-[11px] font-bold text-[#56d364] uppercase tracking-wider mb-3 flex items-center gap-2 drop-shadow-lg"><HardDrive size={12}/> Deploy Status</h2>
             <div ref={deployFeedRef} className="glass-input rounded-lg p-3 flex-1 overflow-y-auto font-mono text-[10px] text-[#8b949e] mb-4 custom-scrollbar">
                <div className="mb-1 opacity-70">[{new Date().toLocaleTimeString()}] Deploy pipeline armed</div>
             </div>
             
             <div className="flex gap-2">
               <button onClick={() => fireCommand('show deployment graph')} className="flex-1 glass-button text-[#e6edf3] text-[11px] py-2 rounded-lg font-semibold tracking-wide">
                 GRAPH
               </button>
               <button onClick={() => fireCommand('deploy now')} className="flex-1 bg-gradient-to-r from-[#166534] to-[#15803d] border border-[#22c55e]/50 hover:from-[#15803d] hover:to-[#16a34a] text-white shadow-[0_0_15px_rgba(22,163,74,0.3)] text-[11px] py-2 rounded-lg font-bold tracking-wider transition-all hover:scale-[1.02] active:scale-[0.98]">
                 DEPLOY
               </button>
             </div>
          </div>
        </aside>
      </div>
      
      {/* Network Status Overlay */}
      <div className="absolute bottom-6 right-8 z-30 pointer-events-none">
        <div className={`flex items-center gap-2 px-3 py-1.5 glass-panel rounded-full shadow-lg border ${isConnected ? 'border-[#3fb950]/30' : 'border-[#f85149]/30'}`}>
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-[#3fb950] animate-pulse-glow' : 'bg-[#f85149]'}`}></div>
          <span className="text-[10px] font-mono font-medium opacity-80">
            {isConnected ? 'NODE LOCAL' : 'RECONNECTING...'}
          </span>
        </div>
      </div>
    </div>
  )
}

function ToggleButton({ active, onClick, label, color = "blue" }) {
  const getColors = () => {
    switch(color) {
      case 'cyan': return active ? 'bg-[#39d2c0]/20 border-[#39d2c0]/40 text-[#39d2c0] shadow-[0_0_10px_rgba(57,210,192,0.2)]' : 'border-transparent text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-white/5';
      case 'green': return active ? 'bg-[#3fb950]/20 border-[#3fb950]/40 text-[#3fb950] shadow-[0_0_10px_rgba(63,185,80,0.2)]' : 'border-transparent text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-white/5';
      case 'accent': return active ? 'bg-[#a78bfa]/20 border-[#a78bfa]/40 text-[#a78bfa] shadow-[inset_0_0_12px_rgba(167,139,250,0.2)] font-bold' : 'border-transparent text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-white/5';
      default: return active ? 'bg-[#38bdf8]/20 border-[#38bdf8]/40 text-[#38bdf8] shadow-[0_0_10px_rgba(56,189,248,0.2)]' : 'border-transparent text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-white/5';
    }
  }
  return <button onClick={onClick} className={`px-3 py-1.5 border rounded-md text-[11px] font-semibold transition-all ${getColors()}`}>{label}</button>;
}

function ActionButton({ icon, label, onClick }) {
  return (
    <button onClick={onClick} className="glass-button flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium text-[#e6edf3]">
      <span className="text-[#a1a1aa] group-hover:text-white transition-colors">{icon}</span>
      {label}
    </button>
  )
}

function ProgressBar({ label, percent, color }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between text-[10px] font-medium"><span className="text-[#8b949e]">{label}</span></div>
      <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden shadow-inner border border-white/5"><div className={`h-full ${color}`} style={{ width: percent }}></div></div>
    </div>
  )
}

function MissionButton({ label, onClick }) {
  return (
    <button onClick={onClick} className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] font-medium text-[#c9d1d9] glass-button rounded-lg text-left">
      <span className="text-[#38bdf8] drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]"><Shield size={12}/></span>{label}
    </button>
  )
}

export default App;
