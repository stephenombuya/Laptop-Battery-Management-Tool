/**
 * renderer.js — BatteryOS Renderer Process
 * =========================================
 * Bridges live data from the Electron main process (via window.batteryOS)
 * into the BatteryOS dashboard state object defined in index.html.
 *
 * This file is loaded as a <script> tag at the bottom of index.html, after
 * the dashboard's own inline script has already defined `state`, `init()`,
 * and all update helpers.
 *
 * Data flow
 * ---------
 *  Python core-service
 *    → stdout JSON lines
 *      → Electron main process (main.js)
 *        → ipcRenderer push ("battery:snapshot-update")
 *          → preload.js contextBridge (window.batteryOS.onSnapshotUpdate)
 *            → this file (applySnapshot)
 *              → dashboard state + UI helpers
 */

"use strict";

// ---------------------------------------------------------------------------
// Guard: check the bridge is present (won't be in a plain browser)
// ---------------------------------------------------------------------------

if (!window.batteryOS) {
  console.warn(
    "window.batteryOS is not defined — running outside Electron. " +
    "The simulation mode from index.html will be used instead."
  );
}

// ---------------------------------------------------------------------------
// Apply a snapshot from the backend into the dashboard state
// ---------------------------------------------------------------------------

/**
 * @param {import('./preload').BatterySnapshot} snapshot
 */
function applySnapshot(snapshot) {
  if (!snapshot || typeof snapshot.percent !== "number") return;

  // Map backend fields → dashboard state
  state.pct      = Math.round(snapshot.percent);
  state.charging = Boolean(snapshot.charging);

  if (typeof snapshot.temperature_celsius === "number") {
    state.temp = Math.round(snapshot.temperature_celsius);
  }
  if (typeof snapshot.health_percent === "number") {
    state.health = Math.round(snapshot.health_percent);
  }
  if (typeof snapshot.cycle_count === "number") {
    state.cycles = snapshot.cycle_count;
    document.getElementById("cyclesVal").textContent = snapshot.cycle_count;
  }
  if (typeof snapshot.voltage_volts === "number") {
    document.getElementById("voltageVal").textContent =
      snapshot.voltage_volts.toFixed(1) + "V";
  }
  if (typeof snapshot.power_watts === "number") {
    const sign = snapshot.charging ? "+" : "";
    document.getElementById("powerDraw").textContent =
      sign + Math.abs(snapshot.power_watts).toFixed(1) + "W";
  }
  if (snapshot.time_left_seconds != null && snapshot.time_left_seconds > 0) {
    const h = Math.floor(snapshot.time_left_seconds / 3600);
    const m = Math.floor((snapshot.time_left_seconds % 3600) / 60);
    document.getElementById("timeLeft").textContent = `${h}h ${m}m`;
  }

  // Push % into history and refresh chart
  state.history.push(state.pct);
  if (state.history.length > 30) state.history.shift();

  // Stop the dashboard's own simulation ticker — real data is now flowing
  stopSimulation();

  // Refresh all visual elements
  updateBatteryVisual();
  renderChart();
}

// ---------------------------------------------------------------------------
// Stop the built-in simulation when real data arrives
// ---------------------------------------------------------------------------

let _simulationStopped = false;

function stopSimulation() {
  if (_simulationStopped) return;
  _simulationStopped = true;

  // The inline script sets up setInterval for simulateTick — clear it
  if (window._simulationTimer) {
    clearInterval(window._simulationTimer);
    window._simulationTimer = null;
    logEvent("success", "Live data connected — simulation mode disabled.");
  }
}

// ---------------------------------------------------------------------------
// Threshold sync: push slider changes back to the backend
// ---------------------------------------------------------------------------

async function syncThresholds(min, max) {
  if (!window.batteryOS) return;
  try {
    await window.batteryOS.setThresholds(min, max);
  } catch (err) {
    console.error("Failed to sync thresholds:", err);
    logEvent("danger", `Failed to update thresholds: ${err.message}`);
  }
}

// Intercept the slider input handlers added by index.html and also call syncThresholds
const _origMaxInput = document.getElementById("maxSlider").oninput;
document.getElementById("maxSlider").addEventListener("change", () => {
  syncThresholds(state.minLimit, state.maxLimit);
});

const _origMinInput = document.getElementById("minSlider").oninput;
document.getElementById("minSlider").addEventListener("change", () => {
  syncThresholds(state.minLimit, state.maxLimit);
});

// ---------------------------------------------------------------------------
// Wire up charging toggle to the real backend
// ---------------------------------------------------------------------------

const _origToggleCharging = window.toggleCharging;
window.toggleCharging = async function () {
  if (window.batteryOS) {
    try {
      if (state.charging) {
        await window.batteryOS.stopCharging();
        logEvent("warn", "Charging stopped via Electron IPC.");
      } else {
        await window.batteryOS.startCharging();
        logEvent("success", "Charging resumed via Electron IPC.");
      }
    } catch (err) {
      logEvent("danger", `IPC error: ${err.message}`);
    }
  }
  // Also update the UI immediately (backend will confirm on next snapshot)
  if (_origToggleCharging) _origToggleCharging();
};

// ---------------------------------------------------------------------------
// Subscribe to live snapshots
// ---------------------------------------------------------------------------

if (window.batteryOS) {
  // Subscribe to pushed updates
  const unsubscribe = window.batteryOS.onSnapshotUpdate(applySnapshot);

  // Also pull an immediate snapshot on load
  window.batteryOS.getSnapshot().then((snap) => {
    if (snap && snap.percent != null) {
      applySnapshot(snap);
    }
  });

  // Clean up listener if the window is ever torn down
  window.addEventListener("unload", unsubscribe);

  // Show platform info from config
  window.batteryOS.getConfig().then(({ platform }) => {
    const map = { darwin: "macOS", win32: "Windows", linux: "Linux" };
    const name = map[platform] || platform;
    document.getElementById("platformVal").textContent = name;
    logEvent("info", `Electron renderer connected — platform: ${name}`);
  });
}
