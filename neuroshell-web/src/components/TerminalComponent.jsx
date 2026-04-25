import React, { useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

const TerminalComponent = forwardRef(({ onConnected, onDisconnected }, ref) => {
  const terminalRef = useRef(null);
  const xtermRef = useRef(null);
  const fitAddonRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!terminalRef.current) return;
    
    // Clear in case of React Strict Mode double-invocation
    if (terminalRef.current.hasChildNodes()) {
       terminalRef.current.innerHTML = '';
    }

    // Initialize xterm.js
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily: '"Cascadia Code", "Consolas", "Courier New", monospace',
      fontSize: 14,
      drawBoldTextInBrightColors: true,
      theme: {
        background: '#0c0c0e',
        foreground: '#e6edf3',
        cursor: '#38bdf8',
        selectionBackground: '#1a3d3aba',
        black: '#484f58',
        red: '#f85149',
        green: '#3fb950',
        yellow: '#d29922',
        blue: '#58a6ff',
        magenta: '#bc8cff',
        cyan: '#39d2c0',
        white: '#e6edf3',
        brightBlack: '#8b949e',
        brightRed: '#ff7b72',
        brightGreen: '#56d364',
        brightYellow: '#e3b341',
        brightBlue: '#79c0ff',
        brightMagenta: '#d2a8ff',
        brightCyan: '#56d4dd',
        brightWhite: '#ffffff',
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    
    term.open(terminalRef.current);
    
    // Delay fit so container has computed styles fully applied
    setTimeout(() => {
       try {
          fitAddon.fit();
       } catch {
       }
    }, 100);

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    term.writeln('\x1b[1;36m[NeuroShell System Engine Initializing...]\x1b[0m');
    term.writeln('Connecting to local python intelligence layer...');

    const connectWs = () => {
      const ws = new WebSocket('ws://localhost:8000/ws/terminal');
      
      ws.onopen = () => {
        term.writeln('\x1b[1;32m[Connected to Brain]\x1b[0m\r\n');
        if (onConnected) onConnected();
      };

      ws.onmessage = (event) => {
        // Output from neuroshell executor
        term.write(event.data);
      };

      ws.onclose = () => {
        term.writeln('\r\n\x1b[1;31m[Disconnected from backend. Retrying in 3s...]\x1b[0m');
        if (onDisconnected) onDisconnected();
        setTimeout(connectWs, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket Error: ', err);
      };

      wsRef.current = ws;
    };

    connectWs();

    // Resize handler
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      term.dispose();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useImperativeHandle(ref, () => ({
    sendCommand: (commandString) => {
      // Intentionally stripped client-side echo. The backend will naturally echo the shell prompt.


      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
         if (commandString.trim() === 'clear') {
            xtermRef.current.clear();
            return;
         }
         // Send to backend
         try {
            wsRef.current.send(JSON.stringify({ type: 'input', payload: commandString }));
         } catch (e) {
            xtermRef.current?.writeln(`\r\n\x1b[31m[SOCKET ERROR] ${e.message}\x1b[0m`);
         }
      } else {
         xtermRef.current?.writeln(`\r\n\x1b[31m[SYS] Cannot send. Socket State: ${wsRef.current ? wsRef.current.readyState : 'NULL'}\x1b[0m`);
      }
    },
    sendConfig: (configObj) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
         wsRef.current.send(JSON.stringify({ type: 'config', ...configObj }));
      } else if (xtermRef.current) {
         xtermRef.current.writeln(`\r\n\x1b[31m[CLIENT] Cannot send config, WebSocket not open.\x1b[0m`);
      }
    }
  }));

  return (
    <div 
      ref={terminalRef} 
      style={{ width: '100%', height: '100%' }} 
      className="terminal-container"
    />
  );
});

export default TerminalComponent;
