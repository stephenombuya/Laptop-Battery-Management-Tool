/**
 * preload.js — BatteryOS Context Bridge
 * ======================================
 * Exposes a minimal, typed API surface to the renderer via contextBridge.
 * The renderer never touches ipcRenderer directly — all communication
 * flows through window.batteryOS.
 */

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

/**
 * @typedef {object} BatterySnapshot
 * @property {number}         percent
 * @property {boolean}        charging
 * @property {boolean}        plugged_in
 * @property {number|null}    time_left_seconds
 * @property {number|null}    power_watts
 * @property {number|null}    temperature_celsius
 * @property {number|null}    health_percent
 * @property {number|null}    cycle_count
 * @property {number|null}    voltage_volts
 * @property {number}         timestamp
 */

contextBridge.exposeInMainWorld("batteryOS", {
  /**
   * Request the latest battery snapshot from the main process.
   * @returns {Promise<BatterySnapshot>}
   */
  getSnapshot: () => ipcRenderer.invoke("battery:get-snapshot"),

  /**
   * Update charge thresholds.
   * @param {number} min  Minimum charge % (0–99)
   * @param {number} max  Maximum charge % (1–100, must be > min)
   * @returns {Promise<{ ok: boolean }>}
   */
  setThresholds: (min, max) =>
    ipcRenderer.invoke("battery:set-thresholds", { min, max }),

  /** Stop charging immediately. @returns {Promise<{ ok: boolean }>} */
  stopCharging: () => ipcRenderer.invoke("battery:stop-charging"),

  /** Resume charging immediately. @returns {Promise<{ ok: boolean }>} */
  startCharging: () => ipcRenderer.invoke("battery:start-charging"),

  /**
   * Get runtime configuration from the main process.
   * @returns {Promise<{ platform: string, pythonRunning: boolean }>}
   */
  getConfig: () => ipcRenderer.invoke("battery:get-config"),

  /**
   * Register a callback that fires whenever a new snapshot is pushed
   * from the Python backend.
   * @param {function(BatterySnapshot): void} callback
   * @returns {function(): void} Unsubscribe function
   */
  onSnapshotUpdate: (callback) => {
    const listener = (_event, snapshot) => callback(snapshot);
    ipcRenderer.on("battery:snapshot-update", listener);
    // Return an unsubscribe handle so the renderer can clean up
    return () => ipcRenderer.removeListener("battery:snapshot-update", listener);
  },
});
