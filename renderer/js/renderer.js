/** * Nous Companion — Renderer v3 */
(function () {
  "use strict";

  const DEFAULT_WS_HOST = "127.0.0.1";
  const DEFAULT_WS_PORT = 8765;
  const WINDOW_WIDTH_PAD = 0;
  const WINDOW_HEIGHT_PAD = 0;
  const LOOPBACK_HOSTS = new Set(["", "file", "localhost", "127.0.0.1", "::1"]);
  const CHARACTER_CODEC_FREQUENCIES = {
    default: "140.85",
    roycampbell: "140.85",
    "roy campbell": "140.85",
    mei_ling: "140.96",
    meiling: "140.96",
    "mei ling": "140.96",
  };

  let WS_HOST = DEFAULT_WS_HOST;
  let WS_PORT = DEFAULT_WS_PORT;
  let WS_URL = `ws://${WS_HOST}:${WS_PORT}`;
  const RECONNECT_DELAY = 750;
  const CONNECT_WATCHDOG_MS = 5000;
  const BACKEND_READY_TIMEOUT_MS = 12000;
  const BACKEND_READY_POLL_MS = 250;
  let mainReconnectTimer = null;
  let commandReconnectTimer = null;
  let mainConnectWatchdog = null;
  let commandConnectWatchdog = null;
  let mainMessageLogCount = 0;
  let commandMessageLogCount = 0;
  let lastFrameTraceAt = 0;
  let settingsBridgeInitialized = false;
  let settingsBridgeCommandQueue = [];
  let settingsBridgeFlushTimer = null;
  const settingsBridgeCache = new Map();
  const SETTINGS_BRIDGE_CACHEABLE_TYPES = new Set([
    "characters",
    "character_data",
    "character_switched",
    "expressions",
    "godmode_changed",
    "godmode_state",
    "hermes_event",
    "model_changed",
    "models",
    "runtime_config",
    "sessions",
    "settings",
    "status",
    "tts_engines",
  ]);
  const SETTINGS_BRIDGE_RELAY_TYPES = new Set([
    ...SETTINGS_BRIDGE_CACHEABLE_TYPES,
    "audio",
    "audio_started",
    "audio_stop",
    "character_created",
    "character_data",
    "character_deleted",
    "character_exported",
    "character_imported",
    "character_saved",
    "text",
  ]);

  async function frontendLog(message) {
    const text = String(message);
    console.log(`[frontend] ${text}`);
    try {
      const invoke = window.__TAURI__?.core?.invoke;
      if (invoke) {
        await invoke("frontend_log", { message: text });
      }
    } catch (_) {
      // Avoid recursive noise if the logging bridge itself is unavailable.
    }
  }

  function logIncomingMessage(channel, data, rawLength) {
    const type = data && typeof data.type === "string" ? data.type : "unknown";
    const isFrame = type === "frame";
    const countRef = channel === "main" ? "main" : "command";
    if (isFrame) {
      const counter = countRef === "main" ? mainMessageLogCount : commandMessageLogCount;
      if (counter > 0) return;
    }
    if (countRef === "main") {
      if (mainMessageLogCount >= 12 && !isFrame) return;
      mainMessageLogCount += 1;
    } else {
      if (commandMessageLogCount >= 12 && !isFrame) return;
      commandMessageLogCount += 1;
    }
    void frontendLog(`${channel} ws recv type=${type} chars=${rawLength}`);
  }

  async function emitTauriEvent(name, payload) {
    const emit = window.__TAURI__?.event?.emit;
    if (typeof emit !== "function") {
      return false;
    }
    try {
      await emit(name, payload);
      return true;
    } catch (err) {
      void frontendLog(`emit ${name} failed: ${err}`);
      return false;
    }
  }

  function relayEventToSettings(data) {
    const type = data && typeof data.type === "string" ? data.type : "";
    if (!IS_TAURI_RUNTIME || !type || !SETTINGS_BRIDGE_RELAY_TYPES.has(type)) {
      return;
    }
    if (SETTINGS_BRIDGE_CACHEABLE_TYPES.has(type)) {
      settingsBridgeCache.set(type, data);
    }
    void emitTauriEvent("settings-bridge-event", data);
  }

  async function setupSettingsBridge() {
    if (settingsBridgeInitialized) return;
    settingsBridgeInitialized = true;
    const listen = window.__TAURI__?.event?.listen;
    if (typeof listen !== "function") {
      void frontendLog("settings bridge unavailable");
      return;
    }

    await listen("settings-bridge-command", (event) => {
      const payload = event?.payload || {};
      const cmd = payload.cmd;
      const data = payload.data || {};
      if (!cmd) return;
      void frontendLog(`settings bridge command cmd=${cmd}`);
      forwardSettingsBridgeCommand(cmd, data);
    });

    await listen("settings-bridge-bootstrap", () => {
      void frontendLog("settings bridge bootstrap");
      for (const cached of settingsBridgeCache.values()) {
        void emitTauriEvent("settings-bridge-event", cached);
      }
      for (const cmd of [
        "get_characters",
        "get_expressions",
        "get_tts_engines",
        "get_models",
        "get_settings",
        "get_runtime_config",
        "list_sessions",
        "get_godmode",
      ]) {
        forwardSettingsBridgeCommand(cmd, {});
      }
    });
  }

  function flushSettingsBridgeCommandQueue() {
    if (settingsBridgeFlushTimer) {
      clearTimeout(settingsBridgeFlushTimer);
      settingsBridgeFlushTimer = null;
    }
    const socket = IS_TAURI_RUNTIME
      ? (commandWs && commandWs.readyState === WebSocket.OPEN
          ? commandWs
          : (ws && ws.readyState === WebSocket.OPEN ? ws : null))
      : (commandWs && commandWs.readyState === WebSocket.OPEN
          ? commandWs
          : (ws && ws.readyState === WebSocket.OPEN ? ws : null));
    if (!socket || !settingsBridgeCommandQueue.length) {
      return;
    }
    const pending = settingsBridgeCommandQueue;
    settingsBridgeCommandQueue = [];
    for (const item of pending) {
      try {
        socket.send(JSON.stringify({ cmd: item.cmd, ...item.data }));
        void frontendLog(`settings bridge flush cmd=${item.cmd} via=${socket === commandWs ? "command" : "main"}`);
      } catch (err) {
        void frontendLog(`settings bridge flush failed cmd=${item.cmd}: ${err}`);
        settingsBridgeCommandQueue.unshift(item);
        break;
      }
    }
  }

  function scheduleSettingsBridgeFlush(reason = "timer") {
    if (settingsBridgeFlushTimer) return;
    settingsBridgeFlushTimer = setTimeout(() => {
      settingsBridgeFlushTimer = null;
      void frontendLog(`settings bridge flush scheduled reason=${reason}`);
      flushSettingsBridgeCommandQueue();
    }, 0);
  }

  function forwardSettingsBridgeCommand(cmd, data) {
    const payload = data && typeof data === "object" ? data : {};
    settingsBridgeCommandQueue.push({ cmd, data: payload });
    void frontendLog(
      `settings bridge queued cmd=${cmd} mainReady=${ws ? ws.readyState : "none"} commandReady=${commandWs ? commandWs.readyState : "none"}`
    );
    scheduleSettingsBridgeFlush(`queue-${cmd}`);
  }

  function clearMainConnectWatchdog() {
    if (mainConnectWatchdog) {
      clearTimeout(mainConnectWatchdog);
      mainConnectWatchdog = null;
    }
  }

  function clearCommandConnectWatchdog() {
    if (commandConnectWatchdog) {
      clearTimeout(commandConnectWatchdog);
      commandConnectWatchdog = null;
    }
  }

  function scheduleMainReconnect(reason) {
    if (mainReconnectTimer) return;
    void frontendLog(`schedule main reconnect reason=${reason}`);
    mainReconnectTimer = setTimeout(() => {
      mainReconnectTimer = null;
      void connect();
    }, RECONNECT_DELAY);
  }

  function scheduleCommandReconnect(reason) {
    if (commandReconnectTimer) return;
    void frontendLog(`schedule command reconnect reason=${reason}`);
    commandReconnectTimer = setTimeout(() => {
      commandReconnectTimer = null;
      void connectCommandSocket();
    }, RECONNECT_DELAY);
  }

  async function waitForBackendReady(label) {
    const invoke = window.__TAURI__?.core?.invoke;
    if (!invoke) return true;

    const deadline = Date.now() + BACKEND_READY_TIMEOUT_MS;
    while (Date.now() < deadline) {
      try {
        const ready = await invoke("backend_is_ready");
        if (ready) {
          void frontendLog(`backend ready for ${label}`);
          return true;
        }
      } catch (err) {
        void frontendLog(`backend_is_ready failed for ${label}: ${err}`);
      }
      await new Promise((resolve) => setTimeout(resolve, BACKEND_READY_POLL_MS));
    }

    void frontendLog(`backend ready timeout for ${label}`);
    return false;
  }

  function isLoopbackHost(hostname) {
    return LOOPBACK_HOSTS.has(hostname) || hostname.endsWith(".localhost");
  }

  async function loadWsConfig() {
    let host = null;
    let port = DEFAULT_WS_PORT;

    try {
      const invoke = window.__TAURI__?.core?.invoke;
      if (invoke) {
        const cfg = await invoke("get_backend_ws_config");
        if (cfg && typeof cfg.ws_host === "string" && cfg.ws_host.trim()) host = cfg.ws_host.trim();
        if (cfg && Number.isInteger(cfg.ws_port)) port = cfg.ws_port;
      }
    } catch (err) {
      console.warn("[nc] get_backend_ws_config unavailable, falling back to static config", err);
    }

    try {
      if (!host) {
        const res = await fetch("config.json", { cache: "no-store" });
        if (res.ok) {
          const cfg = await res.json();
          if (typeof cfg.ws_host === "string" && cfg.ws_host.trim()) host = cfg.ws_host.trim();
          if (Number.isInteger(cfg.ws_port)) port = cfg.ws_port;
        }
      }
    } catch (err) {
      console.warn("[nc] config.json unavailable, using fallback WS host", err);
    }

    if (!host) {
      const hostname = location.hostname;
      host = isLoopbackHost(hostname) ? DEFAULT_WS_HOST : hostname;
    }

    WS_HOST = host;
    WS_PORT = port;
    WS_URL = `ws://${WS_HOST}:${WS_PORT}`;
    console.log("[nc] WS target:", WS_URL);
  }

  // Element refs (assigned in init)
  let portrait, portraitCanvas, portraitCtx, textContent, cursor, statusDot, statusLabel, brandLabel, freqDisplay;
  let exprSelect, charSelect, spriteSizeSelect, reactInput, btnReact, btnSettings, btnCloseApp, settingsPanel;
  let btnPlayPause, waveformCanvas, audioTime, audioInfo, audioPlayer;
  let voiceRefName, btnVoiceRef, voiceRefInput;
  let waveVizCanvas, waveVizCtx, waveBuffer, waveAnimId;
  let waveCtx, grainCanvas, grainCtx, burstCanvas;
  let startupOverlay, startupMessage;
  let reactHistory = [];
  let reactHistoryIndex = -1;
  let currentSpriteSizeKey = "big";

  // State
  let ws = null;
  let commandWs = null;
  let pendingText = null;
  let audioCtx = null;
  let currentBuffer = null;
  let currentSource = null;
  let currentAudioElement = null;
  let audioGainNode = null;
  let audioFallbackRequested = false;
  let playbackStartTime = 0;
  let isPlaying = false;
  let playbackTimer = null;
  let wavBytes = null;
  let wavDuration = 0;
  let playbackVolume = 0.8;
  let typewriterTimer = null;
  let currentPortraitWidth = 187;  // tracks active sprite width for window resize
  let currentDisplayMode = "stretch";  // stretch | fit | cover | original
  let currentChromeStyle = "hermes";  // "hermes" (dashboard-inspired) | "classic" (Retro Codec)
  let pendingFrameBase64 = null;
  let lastFrameBase64 = null;  // cache for instant redraw after resize
  let analogBleedEnabled = true;
  let showBurstOnExpr = false;
  let isSpeaking = false;
  let _lastAudioCall = 0;
  let lastExpression = null;
  
  // Frame overlay
  let frameStyle = "creme";
  const FRAME_THICKNESS = 5;
  const BRACKET_LENGTH = 18;
  let frameCanvas = null;
  let frameCtx = null;
  let frameNeedsRedraw = true;
  
  // Colorize WebGL shader state
  let colorizeEnabled = false;
  let colorizeColor = [1.0, 0.0, 0.0]; // RGB floats
  let colorizeStrength = 1.0;
  let colorizeCanvas = null;
  let colorizeGl = null;
  let colorizeProgram = null;
  let colorizeTexture = null;
  let frameDecodeInFlight = false;
  const frameImageCache = new Map();
  const FRAME_IMAGE_CACHE_LIMIT = 96;
  let pendingCharacterSwitch = null;
  let lastMessageAgePerfAt = 0;
  let nextSwitchRequestId = 1;
  const pendingSwitchRequests = new Map();
  let pendingAudioPerf = null;
  const IS_TAURI_RUNTIME = typeof window.__TAURI__ !== "undefined" ||
    typeof window.__TAURI_INTERNALS__ !== "undefined" ||
    navigator.userAgent.includes("Tauri");
  const MAX_FRAME_AGE_MS = IS_TAURI_RUNTIME ? 250 : 500;
  const GRAIN_FRAME_SKIP = IS_TAURI_RUNTIME ? 15 : 10;
  const GRAIN_BLOCK_SIZE = IS_TAURI_RUNTIME ? 6 : 4;
  const BURST_FRAME_COUNT = IS_TAURI_RUNTIME ? 8 : 12;
  const BURST_NOISE_COUNT = IS_TAURI_RUNTIME ? 80 : 140;
  const BURST_BAR_MIN = IS_TAURI_RUNTIME ? 3 : 4;
  const BURST_BAR_RANGE = IS_TAURI_RUNTIME ? 3 : 4;
  let lastMainThreadPerfAt = 0;

  // ─── Init ────────────────────────────────────────────────

  async function init() {
    void frontendLog(`init start readyState=${document.readyState} tauri=${typeof window.__TAURI__ !== "undefined"} origin=${location.origin} protocol=${location.protocol} secure=${window.isSecureContext} ua=${navigator.userAgent}`);
    portrait = document.getElementById("portrait");
    portraitCanvas = document.getElementById("portrait-canvas");
    portraitCtx = portraitCanvas.getContext("2d");
    textContent = document.getElementById("text-content");
    cursor = document.getElementById("cursor");
    statusDot = document.getElementById("status-dot");
    statusLabel = document.getElementById("status-label");
    brandLabel = document.getElementById("brand-label");
    freqDisplay = document.getElementById("freq-display");
    exprSelect = document.getElementById("expr-select");
    charSelect = document.getElementById("char-select");
    spriteSizeSelect = document.getElementById("sprite-size-select");
    reactInput = document.getElementById("react-input");
    btnReact = document.getElementById("btn-react");
    btnSettings = document.getElementById("btn-settings");
    btnCloseApp = document.getElementById("btn-close-app");
    settingsPanel = document.getElementById("settings-panel");
    waveformCanvas = document.getElementById("audio-waveform");
    audioTime = document.getElementById("audio-time");
    audioInfo = document.getElementById("audio-info");
    audioPlayer = document.getElementById("audio-player");
    startupOverlay = document.getElementById("startup-overlay");
    startupMessage = document.getElementById("startup-message");
    // Random splash background from bg1–bg4, never repeats consecutively
    (function() {
      try {
        var last = parseInt(localStorage.getItem("nc_splash_bg") || "0", 10);
        var n;
        do { n = Math.floor(Math.random() * 4) + 1; } while (n === last);
        localStorage.setItem("nc_splash_bg", String(n));
        var s = document.createElement("style");
        s.textContent = ".startup-overlay::before{background-image:url('bg" + n + ".jpg') !important}";
        document.head.appendChild(s);
      } catch(e) { /* non-critical */ }
    })();
    setStartupOverlay(true, "Booting");
    initFrameOverlay(187, 267);  // create frame overlay early
    // Move it into the splash immediately (splash is already visible)
    const frameCanvas = document.getElementById("frame-overlay-canvas");
    if (frameCanvas && startupOverlay && frameCanvas.parentNode !== startupOverlay) {
      startupOverlay.appendChild(frameCanvas);
    }
    window.addEventListener("beforeunload", () => { void frontendLog("beforeunload"); });
    window.addEventListener("pagehide", () => { void frontendLog("pagehide"); });
    window.addEventListener("pageshow", () => { void frontendLog("pageshow"); });
    document.addEventListener("visibilitychange", () => { void frontendLog(`visibilitychange hidden=${document.hidden} state=${document.visibilityState}`); });
    document.addEventListener("securitypolicyviolation", (event) => {
      void frontendLog(`csp blocked=${event.blockedURI || ""} directive=${event.violatedDirective || ""} effective=${event.effectiveDirective || ""}`);
    });
    window.addEventListener("error", (event) => {
      void frontendLog(`window.error message=${event.message} source=${event.filename || ""} line=${event.lineno || 0}:${event.colno || 0}`);
    });
    window.addEventListener("unhandledrejection", (event) => {
      const reason = event.reason && (event.reason.stack || event.reason.message || String(event.reason));
      void frontendLog(`unhandledrejection reason=${reason || "unknown"}`);
    });
    
    // Audio elements may not exist in main window (they're in settings)
    if (waveformCanvas) {
      waveCtx = waveformCanvas.getContext("2d");
    } else {
      waveCtx = null;
      console.log("[nc] Audio player not in main window (settings has it)");
    }
    
    // Voice ref elements may not exist in main window
    voiceRefName = document.getElementById("voice-ref-name");
    btnVoiceRef = document.getElementById("btn-voice-ref");
    voiceRefInput = document.getElementById("voice-ref-input");
    
    // Initialize grain canvas
    grainCanvas = document.getElementById("grain-canvas");
    if (grainCanvas) grainCtx = grainCanvas.getContext("2d");
    
    // Initialize wave viz canvas
    waveVizCanvas = document.getElementById("wave-viz");
    if (waveVizCanvas) {
      waveVizCtx = waveVizCanvas.getContext("2d");
      initWaveViz();
    }
    
    // Initialize burst canvas
    burstCanvas = document.getElementById("burst-canvas");

    // Load saved sprite size
    const savedSpriteSize = loadSpriteSize();
    if (savedSpriteSize && SPRITE_SIZES[savedSpriteSize]) {
      applySpriteSize(savedSpriteSize);
      if (spriteSizeSelect) spriteSizeSelect.value = savedSpriteSize;
    } else {
      // Invalid saved size, use default
      console.log("[nc] Invalid saved sprite size:", savedSpriteSize, "using default");
      applySpriteSize("big");
      if (spriteSizeSelect) spriteSizeSelect.value = "big";
    }

    // Debug: check if portrait canvas exists
    console.log("[nc] portraitCanvas element:", portraitCanvas);
    console.log("[nc] portraitCanvas in DOM:", document.body.contains(portraitCanvas));
    console.log("[nc] portraitCanvas visible:", portraitCanvas.offsetWidth > 0, portraitCanvas.offsetHeight > 0);
    
    // Check portrait container
    const portraitContainer = document.querySelector('.portrait-container');
    const chromeOverlay = document.querySelector('.chrome-overlay');
    if (portraitContainer && chromeOverlay) {
      portraitContainer.addEventListener("click", (e) => {
        if (e.target.closest('button')) return;
        chromeOverlay.classList.toggle("visible");
      });

      // Start hidden
      chromeOverlay.classList.remove("visible");
    }

    // Check for Tauri API
    const isTauri = typeof window.__TAURI__ !== 'undefined' || 
                    typeof window.__TAURI_INTERNALS__ !== 'undefined' ||
                    navigator.userAgent.includes('Tauri');
    
    if (isTauri) {
      console.log("[nc] Tauri environment detected");
      console.log("[nc] window.__TAURI__:", window.__TAURI__);
      console.log("[nc] window.__TAURI__?.core?.invoke:", typeof window.__TAURI__?.core?.invoke);
      void setupSettingsBridge();
      
      // Set initial window size
      setTimeout(() => syncWindowSize(), 100);
    } else {
      console.log("[nc] Running in browser");
      console.log("[nc] User agent:", navigator.userAgent);
    }

    if (btnSettings) {
      btnSettings.addEventListener("click", async (e) => {
        e.stopPropagation(); // Prevent top-bar click from firing
        await openSettingsWindow();
      });
    }

    if (btnCloseApp) {
      btnCloseApp.addEventListener("click", async (e) => {
        e.stopPropagation();
        await closeApp();
      });
    }

    // Hermes text action buttons
    const hermesBtnSettings = document.getElementById("hermes-btn-settings");
    const hermesBtnClose = document.getElementById("hermes-btn-close");
    if (hermesBtnSettings) {
      hermesBtnSettings.addEventListener("click", async (e) => {
        e.stopPropagation();
        await openSettingsWindow();
      });
    }
    if (hermesBtnClose) {
      hermesBtnClose.addEventListener("click", async (e) => {
        e.stopPropagation();
        await closeApp();
      });
    }

    document.addEventListener("dblclick", (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, true);
    
    // React
    if (btnReact) {
      btnReact.addEventListener("click", () => {
        const ctx = reactInput.value.trim();
        if (ctx) {
          reactHistory.unshift(ctx);
          reactHistory = reactHistory.slice(0, 20);
          reactHistoryIndex = -1;
          sendCommand("react", { context: ctx });
          reactInput.value = "";
        }
      });
    }
    if (reactInput) {
      reactInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && btnReact) {
          btnReact.click();
          return;
        }
        if (e.key === "ArrowUp") {
          if (!reactHistory.length) return;
          e.preventDefault();
          if (reactHistoryIndex < reactHistory.length - 1) reactHistoryIndex += 1;
          reactInput.value = reactHistory[reactHistoryIndex] || reactInput.value;
          reactInput.setSelectionRange(reactInput.value.length, reactInput.value.length);
        } else if (e.key === "ArrowDown") {
          if (reactHistoryIndex > 0) {
            e.preventDefault();
            reactHistoryIndex -= 1;
            reactInput.value = reactHistory[reactHistoryIndex] || "";
            reactInput.setSelectionRange(reactInput.value.length, reactInput.value.length);
          } else if (reactHistoryIndex === 0) {
            e.preventDefault();
            reactHistoryIndex = -1;
            reactInput.value = "";
          }
        }
      });
    }

    // Character
    if (charSelect) {
      charSelect.addEventListener("change", (e) => {
        const requestId = `renderer-${nextSwitchRequestId++}`;
        const startedAt = performance.now();
        pendingSwitchRequests.set(requestId, {
          character: charSelect.value,
          startedAt,
          rendererReported: false,
          controlReported: false,
        });
        sendCommand("switch_character", { character: charSelect.value, request_id: requestId });
        sendPerf("switch_command_sent", {
          request_id: requestId,
          character: charSelect.value,
          event_delay_ms: Number((startedAt - (e.timeStamp || startedAt)).toFixed(1)),
          buffered_amount: commandWs && commandWs.readyState === WebSocket.OPEN
            ? commandWs.bufferedAmount
            : (ws ? ws.bufferedAmount : 0),
        });
        updateFrequencyDisplay(charSelect.value);
      });
    }

    // Expression
    if (exprSelect) {
      exprSelect.addEventListener("change", () => {
        sendCommand("set_expression", { expression: exprSelect.value });
      });
    }

    // Sprite Size
    if (spriteSizeSelect) {
      spriteSizeSelect.addEventListener("change", () => {
        applySpriteSize(spriteSizeSelect.value);
      });
    }

    // Voice ref
    if (btnVoiceRef) {
      btnVoiceRef.addEventListener("click", () => voiceRefInput.click());
    }
    if (voiceRefInput) {
      voiceRefInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file && voiceRefName) voiceRefName.textContent = file.name;
      });
    }

    // Audio play/pause
    if (btnPlayPause) {
      btnPlayPause.addEventListener("click", () => {
        if (!currentBuffer) return;
        if (isPlaying) {
          const pos = audioCtx.currentTime - playbackStartTime;
          stopPlayback();
          drawPlayhead(pos);
          audioTime.textContent = fmtTime(pos) + " / " + fmtTime(currentBuffer.duration);
        } else {
          startPlaybackFrom(0);
        }
      });
    }

    // Click-to-seek on waveform
    if (waveformCanvas) {
      waveformCanvas.addEventListener("click", (e) => {
        if (!currentBuffer) return;
        const rect = waveformCanvas.getBoundingClientRect();
        const seekTo = ((e.clientX - rect.left) / rect.width) * wavDuration;
        const wasPlaying = isPlaying;
        stopPlayback();
        drawPlayhead(seekTo);
        audioTime.textContent = fmtTime(seekTo) + " / " + fmtTime(wavDuration);
        sendCommand("playback_pos", { pos: seekTo });
        if (wasPlaying) startPlaybackFrom(seekTo);
      });
    }

    applyChromeStyle("hermes");
    void connect();
  }

  async function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    await loadWsConfig();
    const ready = await waitForBackendReady("main");
    if (!ready) {
      updateStatus("disconnected");
      setStartupOverlay(true, "Standing by");
      scheduleMainReconnect("not-ready");
      return;
    }
    updateStatus("connecting");
    setStartupOverlay(true, "Connecting");
    void frontendLog(`connect main ws=${WS_URL}`);
    const socket = new WebSocket(WS_URL);
    ws = socket;
    clearMainConnectWatchdog();
    mainConnectWatchdog = setTimeout(() => {
      if (ws === socket && socket.readyState !== WebSocket.OPEN) {
        void frontendLog(`main ws watchdog readyState=${socket.readyState}`);
        try { socket.close(); } catch (_) {}
        scheduleMainReconnect("watchdog");
      }
    }, CONNECT_WATCHDOG_MS);
    socket.onopen = () => {
      if (ws !== socket) return;
      clearMainConnectWatchdog();
      if (mainReconnectTimer) {
        clearTimeout(mainReconnectTimer);
        mainReconnectTimer = null;
      }
      void frontendLog("main ws onopen");
      updateStatus("connected");
      flushSettingsBridgeCommandQueue();
      void frontendLog("main ws send register_client");
      send("register_client", {
        role: "renderer",
        client_name: "main-renderer",
        audio_transport: "base64",
      });
      void frontendLog("main ws send get_expressions");
      send("get_expressions", {});
      void frontendLog("main ws send get_characters");
      send("get_characters", {});
      void frontendLog("main ws send get_settings");
      send("get_settings", {});
      void frontendLog("main ws send get_tts_engines");
      send("get_tts_engines", {});
      void frontendLog("main ws send get_models");
      send("get_models", {});
      void frontendLog("main ws send get_runtime_config");
      send("get_runtime_config", {});
      void frontendLog("main ws send list_sessions");
      send("list_sessions", {});
      void frontendLog("main ws send get_godmode");
      send("get_godmode", {});
      void connectCommandSocket();
    };
    socket.onmessage = async (ev) => {
      if (ws !== socket) return;
      const msgStart = performance.now();
      try {
        // Browser may deliver large text messages as Blob objects (handled by
        // Chrome when the message exceeds ~1MB). Handle both string and Blob.
        let text;
        if (typeof ev.data === "string") {
          text = ev.data;
        } else {
          text = await ev.data.text();
        }
        const d = JSON.parse(text);
        logIncomingMessage("main", d, text.length);
        relayEventToSettings(d);
        handleEvent(d);
        const msgMs = performance.now() - msgStart;
        if (msgMs > 100) {
          sendPerf("ws_message_slow", {
            type: d.type,
            chars: text.length,
            total_ms: Number(msgMs.toFixed(1)),
          });
        }
      } catch (err) {
        void frontendLog(`main ws onmessage error=${err && (err.stack || err.message || String(err))}`);
      }
    };
    socket.onclose = (ev) => {
      const isCurrent = ws === socket;
      if (isCurrent) {
        ws = null;
      } else {
        void frontendLog(`main ws stale onclose code=${ev.code} reason=${ev.reason || ""} clean=${ev.wasClean}`);
        return;
      }
      clearMainConnectWatchdog();
      void frontendLog(`main ws onclose code=${ev.code} reason=${ev.reason || ""} clean=${ev.wasClean}`);
      updateStatus("disconnected");
      setStartupOverlay(true, "Standing by");
      scheduleMainReconnect("close");
    };
    socket.onerror = (ev) => {
      if (ws !== socket) {
        void frontendLog(`main ws stale onerror type=${ev?.type || "unknown"}`);
        return;
      }
      void frontendLog(`main ws onerror type=${ev?.type || "unknown"}`);
      setStartupOverlay(true, "Standing by");
      if (socket.readyState !== WebSocket.OPEN) {
        clearMainConnectWatchdog();
        try { socket.close(); } catch (_) {}
        ws = null;
        scheduleMainReconnect("error");
      }
    };
  }

  async function connectCommandSocket() {
    // In Tauri mode, bridge commands route via the main WS instead.
    // Skip the separate command WS entirely — it has persistent connection
    // issues and the main WS relay is more reliable.
    if (IS_TAURI_RUNTIME) return;
    if (commandWs && (commandWs.readyState === WebSocket.OPEN || commandWs.readyState === WebSocket.CONNECTING)) {
      return;
    }
    await loadWsConfig();
    const ready = await waitForBackendReady("command");
    if (!ready) {
      scheduleCommandReconnect("not-ready");
      return;
    }
    void frontendLog(`connect command ws=${WS_URL}`);
    const socket = new WebSocket(WS_URL);
    commandWs = socket;
    clearCommandConnectWatchdog();
    commandConnectWatchdog = setTimeout(() => {
      if (commandWs === socket && socket.readyState !== WebSocket.OPEN) {
        void frontendLog(`command ws watchdog readyState=${socket.readyState}`);
        try { socket.close(); } catch (_) {}
        scheduleCommandReconnect("watchdog");
      }
    }, CONNECT_WATCHDOG_MS);
    socket.onopen = () => {
      if (commandWs !== socket) return;
      clearCommandConnectWatchdog();
      if (commandReconnectTimer) {
        clearTimeout(commandReconnectTimer);
        commandReconnectTimer = null;
      }
      void frontendLog("command ws onopen");
      socket.send(JSON.stringify({
        cmd: "register_client",
        role: "control",
        client_name: "main-control",
      }));
      if (!IS_TAURI_RUNTIME) {
        socket.send(JSON.stringify({ cmd: "get_godmode" }));
        socket.send(JSON.stringify({ cmd: "list_sessions" }));
        socket.send(JSON.stringify({ cmd: "get_models" }));
        socket.send(JSON.stringify({ cmd: "get_tts_engines" }));
        socket.send(JSON.stringify({ cmd: "get_runtime_config" }));
      }
      flushSettingsBridgeCommandQueue();
    };
    socket.onmessage = async (ev) => {
      if (commandWs !== socket) return;
      try {
        let text;
        if (typeof ev.data === "string") {
          text = ev.data;
        } else {
          text = await ev.data.text();
        }
        const d = JSON.parse(text);
        logIncomingMessage("command", d, text.length);
        relayEventToSettings(d);
        if (typeof d.server_sent_at_ms === "number") {
          const ageMs = Date.now() - d.server_sent_at_ms;
          if (ageMs > 100) {
            sendPerf("main_control_message_age", {
              type: d.type,
              age_ms: Number(ageMs.toFixed(1)),
              request_id: d.request_id || null,
              has_focus: typeof document.hasFocus === "function" ? document.hasFocus() : null,
              visibility_state: document.visibilityState || null,
              hidden: typeof document.hidden === "boolean" ? document.hidden : null,
            });
          }
        }
        if (d.type === "character_switched" && d.request_id && pendingSwitchRequests.has(d.request_id)) {
          const req = pendingSwitchRequests.get(d.request_id);
          if (!req.controlReported) {
            req.controlReported = true;
            sendPerf("main_control_switch_roundtrip", {
              request_id: d.request_id,
              character: d.character,
              roundtrip_ms: Number((performance.now() - req.startedAt).toFixed(1)),
              buffered_amount: commandWs ? commandWs.bufferedAmount : 0,
            });
            if (req.rendererReported) {
              pendingSwitchRequests.delete(d.request_id);
            } else {
              pendingSwitchRequests.set(d.request_id, req);
            }
          }
        }
      } catch (err) {
        void frontendLog(`command ws onmessage error=${err && (err.stack || err.message || String(err))}`);
      }
    };
    socket.onclose = () => {
      const isCurrent = commandWs === socket;
      if (isCurrent) {
        commandWs = null;
      } else {
        void frontendLog("command ws stale onclose");
        return;
      }
      clearCommandConnectWatchdog();
      void frontendLog("command ws onclose");
      scheduleCommandReconnect("close");
    };
    socket.onerror = (ev) => {
      if (commandWs !== socket) {
        void frontendLog(`command ws stale onerror type=${ev?.type || "unknown"}`);
        return;
      }
      void frontendLog(`command ws onerror type=${ev?.type || "unknown"}`);
      if (socket.readyState !== WebSocket.OPEN) {
        clearCommandConnectWatchdog();
        try { socket.close(); } catch (_) {}
        commandWs = null;
        scheduleCommandReconnect("error");
      }
    };
  }

  function send(cmd, data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ cmd, ...data }));
  }

  function sendCommand(cmd, data) {
    const socket = IS_TAURI_RUNTIME
      ? (ws && ws.readyState === WebSocket.OPEN ? ws : commandWs)
      : (commandWs && commandWs.readyState === WebSocket.OPEN ? commandWs : ws);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ cmd, ...data }));
    }
  }

  function sendPerf(name, data) {
    sendCommand("perf", {
      name,
      data,
    });
  }

  function getAudioGainNode() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (!audioGainNode) {
      audioGainNode = audioCtx.createGain();
      audioGainNode.connect(audioCtx.destination);
      ensureAnalyser(); // create alongside audio graph
    }
    audioGainNode.gain.value = playbackVolume;
    return audioGainNode;
  }

  function applyPlaybackVolume(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    playbackVolume = Math.max(0, Math.min(1, numeric));
    if (currentAudioElement) {
      currentAudioElement.volume = playbackVolume;
    }
    if (audioGainNode) {
      audioGainNode.gain.value = playbackVolume;
    }
  }

  function applyChromeStyle(style) {
    console.log("[nc] Chrome style:", style);
    currentChromeStyle = style;
    const wrapper = document.getElementById("wrapper");
    if (!wrapper) return;
    if (style === "hermes") {
      wrapper.classList.add("hermes-mode");
      applyHermesLayout();
    } else {
      wrapper.classList.remove("hermes-mode");
    }
  }

  function applyHermesLayout() {
    const companion = document.getElementById("companion");
    const wrapper = document.getElementById("wrapper");
    if (!companion || !wrapper) return;
    const width = companion.offsetWidth || parseInt(companion.style.width) || 187;
    wrapper.classList.remove("hermes-big", "hermes-medium", "hermes-small");
    if (width >= 120) {
      wrapper.classList.add("hermes-big");
    } else if (width >= 80) {
      wrapper.classList.add("hermes-medium");
    } else {
      wrapper.classList.add("hermes-small");
    }
  }

  // ─── Wave Viz ──────────────────────────────────────────────

  const WAVE_BUFFER_SIZE = 160;
  let wavePhase = 0;
  let waveAmplitude = 0;
  let waveActive = false;
  let waveSamples = 0;
  let smoothedRms = 0;
  let analyserNode = null;
  let waveInited = false;

  function initWaveViz() {
    if (!waveVizCanvas || !brandLabel || waveInited) return;
    waveInited = true;
    // Measure NOUS using the ACTUAL rendered text (accounts for font loading, letter-spacing)
    const nousWidth = measureRenderedTextWidth("NOUS");
    const gapLeft = 2;
    const brandLeft = 18;
    const winWidth = document.getElementById("companion")?.offsetWidth || 187;
    waveVizCanvas.style.left = (brandLeft + nousWidth + gapLeft) + "px";
    const vizWidth = Math.max(20, winWidth - (brandLeft + nousWidth + gapLeft));
    const vizHeight = 28;
    const dpr = window.devicePixelRatio || 1;
    waveVizCanvas.width = Math.round(vizWidth * dpr);
    waveVizCanvas.height = Math.round(vizHeight * dpr);
    waveVizCanvas.style.width = vizWidth + "px";
    waveVizCanvas.style.height = vizHeight + "px";
    waveBuffer = new Float32Array(WAVE_BUFFER_SIZE);
    waveAmplitude = 0.01;
    waveActive = true; // always gently running
    if (!waveAnimId) {
      waveAnimId = requestAnimationFrame(drawWaveViz);
    }
    // Re-measure after fonts load for accuracy
    document.fonts.ready.then(() => {
      repositionWaveViz();
    });
  }

  function repositionWaveViz() {
    if (!waveVizCanvas) return;
    const actualWidth = measureRenderedTextWidth("NOUS");
    const actualLeft = 18 + actualWidth + 2;
    const winWidth = document.getElementById("companion")?.offsetWidth || 187;
    waveVizCanvas.style.left = actualLeft + "px";
    const actualVizWidth = Math.max(20, winWidth - actualLeft);
    const dpr = window.devicePixelRatio || 1;
    waveVizCanvas.width = Math.round(actualVizWidth * dpr);
    waveVizCanvas.style.width = actualVizWidth + "px";
    alignWaveViz();
  }

  function measureRenderedTextWidth(text) {
    // Create a hidden span with the same font properties to measure actual rendered width
    const span = document.createElement("span");
    span.textContent = text;
    span.style.cssText = `
      font-family: var(--font-brand);
      font-weight: 700;
      font-size: 24px;
      letter-spacing: 0.0525rem;
      text-transform: uppercase;
      position: absolute;
      visibility: hidden;
      white-space: nowrap;
    `;
    document.body.appendChild(span);
    const width = span.getBoundingClientRect().width;
    document.body.removeChild(span);
    return width;
  }

  function alignWaveViz() {
    if (!waveVizCanvas || !brandLabel) return;
    const brandRect = brandLabel.getBoundingClientRect();
    const parent = waveVizCanvas.offsetParent;
    if (!parent) return;
    const parentRect = parent.getBoundingClientRect();
    const canvasH = waveVizCanvas.offsetHeight || 28;
    const textH = 24;
    const offset = (canvasH - textH) / 2;
    waveVizCanvas.style.top = (brandRect.top - parentRect.top - offset) + "px";
  }

  function ensureAnalyser() {
    if (analyserNode) return analyserNode;
    if (!audioCtx) return null;
    analyserNode = audioCtx.createAnalyser();
    analyserNode.fftSize = 256;
    return analyserNode;
  }

  function startWaveViz() {
    waveActive = true;
    waveSamples = 0;
    alignWaveViz();
  }

  function stopWaveViz() {
    smoothedRms = 0;
    // amplitude naturally decays to baseline via targetAmp
  }

  function drawWaveViz(timestamp) {
    if (waveSamples === 0) alignWaveViz();
    waveSamples++;

    // Read real audio RMS from analyser if available
    let audioEnergy = 0;
    if (analyserNode) {
      const data = new Uint8Array(analyserNode.frequencyBinCount);
      try { analyserNode.getByteTimeDomainData(data); } catch(e) {}
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      audioEnergy = Math.sqrt(sum / data.length);
    }

    // Smooth RMS
    const target = audioEnergy > 0 ? audioEnergy * 1.5 : 0;
    smoothedRms += (target - smoothedRms) * 0.06;

    // Amplitude: very low at idle, rises with audio (less smooth, faster)
    const targetAmp = Math.max(0.01, smoothedRms * 2);
    waveAmplitude += (targetAmp - waveAmplitude) * 0.18;

    // Advance phase — responsive speed for audio
    wavePhase += 0.02;
    if (wavePhase > 1) wavePhase -= 1;
    const beat = Math.sin(wavePhase * Math.PI * 2);
    // Full sine strength for audio reactivity, audio adds extra energy
    const value = (beat * 0.6 + smoothedRms * 0.4) * Math.min(0.7, waveAmplitude * 3);
    const clamped = Math.max(-1, Math.min(1, value));

    // Push to buffer
    for (let i = 0; i < WAVE_BUFFER_SIZE - 1; i++) {
      waveBuffer[i] = waveBuffer[i + 1];
    }
    waveBuffer[WAVE_BUFFER_SIZE - 1] = clamped;

    // Draw
    drawWaveLine();
    waveAnimId = requestAnimationFrame(drawWaveViz);
  }

  function drawWaveLine() {
    if (!waveVizCtx || !waveVizCanvas) return;
    const w = waveVizCanvas.width;
    const h = waveVizCanvas.height;
    const dpr = window.devicePixelRatio || 1;
    waveVizCtx.clearRect(0, 0, w, h);
    if (waveAmplitude < 0.005) return;
    const mid = h / 2;
    const amp = (h / 2 - 2) * dpr;
    waveVizCtx.beginPath();
    for (let i = 0; i < WAVE_BUFFER_SIZE; i++) {
      const x = (i / (WAVE_BUFFER_SIZE - 1)) * w;
      // Fade to 0 at edges — flat 15% on each side
      const p = i / (WAVE_BUFFER_SIZE - 1);
      const edge = 0.15;
      let fade;
      if (p < edge) fade = p / edge;
      else if (p > 1 - edge) fade = (1 - p) / edge;
      else fade = 1;
      const y = mid + waveBuffer[i] * amp * fade;
      if (i === 0) waveVizCtx.moveTo(x, y);
      else waveVizCtx.lineTo(x, y);
    }
    waveVizCtx.strokeStyle = "rgba(255, 230, 203, 0.3)";
    waveVizCtx.lineWidth = 1.2 * dpr;
    waveVizCtx.stroke();
  }

  function startMainThreadMonitor() {
    let lastTick = performance.now();
    function tick(now) {
      const gap = now - lastTick;
      if (gap > 250 && now - lastMainThreadPerfAt > 500) {
        sendPerf("main_thread_stall", {
          gap_ms: Number(gap.toFixed(1)),
        });
        lastMainThreadPerfAt = now;
      }
      lastTick = now;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ─── Event Handling ──────────────────────────────────────

  function handleEvent(data) {
    const { type, frame, expression } = data;
    const serverSentAtMs = typeof data.server_sent_at_ms === "number" ? data.server_sent_at_ms : null;
    if (typeof data.server_sent_at_ms === "number") {
      const ageMs = Date.now() - data.server_sent_at_ms;
      if (ageMs > 100) {
        const now = performance.now();
        if (type !== "frame" || now - lastMessageAgePerfAt > 500) {
          sendPerf("message_age", {
            type,
            age_ms: Number(ageMs.toFixed(1)),
            request_id: data.request_id || null,
            frame_chars: frame ? frame.length : 0,
            has_focus: typeof document.hasFocus === "function" ? document.hasFocus() : null,
            visibility_state: document.visibilityState || null,
            hidden: typeof document.hidden === "boolean" ? document.hidden : null,
          });
          lastMessageAgePerfAt = now;
        }
      }
    }

    if (frame) {
      // Delay first draw until sprite dimensions arrive from server
      // so the canvas is sized correctly. Frame is cached regardless.
      lastFrameBase64 = frame;
      if (spriteDimensionsReady) {
        drawPortraitWithBleed(frame);
        setStartupOverlay(false);
      }
    }

    switch (type) {
      case "idle":
        updateStatus("connected");
        pendingText = null;
        isSpeaking = false;
        break;
      case "frame":
        if (performance.now() - lastFrameTraceAt > 5000) {
          lastFrameTraceAt = performance.now();
          void frontendLog(`main frame trace expr=${expression || "unknown"} cached=${frameImageCache.has(frame)}`);
        }
        // Track expression for burst-on-expression-change feature
        if (expression) {
          if (showBurstOnExpr && !isSpeaking && lastExpression && lastExpression !== expression) {
            console.log("[nc] Expr changed:", lastExpression, "→", expression, "→ triggerBurst()");
            triggerBurst(true);
          } else if (lastExpression && lastExpression !== expression) {
            console.log("[nc] Expr changed but no burst: showBurstOnExpr=", showBurstOnExpr, "isSpeaking=", isSpeaking);
          }
          lastExpression = expression;
        }
        break;
      case "expressions":
        if (data.expressions) populateExpressions(data.expressions);
        break;
      case "audio":
        handleAudio(data.audio, data.audio_path, data.duration_s);
        updateStatus("speaking");
        isSpeaking = true;
        break;
      case "audio_stop":
        stopPlayback();
        updateStatus("connected");
        setCursorVisible(false);
        isSpeaking = false;
        break;
      case "characters":
        if (data.characters) {
          populateCharacters(data.characters, data.active);
          updateFrequencyDisplay(data.active);
        }
        // Update native sprite dimensions on initial load
        if (data.frame_width && data.frame_height) {
          spriteDimensionsReady = true;
          if (data.frame_width !== nativeSpriteWidth || data.frame_height !== nativeSpriteHeight) {
            nativeSpriteWidth = data.frame_width;
            nativeSpriteHeight = data.frame_height;
            refreshSpriteSizes();
          }
          // Draw cached frame at correct size
          const currentSize = spriteSizeSelect ? spriteSizeSelect.value : loadSpriteSize();
          if (currentSize) {
            applySpriteSize(currentSize);
          }
          // First frame: hide splash now that dimensions are known
          if (lastFrameBase64) {
            setStartupOverlay(false);
          }
        }
        break;
      case "settings":
        if (data.settings) {
          console.log("[nc] Settings received, chrome_style =", data.settings.chrome_style);
          if (typeof data.settings.playback_volume === "number") {
            applyPlaybackVolume(data.settings.playback_volume);
          }
          if (data.settings.chrome_style) {
            currentChromeStyle = data.settings.chrome_style;
            applyChromeStyle(currentChromeStyle);
            console.log("[nc] Chrome style applied:", currentChromeStyle);
          }
          // Toggle indicator dot visibility
          if (typeof data.settings.show_indicator_dot === "boolean") {
            const dot = document.getElementById("status-dot");
            if (dot) {
              dot.style.display = data.settings.show_indicator_dot ? "" : "none";
            }
          }
          // Visual effects toggles
          const effectMap = [
            ["show_scanlines", ".scanlines"],
            ["show_grain", "#grain-canvas"],
            ["show_interference", "#interference-bars"],
            ["show_burst", "#burst-overlay"],
          ];
          for (const [key, selector] of effectMap) {
            if (typeof data.settings[key] === "boolean") {
              const el = document.querySelector(selector);
              if (el) el.style.display = data.settings[key] ? "" : "none";
            }
          }
          // Analog bleed — JS toggle
          if (typeof data.settings.show_analog_bleed === "boolean") {
            console.log("[nc] Analog bleed set to:", data.settings.show_analog_bleed);
            analogBleedEnabled = data.settings.show_analog_bleed;
            // Force redraw of last frame to apply/remove bleed immediately
            if (lastFrameBase64) {
              // Invalidate cache so it re-renders fresh
              frameImageCache.delete(lastFrameBase64);
              drawPortraitWithBleed(lastFrameBase64);
              console.log("[nc] Redrew last frame, bleed =", analogBleedEnabled);
            }
          }
          // Frame overlay style
          if (typeof data.settings.frame_style === "string") {
            frameStyle = data.settings.frame_style;
            console.log("[nc] Frame style set to:", frameStyle);
            redrawFrameOverlay();
            if (lastFrameBase64) {
              frameImageCache.delete(lastFrameBase64);
              drawPortraitWithBleed(lastFrameBase64);
            }
          }
          // Burst on expression change toggle
          if (typeof data.settings.show_burst_on_expr === "boolean") {
            showBurstOnExpr = data.settings.show_burst_on_expr;
            console.log("[nc] Burst on expression set to:", showBurstOnExpr);
          }
          // Colorize WebGL shader settings
          if (typeof data.settings.colorize_enabled === "boolean") {
            colorizeEnabled = data.settings.colorize_enabled;
            console.log("[nc] Colorize set to:", colorizeEnabled);
            if (lastFrameBase64) {
              frameImageCache.delete(lastFrameBase64);
              drawPortraitWithBleed(lastFrameBase64);
            }
          }
          if (typeof data.settings.colorize_color === "string") {
            const c = hexToRgb(data.settings.colorize_color);
            if (c) colorizeColor = c;
            console.log("[nc] Colorize color:", data.settings.colorize_color);
            if (lastFrameBase64 && colorizeEnabled) {
              frameImageCache.delete(lastFrameBase64);
              drawPortraitWithBleed(lastFrameBase64);
            }
          }
          if (typeof data.settings.colorize_strength === "number") {
            colorizeStrength = Math.max(0, Math.min(1, data.settings.colorize_strength));
            console.log("[nc] Colorize strength:", colorizeStrength);
            if (lastFrameBase64 && colorizeEnabled) {
              frameImageCache.delete(lastFrameBase64);
              drawPortraitWithBleed(lastFrameBase64);
            }
          }
        }
        break;
      case "character_switched":
        console.log("[nc] Character switched to:", data.name);
        if (data.request_id && pendingSwitchRequests.has(data.request_id)) {
          const req = pendingSwitchRequests.get(data.request_id);
          if (!req.rendererReported) {
            req.rendererReported = true;
            sendPerf("switch_roundtrip", {
              request_id: data.request_id,
              character: data.character,
              roundtrip_ms: Number((performance.now() - req.startedAt).toFixed(1)),
              buffered_amount: ws ? ws.bufferedAmount : 0,
            });
            if (req.controlReported) {
              pendingSwitchRequests.delete(data.request_id);
            } else {
              pendingSwitchRequests.set(data.request_id, req);
            }
          }
        }
        pendingCharacterSwitch = {
          character: data.character,
          startedAt: performance.now(),
          requestId: data.request_id || null,
        };
        if (data.name && charSelect) charSelect.value = data.character;
        updateFrequencyDisplay(data.character, data.name);
        if (data.display_mode) {
          currentDisplayMode = data.display_mode;
          console.log("[nc] Display mode:", currentDisplayMode);
        }
        // Update native sprite aspect ratio from server
        if (data.frame_width && data.frame_height) {
          if (data.frame_width !== nativeSpriteWidth || data.frame_height !== nativeSpriteHeight) {
            nativeSpriteWidth = data.frame_width;
            nativeSpriteHeight = data.frame_height;
            refreshSpriteSizes();
            // Re-apply current sprite size to use new aspect ratio
            const currentSize = spriteSizeSelect ? spriteSizeSelect.value : loadSpriteSize();
            if (currentSize) {
              applySpriteSize(currentSize);
            }
          }
        }
        break;

      case "set_sprite_size":
        // Handle sprite size change from settings popup
        console.log("[nc] Received set_sprite_size:", data.size);
        if (data.size) {
          console.log("[nc] Applying sprite size:", data.size);
          applySpriteSize(data.size);
          // Update the sprite size dropdown if it exists
          if (spriteSizeSelect) {
            spriteSizeSelect.value = data.size;
          }
        }
        break;

      case "text":
        if (data.text) {
          typewrite(data.text);
          if (data.expression && exprSelect) {
            exprSelect.value = data.expression;
          }
        }
        break;
      case "status":
        if (data.status === "idle") {
          updateStatus("connected");
          setCursorVisible(false);
        }
        else if (data.status === "thinking...") updateStatus("thinking");
        break;
      case "hermes_event":
        if (data.event_type === "thinking" || data.event_type === "tool_use") {
          updateStatus("thinking");
        } else if (data.event_type === "responding") {
          updateStatus("speaking");
        } else if (data.event_type === "complete") {
          updateStatus("connected");
        }
        break;
    }
  }

  function populateCharacters(characters, activeId) {
    if (!charSelect) return;
    charSelect.innerHTML = "";
    for (const c of characters) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      if (c.id === activeId) opt.selected = true;
      charSelect.appendChild(opt);
    }
  }

  function populateExpressions(expressions) {
    if (!exprSelect) return;
    exprSelect.innerHTML = "";
    for (const expr of expressions) {
      const opt = document.createElement("option");
      if (typeof expr === "object") { opt.value = expr.name; opt.textContent = expr.label; }
      else { opt.value = expr; opt.textContent = expr.replace(/_/g, " "); }
      exprSelect.appendChild(opt);
    }
  }

  // ─── Audio ───────────────────────────────────────────────

  function getPlayableAudioUrl(audioPath) {
    if (!audioPath) return null;
    const convertFileSrc = window.__TAURI__?.core?.convertFileSrc || window.__TAURI__?.tauri?.convertFileSrc;
    if (typeof convertFileSrc === "function") {
      return convertFileSrc(audioPath);
    }
    const normalized = audioPath.replace(/\\/g, "/");
    const prefixed = normalized.startsWith("/") ? normalized : "/" + normalized;
    return encodeURI("file://" + prefixed);
  }

  async function loadAudioViaTauri(audioPath) {
    const invoke = window.__TAURI__?.core?.invoke;
    if (typeof invoke !== "function" || !audioPath) {
      return null;
    }
    try {
      return await invoke("read_file_base64", { path: audioPath });
    } catch (err) {
      console.error("[nc] read_file_base64 failed:", err);
      return null;
    }
  }

  function handleAudio(base64Wav, audioPath, announcedDurationS) {
    // Deduplicate: if we've already queued audio within the last 500ms,
    // this is likely a fallback response. Skip to avoid double-play.
    const now = performance.now();
    if (now - _lastAudioCall < 500) {
      void frontendLog(`audio dedup skip (${Math.round(now - _lastAudioCall)}ms)`);
      return;
    }
    _lastAudioCall = now;
    const audioStart = performance.now();
    stopPlayback();
    startWaveViz();
    currentBuffer = null;
    audioFallbackRequested = false;

    if (audioPath && IS_TAURI_RUNTIME) {
      const playableUrl = getPlayableAudioUrl(audioPath);
      if (!playableUrl) {
        console.error("[nc] No playable URL for audio path:", audioPath);
        return;
      }

      const prepMs = performance.now() - audioStart;
      wavBytes = null;
      wavDuration = announcedDurationS || 0;
      drawWaveform();
      drawPlayhead(0);

      const audio = new Audio(playableUrl);
      audio.preload = "auto";
      audio.volume = playbackVolume;
      currentAudioElement = audio;

      audio.addEventListener("loadeddata", () => {
        const readyMs = performance.now() - audioStart;
        wavDuration = audio.duration || announcedDurationS || 0;
        sendPerf("audio_ready", {
          wav_bytes: 0,
          prep_ms: Number(prepMs.toFixed(1)),
          ready_ms: Number(readyMs.toFixed(1)),
          duration_s: Number((wavDuration || 0).toFixed(2)),
          transport: "path",
        });
        startPlaybackFrom(0);
        sendCommand("playback_started", {});
      }, { once: true });

      audio.addEventListener("error", () => {
        sendPerf("audio_path_failed", {
          wav_bytes: 0,
          prep_ms: Number(prepMs.toFixed(1)),
          error: "audio element load failed",
          transport: "path",
        });
        if (audioFallbackRequested) {
          return;
        }
        audioFallbackRequested = true;
        loadAudioViaTauri(audioPath).then((fallbackAudio) => {
          if (fallbackAudio) {
            handleAudio(fallbackAudio, null, announcedDurationS);
          } else {
            sendCommand("audio_fallback_request", {});
          }
        });
      }, { once: true });

      audio.load();
      return;
    }

    wavBytes = Uint8Array.from(atob(base64Wav), c => c.charCodeAt(0));
    const dv = new DataView(wavBytes.buffer);
    const sr = dv.getUint32(24, true);
    const ch = dv.getUint16(22, true);
    const bps = dv.getUint16(34, true);
    const ds = dv.getUint32(40, true);
    wavDuration = ds / (sr * ch * (bps / 8));

    if (audioInfo) {
      audioInfo.textContent = `${(wavBytes.length/1024).toFixed(0)}KB ${sr}Hz ${ch}ch ${bps}bit`;
    }
    if (audioPlayer) {
      audioPlayer.style.display = "flex";
    }

    drawWaveform();
    drawPlayhead(0);

    const prepMs = performance.now() - audioStart;
    pendingAudioPerf = {
      receivedAt: audioStart,
      wavBytes: wavBytes.length,
      prepMs,
    };

    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();

    audioCtx.decodeAudioData(wavBytes.buffer.slice(0), (buffer) => {
      currentBuffer = buffer;
      const readyMs = performance.now() - audioStart;
      sendPerf("audio_ready", {
        wav_bytes: wavBytes.length,
        prep_ms: Number(prepMs.toFixed(1)),
        ready_ms: Number(readyMs.toFixed(1)),
        duration_s: Number(buffer.duration.toFixed(2)),
      });
      // If context is suspended, resume it first so playback actually begins
      // before we tell the server to start animating.
      if (audioCtx.state === "suspended") {
        audioCtx.resume().then(() => {
          startPlaybackFrom(0);
          sendCommand("playback_started", {});
        }).catch((err) => {
          console.error("[nc] resume failed:", err);
          startPlaybackFrom(0);
          sendCommand("playback_started", {});
        });
      } else {
        startPlaybackFrom(0);
        sendCommand("playback_started", {});
      }
    }, (err) => {
      console.error("[nc] Decode failed:", err);
      sendPerf("audio_decode_failed", {
        wav_bytes: wavBytes.length,
        prep_ms: Number(prepMs.toFixed(1)),
        error: String(err),
      });
      sendCommand("playback_started", {});
    });
  }

  function startPlaybackFrom(offset) {
    if (currentSource) { try { currentSource.stop(); } catch(e) {} }
    if (currentAudioElement) {
      // Route audio element through analyser for wave reactivity
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === "suspended") audioCtx.resume();
        const mediaSource = audioCtx.createMediaElementSource(currentAudioElement);
        mediaSource.connect(ensureAnalyser());
        if (analyserNode) analyserNode.connect(getAudioGainNode());
        else mediaSource.connect(getAudioGainNode());
        currentAudioElement.volume = 1; // volume controlled by gain node
      } catch (e) {
        console.warn("[nc] Could not route audio element through analyser:", e);
        currentAudioElement.volume = playbackVolume;
      }
      currentAudioElement.currentTime = offset > 0 ? offset : 0;
      currentAudioElement.play().catch((err) => {
        console.error("[nc] audio element play failed:", err);
      });
      isPlaying = true;
      if (btnPlayPause) {
        btnPlayPause.textContent = "â¸";
      }

      currentAudioElement.onended = () => {
        isPlaying = false;
        if (btnPlayPause) {
          btnPlayPause.textContent = "â–¶";
        }
        if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null; }
      };

      if (playbackTimer) clearInterval(playbackTimer);
      playbackTimer = setInterval(() => {
        if (!isPlaying || !currentAudioElement) return;
        const pos = currentAudioElement.currentTime;
        const dur = currentAudioElement.duration || wavDuration || 0;
        if (audioTime) {
          audioTime.textContent = fmtTime(pos) + " / " + fmtTime(dur);
        }
        drawPlayhead(pos);
        sendCommand("playback_pos", { pos: pos });
      }, 100);
      return;
    }
    const source = audioCtx.createBufferSource();
    source.buffer = currentBuffer;
    source.connect(ensureAnalyser() || getAudioGainNode());
    if (analyserNode) analyserNode.connect(getAudioGainNode());
    source.start(0, offset > 0 ? offset : 0);
    playbackStartTime = audioCtx.currentTime - (offset > 0 ? offset : 0);
    currentSource = source;
    isPlaying = true;
    if (btnPlayPause) {
      btnPlayPause.textContent = "⏸";
    }

    source.onended = () => {
      isPlaying = false;
      if (btnPlayPause) {
        btnPlayPause.textContent = "▶";
      }
      if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null; }
    };

    if (playbackTimer) clearInterval(playbackTimer);
    playbackTimer = setInterval(() => {
      if (!isPlaying || !currentBuffer) return;
      const pos = audioCtx.currentTime - playbackStartTime;
      if (pos < currentBuffer.duration) {
        if (audioTime) {
          audioTime.textContent = fmtTime(pos) + " / " + fmtTime(currentBuffer.duration);
        }
        drawPlayhead(pos);
        sendCommand("playback_pos", { pos: pos });
      }
    }, 100);
  }

  function stopPlayback() {
    stopWaveViz();
    if (currentSource) { try { currentSource.stop(); } catch(e) {} currentSource = null; }
    if (currentAudioElement) {
      try { currentAudioElement.pause(); } catch(e) {}
      currentAudioElement = null;
    }
    isPlaying = false;
    if (btnPlayPause) btnPlayPause.textContent = "▶";
    if (playbackTimer) { clearInterval(playbackTimer); playbackTimer = null; }
  }

  // ─── Waveform ────────────────────────────────────────────

  function drawWaveform() {
    if (!wavBytes || !waveCtx || !waveformCanvas) return;
    const W = waveformCanvas.width;
    const H = waveformCanvas.height;
    waveCtx.fillStyle = "rgba(0,0,0,0.5)";
    waveCtx.fillRect(0, 0, W, H);

    const dv = new DataView(wavBytes.buffer);
    let off = 44;
    if (dv.getUint32(36, true) !== 0x61746164) {
      for (let i = 36; i < wavBytes.length - 8; i++) {
        if (dv.getUint32(i, true) === 0x61746164) { off = i + 8; break; }
      }
    }
    const bps = dv.getUint16(34, true);
    const b = bps / 8;
    const ch = dv.getUint16(22, true);
    const ns = Math.floor((wavBytes.length - off) / (b * ch));

    waveCtx.strokeStyle = "rgba(122,170,150,0.7)";
    waveCtx.lineWidth = 1;
    waveCtx.beginPath();
    for (let x = 0; x < W; x++) {
      const s0 = Math.floor(x * ns / W);
      const spp = Math.max(1, Math.floor(ns / W));
      let mn = 1, mx = -1;
      for (let s = 0; s < spp && (s0+s) < ns; s++) {
        const idx = off + (s0+s) * b * ch;
        let v;
        if (b === 2) v = dv.getInt16(idx, true) / 32768;
        else if (b === 4) v = dv.getFloat32(idx, true);
        else v = (wavBytes[idx] - 128) / 128;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      waveCtx.moveTo(x, (1-mx)*H/2);
      waveCtx.lineTo(x, (1-mn)*H/2);
    }
    waveCtx.stroke();
  }

  function drawPlayhead(t) {
    if (!wavBytes || !waveCtx || !waveformCanvas) return;
    drawWaveform();
    const x = Math.floor((t / wavDuration) * waveformCanvas.width);
    waveCtx.strokeStyle = "rgba(205,205,205,0.9)";
    waveCtx.lineWidth = 2;
    waveCtx.beginPath();
    waveCtx.moveTo(x, 0);
    waveCtx.lineTo(x, waveformCanvas.height);
    waveCtx.stroke();
  }

  // ─── Helpers ─────────────────────────────────────────────

  function fmtTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function updateStatus(state) {
    if (!statusDot) return;
    statusDot.className = "indicator";
    // Also update brand label state if it exists
    if (brandLabel) {
      brandLabel.classList.remove("state-speaking", "state-thinking", "state-disconnected");
    }
    switch (state) {
      case "speaking":
        statusDot.classList.add("speaking");
        if (brandLabel) brandLabel.classList.add("state-speaking");
        break;
      case "disconnected":
        statusDot.classList.add("disconnected");
        if (brandLabel) brandLabel.classList.add("state-disconnected");
        break;
      case "connecting":
      case "thinking":
        statusDot.classList.add("thinking");
        if (brandLabel) brandLabel.classList.add("state-thinking");
        break;
    }
  }

  function setStartupOverlay(visible, message) {
    if (startupMessage && typeof message === "string" && message.trim()) {
      startupMessage.textContent = message;
    }
    if (!startupOverlay) return;
    startupOverlay.classList.toggle("hidden", !visible);

    // Move frame overlay canvas into splash when visible, back to portrait when hidden
    const frameCanvas = document.getElementById("frame-overlay-canvas");
    if (frameCanvas) {
      if (visible) {
        // During splash: canvas renders inside splash overlay (above the text)
        if (frameCanvas.parentNode !== startupOverlay) {
          startupOverlay.appendChild(frameCanvas);
          frameCanvas.style.zIndex = "100";
        }
      } else {
        // After splash: canvas renders in portrait container (normal view)
        const portraitContainer = document.querySelector('.portrait-container');
        if (portraitContainer && frameCanvas.parentNode !== portraitContainer) {
          portraitContainer.appendChild(frameCanvas);
          frameCanvas.style.zIndex = "100";
        }
      }
    }
  }

  function normalizeCharacterKey(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  function updateFrequencyDisplay(characterId, characterName) {
    if (!freqDisplay) return;
    const keys = [characterId, characterName].map(normalizeCharacterKey);
    for (const key of keys) {
      if (key && CHARACTER_CODEC_FREQUENCIES[key]) {
        freqDisplay.textContent = CHARACTER_CODEC_FREQUENCIES[key];
        return;
      }
    }
    if (CHARACTER_CODEC_FREQUENCIES.default) {
      freqDisplay.textContent = CHARACTER_CODEC_FREQUENCIES.default;
    }
  }

  function setCursorVisible(visible) {
    if (!cursor) return;
    cursor.classList.toggle("hidden", !visible);
  }

  function stopTypewriter() {
    if (typewriterTimer) {
      clearInterval(typewriterTimer);
      typewriterTimer = null;
    }
  }

  function typewrite(text) {
    stopTypewriter();
    if (!textContent) return;
    textContent.textContent = "";
    setCursorVisible(true);
    let i = 0;
    const speed = Math.round(35 * 1.25);
    typewriterTimer = setInterval(() => {
      if (i < text.length) {
        textContent.textContent += text[i];
        i++;
      } else {
        stopTypewriter();
        setCursorVisible(false);
      }
    }, speed);
  }

  // ─── Visual Effects ──────────────────────────────────────

  // Open settings popup window
  async function openSettingsWindow() {
    try {
      if (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke) {
        await window.__TAURI__.core.invoke('open_settings_window');
        console.log("[nc] Opened settings window via Tauri");
      } else {
        console.log("[nc] Tauri API not available, falling back to window.open");
        window.open('settings.html', 'nous-settings', 'width=187,height=400,resizable=no,scrollbars=no');
      }
    } catch (e) {
      console.log("[nc] Failed to open settings window:", e);
      window.open('settings.html', 'nous-settings', 'width=187,height=400,resizable=no,scrollbars=no');
    }
  }

  async function closeApp() {
    try {
      if (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke) {
        await window.__TAURI__.core.invoke('close_app');
      } else {
        window.close();
      }
    } catch (e) {
      console.log("[nc] Failed to close app via Tauri:", e);
      window.close();
    }
  }

  // Sprite size configurations
  // Native sprite dimensions come from the server per-character
  let nativeSpriteWidth = 342;
  let nativeSpriteHeight = 512;
  let spriteDimensionsReady = false;  // set true when server sends frame_width/frame_height

  const SPRITE_SIZES = {
    "big": null,
    "medium": null,
    "small": null,
  };

  function refreshSpriteSizes() {
    const aspect = nativeSpriteWidth / nativeSpriteHeight;
    const bigW = Math.round(267 * aspect);
    const medW = Math.round(150 * aspect);
    const smallW = Math.round(89 * aspect);
    SPRITE_SIZES["big"] = { width: bigW, height: 267, stretched: false };
    SPRITE_SIZES["medium"] = { width: medW, height: 150, stretched: false };
    SPRITE_SIZES["small"] = { width: smallW, height: 89, stretched: false };
    console.log(`[nc] Sprite sizes refreshed: native=${nativeSpriteWidth}x${nativeSpriteHeight}, aspect=${aspect.toFixed(3)}`);
  }
  refreshSpriteSizes();
  
  // Load saved sprite size from localStorage
  function loadSpriteSize() {
    return localStorage.getItem('nous-sprite-size') || localStorage.getItem('codec-sprite-size') || 'big';
  }
  
  // Save sprite size to localStorage
  function saveSpriteSize(sizeKey) {
    localStorage.setItem('nous-sprite-size', sizeKey);
  }

  function applySpriteSize(sizeKey) {
    const size = SPRITE_SIZES[sizeKey];
    if (!size) {
      console.log("[nc] Unknown sprite size:", sizeKey);
      return;
    }

    console.log("[nc] Applying sprite size:", sizeKey, size);

    // Save to localStorage
    saveSpriteSize(sizeKey);

    // Track current portrait width for window resize calculations
    currentPortraitWidth = size.width;

    // Update canvas dimensions
    portraitCanvas.width = size.width;
    portraitCanvas.height = size.height;
    
    // Update grain and burst canvases to match
    grainCanvas.width = size.width;
    grainCanvas.height = size.height;
    if (burstCanvas) {
      burstCanvas.width = size.width;
      burstCanvas.height = size.height;
    }
    initColorize(size.width, size.height);
    initFrameOverlay(size.width, size.height);

    // Redraw last cached frame instantly (no blank frame)
    if (lastFrameBase64) {
      drawPortraitWithBleed(lastFrameBase64);
    }
    
    // Update CSS for portrait container
    const portraitContainer = document.querySelector('.portrait-container');
    portraitContainer.style.height = size.height + 'px';
    portraitContainer.classList.remove('size-big', 'size-medium', 'size-small');
    const sizeClass = sizeKey.startsWith('big') ? 'size-big' : sizeKey.startsWith('medium') ? 'size-medium' : 'size-small';
    portraitContainer.classList.add(sizeClass);
    currentSpriteSizeKey = sizeKey;
    if (spriteSizeSelect) spriteSizeSelect.value = sizeKey;
    
    // Update CSS for portrait canvas
    portraitCanvas.style.width = size.width + 'px';
    portraitCanvas.style.height = size.height + 'px';
    console.log(`[nc] Set portrait canvas CSS: ${portraitCanvas.style.width} x ${portraitCanvas.style.height}`);
    
    // Update CSS for grain canvas
    grainCanvas.style.width = size.width + 'px';
    grainCanvas.style.height = size.height + 'px';
    
    // Update CSS for burst canvas
    if (burstCanvas) {
      burstCanvas.style.width = size.width + 'px';
      burstCanvas.style.height = size.height + 'px';
    }

    // Update companion container width to match portrait
    const companion = document.getElementById('companion');
    if (companion) companion.style.width = size.width + 'px';

    // Resize Tauri window
    syncWindowSize(size.height);
    applyHermesLayout();
    repositionWaveViz();
    
    console.log(`[nc] Sprite size changed to ${sizeKey}: ${size.width}x${size.height}`);
  }

  // Draw portrait with horizontal analog bleed (SCART RGB simulation)
  function drawPortraitWithBleed(base64Frame) {
    if (!portraitCtx) {
      console.log("[nc] portraitCtx not available");
      return;
    }

    const cachedImg = frameImageCache.get(base64Frame);
    if (cachedImg) {
      touchFrameCache(base64Frame, cachedImg);
      renderDecodedPortrait(cachedImg, {
        decodeMs: 0,
        cacheHit: true,
        frameChars: base64Frame.length,
      });
      return;
    }

    pendingFrameBase64 = base64Frame;
    if (frameDecodeInFlight) {
      return;
    }

    decodeLatestPortraitFrame();
  }

  function decodeLatestPortraitFrame() {
    if (!pendingFrameBase64) {
      return;
    }

    const frameToDraw = pendingFrameBase64;
    const decodeStart = performance.now();
    pendingFrameBase64 = null;
    frameDecodeInFlight = true;

    // If decode takes too long (e.g. large base64, GPU stall),
    // reset the flag so new frames can attempt processing.
    const DECODE_TIMEOUT_MS = 5000;
    let decodeTimedOut = false;
    const decodeTimeout = setTimeout(() => {
      if (frameDecodeInFlight) {
        decodeTimedOut = true;
        frameDecodeInFlight = false;
        console.log("[nc] Portrait decode timed out after 5s, resetting");
        if (pendingFrameBase64) {
          decodeLatestPortraitFrame();
        }
      }
    }, DECODE_TIMEOUT_MS);

    const img = new Image();
    img.onload = () => {
      clearTimeout(decodeTimeout);
      if (decodeTimedOut) return; // already handled by timeout
      frameDecodeInFlight = false;
      touchFrameCache(frameToDraw, img);
      if (pendingFrameBase64) {
        decodeLatestPortraitFrame();
      } else {
        renderDecodedPortrait(img, {
          decodeMs: performance.now() - decodeStart,
          cacheHit: false,
          frameChars: frameToDraw.length,
        });
      }
    };
    img.onerror = () => {
      clearTimeout(decodeTimeout);
      frameDecodeInFlight = false;
      console.log("[nc] Portrait image failed to load");
      if (pendingFrameBase64) {
        decodeLatestPortraitFrame();
      }
    };
    img.src = "data:image/png;base64," + frameToDraw;
  }

  function touchFrameCache(key, img) {
    if (frameImageCache.has(key)) {
      frameImageCache.delete(key);
    }
    frameImageCache.set(key, img);
    if (frameImageCache.size > FRAME_IMAGE_CACHE_LIMIT) {
      const oldestKey = frameImageCache.keys().next().value;
      frameImageCache.delete(oldestKey);
    }
  }

  function renderDecodedPortrait(img, perfInfo) {
    if (!portraitCtx || !portraitCanvas) return;
    const renderStart = performance.now();

    const cw = portraitCanvas.width;
    const ch = portraitCanvas.height;
    const iw = img.width;
    const ih = img.height;

    let dx, dy, dw, dh;

    switch (currentDisplayMode) {
      case "fit": {
        const scale = Math.min(cw / iw, ch / ih);
        dw = iw * scale;
        dh = ih * scale;
        dx = (cw - dw) / 2;
        dy = (ch - dh) / 2;
        break;
      }
      case "cover": {
        const scale = Math.max(cw / iw, ch / ih);
        dw = iw * scale;
        dh = ih * scale;
        dx = (cw - dw) / 2;
        dy = (ch - dh) / 2;
        break;
      }
      case "original": {
        dw = iw;
        dh = ih;
        dx = (cw - dw) / 2;
        dy = (ch - dh) / 2;
        break;
      }
      case "stretch":
      default: {
        dx = 0;
        dy = 0;
        dw = cw;
        dh = ch;
        break;
      }
    }

    portraitCtx.clearRect(0, 0, cw, ch);
    portraitCtx.globalAlpha = 1.0;
    const src = colorizeEnabled ? applyColorize(img) : img;
    portraitCtx.drawImage(src, dx, dy, dw, dh);
    // Interference bars — drawn on canvas for overlay blending with character
    drawInterference(portraitCtx, cw, ch);
    // Frame overlay drawn on separate canvas on top
    if (analogBleedEnabled) {
      portraitCtx.globalAlpha = 0.20;
      portraitCtx.drawImage(src, dx - 2, dy, dw, dh);
      portraitCtx.drawImage(src, dx + 2, dy, dw, dh);
    }
    portraitCtx.globalAlpha = 1.0;

    const renderMs = performance.now() - renderStart;
    const decodeMs = perfInfo?.decodeMs ?? 0;
    const totalMs = decodeMs + renderMs;
    if (pendingCharacterSwitch) {
      sendPerf("switch_to_first_frame", {
        character: pendingCharacterSwitch.character,
        request_id: pendingCharacterSwitch.requestId,
        ms: Number((performance.now() - pendingCharacterSwitch.startedAt).toFixed(1)),
        cache_hit: !!perfInfo?.cacheHit,
      });
      pendingCharacterSwitch = null;
    }
    if (totalMs > 100) {
      sendPerf("frame_render_slow", {
        cache_hit: !!perfInfo?.cacheHit,
        frame_chars: perfInfo?.frameChars || 0,
        decode_ms: Number(decodeMs.toFixed(1)),
        render_ms: Number(renderMs.toFixed(1)),
        total_ms: Number(totalMs.toFixed(1)),
      });
    }
  }

  // Film grain effect - procedural, flickering pixels
  let grainFrame = 0;

  function initGrain() {
    if (!grainCanvas) return;
    requestAnimationFrame(updateGrain);
  }

  function updateGrain() {
    if (!grainCtx) return;
    grainFrame++;

    // Grain is purely decorative, so keep it on a low update budget.
    if (grainFrame % GRAIN_FRAME_SKIP === 0) {
      const w = grainCanvas.width;
      const h = grainCanvas.height;
      const blockSize = GRAIN_BLOCK_SIZE;
      
      grainCtx.clearRect(0, 0, w, h);
      
      // Uniform noise across entire canvas - not sparse bright spots
      for (let y = 0; y < h; y += blockSize) {
        for (let x = 0; x < w; x += blockSize) {
          // Random value for each block - creates dither pattern
          const noise = Math.random();
          // Subtle variation: very low opacity differences
          if (noise > 0.55) {
            // Slightly bright
            grainCtx.fillStyle = "rgba(255,255,255,0.18)";
            grainCtx.fillRect(x, y, blockSize, blockSize);
          } else if (noise < 0.45) {
            // Slightly dark
            grainCtx.fillStyle = "rgba(0,0,0,0.10)";
            grainCtx.fillRect(x, y, blockSize, blockSize);
          }
          // 45-55% range = no grain (transparent)
        }
      }
    }

    requestAnimationFrame(updateGrain);
  }

  // Intermittent interference bars — rendered on canvas for proper overlay blending
  let interferenceBars = [];
  let interferenceNextId = 0;

  function initInterference() {
    scheduleNextBar();
  }

  function scheduleNextBar() {
    const delay = 8000 + Math.random() * 12000; // 8-20 seconds
    setTimeout(() => {
      spawnInterferenceBar();
      scheduleNextBar();
    }, delay);
  }

  function spawnInterferenceBar() {
    // Weighted random: 70% 1 bar, 25% 2 bars, 5% 3 bars
    const r = Math.random();
    const count = r < 0.70 ? 1 : (r < 0.95 ? 2 : 3);
    for (let i = 0; i < count; i++) {
      let height;
      if (count === 2) {
        // For 2 bars, ensure clearly different sizes
        if (i === 0) {
          height = 14 + Math.floor(Math.random() * 14); // 14-27px (smaller)
        } else {
          height = 28 + Math.floor(Math.random() * 13); // 28-40px (larger)
        }
      } else {
        height = 14 + Math.floor(Math.random() * 26); // 14-40px
      }
      const duration = (4 + Math.random() * 3); // 4-7s
      const barId = interferenceNextId++;
      interferenceBars.push({
        id: barId,
        height: height,
        y: -height - 10, // start above canvas
        startY: -height - 10,
        endY: portraitCanvas ? portraitCanvas.height + 10 : 277,
        opacity: 0,
        progress: 0,
        startTime: performance.now() + (i * 300), // stagger by 300ms
        duration: duration * 1000,
        expired: false,
      });
      // Cleanup expired bars after animation
      setTimeout(() => {
        const idx = interferenceBars.findIndex(b => b.id === barId);
        if (idx >= 0) interferenceBars[idx].expired = true;
      }, (duration + 1) * 1000);
    }
    startInterferenceLoop();
  }

  function drawInterference(ctx, cw, ch) {
    const now = performance.now();
    // Filter out expired bars
    interferenceBars = interferenceBars.filter(b => !b.expired);

    let anyActive = false;
    for (const bar of interferenceBars) {
      const elapsed = now - bar.startTime;
      if (elapsed < 0) continue; // not yet started

      bar.progress = Math.min(1, elapsed / bar.duration);

      // Fade in, scroll, fade out
      let alpha = 0;
      if (bar.progress < 0.05) {
        alpha = bar.progress / 0.05;
      } else if (bar.progress < 0.95) {
        alpha = 0.6;
      } else {
        alpha = 0.6 * (1 - (bar.progress - 0.95) / 0.05);
      }

      // Y position: interpolate from startY to endY
      bar.y = bar.startY + (bar.endY - bar.startY) * bar.progress;

      if (alpha > 0 && bar.y + bar.height > 0 && bar.y < ch) {
        anyActive = true;
        ctx.save();
        ctx.globalCompositeOperation = 'soft-light';
        ctx.globalAlpha = alpha;
        ctx.fillStyle = 'rgba(255, 255, 255, 1)';
        ctx.fillRect(0, bar.y, cw, bar.height);
        ctx.restore();
      }
    }
    return anyActive;
  }

  // Independent animation loop for interference bars (runs even when no frames arrive)
  let interferenceAnimId = null;
  function startInterferenceLoop() {
    if (interferenceAnimId) return;
    function tick() {
      const active = interferenceBars.length > 0;
      if (active && lastFrameBase64) {
        // Redraw the last frame to update bar positions
        // Don't delete cache — the cache hit path calls renderDecodedPortrait directly
        drawPortraitWithBleed(lastFrameBase64);
      }
      if (active || interferenceBars.length > 0) {
        interferenceAnimId = requestAnimationFrame(tick);
      } else {
        interferenceAnimId = null;
      }
    }
    interferenceAnimId = requestAnimationFrame(tick);
  }

  // Heavy burst effect for character switches
  let burstOverlay, burstCtx;
  let burstActive = false;
  let burstFrame = 0;
  let burstSubtle = false;

  function initBurst() {
    burstOverlay = document.getElementById("burst-overlay");
    burstCanvas = document.getElementById("burst-canvas");
    if (!burstCanvas) return;
    burstCtx = burstCanvas.getContext("2d");
  }

  function triggerBurst(subtle) {
    if (!burstOverlay || !burstCtx) return;
    burstActive = true;
    burstFrame = 0;
    burstSubtle = !!subtle;
    burstOverlay.classList.add("active");
    requestAnimationFrame(updateBurst);
  }

  function updateBurst() {
    if (!burstActive || !burstCtx) return;
    burstFrame++;

    const w = burstCanvas.width;
    const h = burstCanvas.height;
    
    // Clear canvas
    burstCtx.clearRect(0, 0, w, h);
    
    // Keep the burst short and cheap; it's just a visual accent.
    const intensity = Math.max(0, 1 - (burstFrame / BURST_FRAME_COUNT));
    const subScale = burstSubtle ? 0.45 : 1.0;  // subtle mode: ~half
    
    // Heavy static noise - main visual element
    burstCtx.fillStyle = `rgba(255,255,255,${0.5 * intensity * subScale})`;
    for (let i = 0; i < BURST_NOISE_COUNT; i++) {
      const x = Math.random() * w;
      const y = Math.random() * h;
      const size = 1 + Math.floor(Math.random() * 3);
      burstCtx.fillRect(x, y, size, size);
    }
    
    // Moderate horizontal bars
    const barCount = BURST_BAR_MIN + Math.floor(Math.random() * BURST_BAR_RANGE);
    burstCtx.fillStyle = `rgba(255,255,255,${0.6 * intensity * subScale})`;
    for (let b = 0; b < barCount; b++) {
      const barTop = Math.floor(Math.random() * h);
      const barHeight = 2 + Math.floor(Math.random() * 10);
      const scrollOffset = (burstFrame * 5) % h;
      const y = (barTop + scrollOffset) % h;
      burstCtx.fillRect(0, y, w, barHeight);
    }

    if (burstFrame < BURST_FRAME_COUNT) {
      requestAnimationFrame(updateBurst);
    } else {
      burstActive = false;
      burstOverlay.classList.remove("active");
      burstCtx.clearRect(0, 0, w, h);
    }
  }

  // Unified window resize — call whenever portrait size or settings state changes.
  // Tauri v2: invoke lives at window.__TAURI__.core.invoke (requires withGlobalTauri: true).
  async function syncWindowSize(portraitHeight) {
    if (typeof window.__TAURI__ === 'undefined') {
      console.log("[nc] window.__TAURI__ not available — is withGlobalTauri set in tauri.conf.json?");
      return;
    }

    const invoke = window.__TAURI__.core?.invoke;
    if (!invoke) {
      console.log("[nc] window.__TAURI__.core.invoke not found");
      return;
    }

    const settingsOpen = settingsPanel ? settingsPanel.classList.contains("open") : false;

    // If portraitHeight wasn't passed, infer from canvas
    if (portraitHeight === undefined) {
      portraitHeight = portraitCanvas ? portraitCanvas.height : 267;
    }

    const totalWidth  = currentPortraitWidth + (settingsOpen ? 187 : 0) + WINDOW_WIDTH_PAD;
    const totalHeight = portraitHeight + WINDOW_HEIGHT_PAD; // keep a tiny safety margin for release webviews

    try {
      await invoke('resize_window', { width: totalWidth, height: totalHeight });
      console.log(`[nc] Window resized to ${totalWidth}x${totalHeight} (settings ${settingsOpen ? 'open' : 'closed'})`);
    } catch (e) {
      console.log("[nc] resize_window failed:", e);
    }
  }

  // ─── Frame Overlay Canvas ────────────────────────────────

  function initFrameOverlay(width, height) {
    let el = document.getElementById("frame-overlay-canvas");
    if (!el) {
      el = document.createElement("canvas");
      el.id = "frame-overlay-canvas";
      el.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:100;width:100%;height:100%';
      const container = document.querySelector('.portrait-container');
      if (container) container.appendChild(el);
    }
    frameCanvas = el;
    if (frameCanvas.width !== width || frameCanvas.height !== height) {
      frameCanvas.width = width;
      frameCanvas.height = height;
    }
    frameCtx = frameCanvas.getContext('2d');
    frameNeedsRedraw = true;
    redrawFrameOverlay();
  }

  function redrawFrameOverlay() {
    if (!frameCtx || !frameCanvas) return;
    const cw = frameCanvas.width;
    const ch = frameCanvas.height;
    frameCtx.clearRect(0, 0, cw, ch);

    if (frameStyle === "none" || !frameStyle) return;

    if (frameStyle === "brackets") {
      const t = FRAME_THICKNESS;
      const b = BRACKET_LENGTH;
      frameCtx.fillStyle = 'rgba(0, 0, 0, 0.55)';
      frameCtx.fillRect(0, 0, cw, t);
      frameCtx.fillRect(0, ch - t, cw, t);
      frameCtx.fillRect(0, 0, t, ch);
      frameCtx.fillRect(cw - t, 0, t, ch);
      frameCtx.strokeStyle = '#ffe6cb';
      frameCtx.lineWidth = 2;
      frameCtx.beginPath();
      frameCtx.moveTo(cw - t - b, t);
      frameCtx.lineTo(cw - t, t);
      frameCtx.lineTo(cw - t, t + b);
      frameCtx.stroke();
      frameCtx.beginPath();
      frameCtx.moveTo(t + b, ch - t);
      frameCtx.lineTo(t, ch - t);
      frameCtx.lineTo(t, ch - t - b);
      frameCtx.stroke();
      return;
    }

    let color = '#ffe6cb';
    if (frameStyle === "white") color = '#ffffff';
    else if (frameStyle === "black") color = '#000000';
    else if (frameStyle === "creme") color = '#ffe6cb';

    frameCtx.strokeStyle = color;
    frameCtx.lineWidth = 1;
    frameCtx.strokeRect(0.5, 0.5, cw - 1, ch - 1);
  }

  const COLORIZE_VS = `
    attribute vec2 a_position;
    attribute vec2 a_texCoord;
    varying vec2 v_texCoord;
    void main() {
      gl_Position = vec4(a_position, 0.0, 1.0);
      v_texCoord = a_texCoord;
    }
  `;

  const COLORIZE_FS = `
    precision mediump float;
    varying vec2 v_texCoord;
    uniform sampler2D u_texture;
    uniform vec3 u_color;
    uniform float u_strength;
    void main() {
      vec4 texColor = texture2D(u_texture, v_texCoord);
      float lum = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));
      vec3 colorized = vec3(lum) * u_color;
      gl_FragColor = vec4(mix(texColor.rgb, colorized, u_strength), texColor.a);
    }
  `;

  function initColorize(width, height) {
    if (!colorizeGl) {
      colorizeCanvas = document.createElement('canvas');
      colorizeGl = colorizeCanvas.getContext('webgl');
      if (!colorizeGl) {
        console.log("[nc] WebGL not available, colorize disabled");
        return;
      }
      console.log("[nc] WebGL context created, canvas size:", width, "x", height);
      // Compile shaders
      const vs = glCompile(colorizeGl, colorizeGl.VERTEX_SHADER, COLORIZE_VS);
      const fs = glCompile(colorizeGl, colorizeGl.FRAGMENT_SHADER, COLORIZE_FS);
      if (!vs || !fs) {
        console.log("[nc] WebGL shader compilation failed");
        colorizeGl = null;
        return;
      }
      colorizeProgram = colorizeGl.createProgram();
      colorizeGl.attachShader(colorizeProgram, vs);
      colorizeGl.attachShader(colorizeProgram, fs);
      colorizeGl.linkProgram(colorizeProgram);
      if (!colorizeGl.getProgramParameter(colorizeProgram, colorizeGl.LINK_STATUS)) {
        console.log("[nc] WebGL shader link failed:", colorizeGl.getProgramInfoLog(colorizeProgram));
        colorizeGl = null;
        return;
      }
      colorizeGl.useProgram(colorizeProgram);

      // Full-screen quad (triangle strip)
      const positions = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
      const posBuf = colorizeGl.createBuffer();
      colorizeGl.bindBuffer(colorizeGl.ARRAY_BUFFER, posBuf);
      colorizeGl.bufferData(colorizeGl.ARRAY_BUFFER, positions, colorizeGl.STATIC_DRAW);
      const posLoc = colorizeGl.getAttribLocation(colorizeProgram, 'a_position');
      colorizeGl.enableVertexAttribArray(posLoc);
      colorizeGl.vertexAttribPointer(posLoc, 2, colorizeGl.FLOAT, false, 0, 0);

      const texCoords = new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]);
      const texBuf = colorizeGl.createBuffer();
      colorizeGl.bindBuffer(colorizeGl.ARRAY_BUFFER, texBuf);
      colorizeGl.bufferData(colorizeGl.ARRAY_BUFFER, texCoords, colorizeGl.STATIC_DRAW);
      const texLoc = colorizeGl.getAttribLocation(colorizeProgram, 'a_texCoord');
      colorizeGl.enableVertexAttribArray(texLoc);
      colorizeGl.vertexAttribPointer(texLoc, 2, colorizeGl.FLOAT, false, 0, 0);

      // Uniform locations
      colorizeGl.uniform1i(colorizeGl.getUniformLocation(colorizeProgram, 'u_texture'), 0);
      // Store color/strength uniform locs on the gl context for fast access
      colorizeGl._colorLoc = colorizeGl.getUniformLocation(colorizeProgram, 'u_color');
      colorizeGl._strengthLoc = colorizeGl.getUniformLocation(colorizeProgram, 'u_strength');
    }

    // Resize canvas if needed
    if (colorizeCanvas.width !== width || colorizeCanvas.height !== height) {
      colorizeCanvas.width = width;
      colorizeCanvas.height = height;
      colorizeGl.viewport(0, 0, width, height);
    }
  }

  function hexToRgb(hex) {
    // #rrggbb → [r, g, b] floats 0–1
    const m = /^#?([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i.exec(hex);
    return m ? [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255] : null;
  }

  function glCompile(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  }

  function applyColorize(img) {
    if (!colorizeGl || !colorizeProgram) {
      console.log("[nc] applyColorize: no GL context, falling back to raw img");
      return img;
    }
    const gl = colorizeGl;

    // Draw image to a temp 2D canvas first, then upload that as WebGL texture
    // This is more reliable across browsers than texImage2D(..., HTMLImageElement)
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = img.naturalWidth || img.width;
    tempCanvas.height = img.naturalHeight || img.height;
    const tempCtx = tempCanvas.getContext('2d');
    tempCtx.drawImage(img, 0, 0);

    // Reuse one texture
    if (!colorizeTexture) {
      colorizeTexture = gl.createTexture();
    }
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, colorizeTexture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, tempCanvas);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    gl.uniform3f(gl._colorLoc, colorizeColor[0], colorizeColor[1], colorizeColor[2]);
    gl.uniform1f(gl._strengthLoc, colorizeStrength);

    gl.clearColor(0.0, 0.0, 0.0, 0.0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    const err = gl.getError();
    if (err !== gl.NO_ERROR) {
      console.log("[nc] WebGL error:", err);
    }

    return colorizeCanvas;
  }

  // Initialize effects on DOM ready
  const origInit = init;
  init = function() {
    origInit();
    startMainThreadMonitor();
    initGrain();
    initInterference();
    initBurst();
    initColorize(portraitCanvas ? portraitCanvas.width : 187, portraitCanvas ? portraitCanvas.height : 267);
    initFrameOverlay(portraitCanvas ? portraitCanvas.width : 187, portraitCanvas ? portraitCanvas.height : 267);
  };

  // Hook into character switch to trigger burst
  const origHandleEvent = handleEvent;
  handleEvent = function(data) {
    if (data.type === "character_switched") {
      triggerBurst();
    }
    origHandleEvent(data);
  };

  // ─── Boot ────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
