# CP/AA Relay & Trace Integration for Plugbot

This folder contains two modules that plug into the Plugbot test automation framework (`can_bus_tool`) to drive a CarPlay / Android Auto HIL test bench:

| File | Role |
|------|------|
| `oem_custom_hu_state_manager.py` | Custom **HU State Manager** (registered as `oem`). Translates Plugbot's ignition requests (IGN_ON, warm/cold IGN_OFF) into key-press pulses on a USB relay board. |
| `esoTraceLogger_ubuntu.py` | **Trace logger**. Starts and stops `jTraceCapture` sessions (SYS, IVI, ConMod partitions) in sync with each test loop. It is called by the state manager. |

Both files live in:

```
plugbot/lib/python3.12/site-packages/can_bus_tool/
```

They are imported by Plugbot at runtime, so they must sit in the same package directory as `base_hu_state_manager`.

---

## 1. Architecture

```
 Plugbot (python -m plugbot wireless ...)
          │
          │  --can_manager=oem
          ▼
 HuStateManagerOem  (oem_custom_hu_state_manager.py)
          │                         │
          │ usbrelay QAAMZ_1/2      │ start_traces() / stop_traces()
          ▼                         ▼
 USB relay board  ──► HU KL15    esoTraceLogger_ubuntu.py
 (ignition button)   (head unit)     │
                                     ├─ lxterminal → java -jar jtracecapture.jar  (SYS, port 21005)
                                     ├─ lxterminal → java -jar jtracecapture.jar  (IVI, port 21002)
                                     └─ lxterminal → start_conmod.sh
                                                     (adb forward + jtracecapture, ConMod)
```

---

## 2. `oem_custom_hu_state_manager.py`

### 2.1 Purpose

Plugbot's CAN-bus tooling expects an *HU state manager* that can switch the head unit between ignition states. This class implements that interface for a bench where the ignition is simulated by pressing the head unit's power button through a relay. No CAN message is sent by this module.

### 2.2 Hardware

- **Relay board:** USBB-Relay04, serial `QAAMZ`, controlled with the `usbrelay` command-line tool.
- **Channels:** `QAAMZ_1` and `QAAMZ_2`. Both are closed together to simulate a press of the power button (ZAT1 and ZAT2 are shorted to ground).

### 2.3 Class `HuStateManagerOem`

Registered with `@BaseHuStateManager.register("oem")`, so it is selected with `--can_manager=oem`.

**State attributes**

| Attribute | Meaning |
|-----------|---------|
| `is_ign_on` | Virtual ignition state (`True` = ON). |
| `proveniente_da_cold_boot` | Set to `True` after a cold OFF. The next IGN_ON then uses the double-impulse sequence. |

**Methods**

| Method | Behaviour |
|--------|-----------|
| `_invia_impulso_pulsante()` | Closes both relays, waits **0.3 s** (a "finger tap"), then opens them. Errors from `usbrelay` are logged and not raised. |
| `setup()` | Forces both relays open and sets `is_ign_on = False`. Plugbot requires the HU to start OFF. Returns `SUCCESS` or `ERROR`. |
| `teardown()` | Stops the jTrace captures, resets the trace loop counter, then calls `setup()`. |
| `ign_on()` | If the HU is off: sends one pulse (warm start), or two pulses separated by **1.5 s** if coming from a cold boot. Then starts the traces. If already on, does nothing. |
| `warm_ign_off()` | Sends one pulse to turn the HU off. Stops the traces. Clears the cold-boot flag. |
| `cold_ign_off()` | Sends one pulse to turn the HU off, stops the traces, sets the cold-boot flag, then **waits 5 minutes** so the HU can enter Suspend-to-RAM / deep sleep before the next test. |

### 2.4 Ignition sequences

```
IGN_ON (warm)        : [pulse 0.3 s]
IGN_ON (after cold)  : [pulse 0.3 s] → wait 1.5 s → [pulse 0.3 s]
WARM_IGN_OFF         : [pulse 0.3 s]
COLD_IGN_OFF         : [pulse 0.3 s] → wait 5 min
```

The double pulse after a cold boot wakes the PMIC / SoC from standby first, and the second pulse then powers up the infotainment.

### 2.5 Logging

Standard Python `logging` is used. The module logs at `DEBUG` and `INFO`, and errors from `usbrelay` are logged at `ERROR`. The jTrace integration is optional: if `esoTraceLogger_ubuntu` cannot be imported, the class still works and the traces are simply not started.

---

## 3. `esoTraceLogger_ubuntu.py`

### 3.1 Purpose

Runs three `jTraceCapture` (esoTrace) acquisitions in parallel for each test loop, each in its own `lxterminal` window:

| Job | Target | Port | Output file |
|-----|--------|------|-------------|
| SYS | `172.16.250.248` | 21005 | `traceSYS_Loop_<n>.esotrace_<timestamp>` |
| IVI | `172.16.250.248` | 21002 | `traceIVI_Loop_<n>.esotrace_<timestamp>` |
| ConMod | `127.0.0.1` (via `adb forward`) | 21002 | `traceConMod_Loop_<n>.esotrace_<timestamp>` |

The `#yyyyMMddhhmm#` token is expanded by jTraceCapture when the file is created.

### 3.2 Configuration and hardcoded values

> ⚠️ **Verify before running.** The values below are hardcoded for one specific machine and bench. They are not read from the environment or from a config file. If you run the bench on another machine, with another head unit, or with another USB device, check every item in this table first. A wrong value does not always produce a clear error: for example, a wrong `ADB_SERIAL` makes the ConMod window wait forever, and a wrong IP produces empty trace files.

| Constant / location | Current value | Where it is used | What to check |
|---------------------|---------------|------------------|---------------|
| `JTRACE_DIR` | `/home/emanuele/Downloads/Plugbot_tracing` | `_preflight_ok()`, `start_traces()` | Folder exists and contains `jtracecapture.jar`. |
| `OUTPUT_DIR` | `/home/emanuele/Downloads/Plugbot_tracing` | Trace output, `start_conmod.sh`, `lxterminal` working directory | Folder is writable by the user running the bench. |
| `JAR_NAME` | `jtracecapture.jar` | Preflight check, launch command, `pkill` pattern | Name matches the file actually in `JTRACE_DIR`. |
| `ADB_SERIAL` | `352425160185727` | ConMod `adb -s ... forward` in `start_conmod.sh` | Matches the output of `adb devices` for the device in use. |
| `ADB_PORT` | `21002` | ConMod port forward and jTraceCapture port | Not in conflict with another service on the Pi. |
| HU IP in `_JOBS` | `172.16.250.248` | SYS and IVI jTraceCapture targets | Matches the head unit's current IP (also `--hu_serial` in the Plugbot command). |
| SYS / IVI ports in `_JOBS` | `21005` / `21002` | SYS and IVI jTraceCapture | Match the trace ports configured on the head unit. |
| `ConMod` target | `127.0.0.1` | `start_conmod.sh` | Should stay `127.0.0.1` (traffic goes through `adb forward`). |

Other hardcoded values outside this file that must also be checked before a run:

| Location | Value | Why it matters |
|----------|-------|----------------|
| `oem_custom_hu_state_manager.py` | Relay channels `QAAMZ_1`, `QAAMZ_2` | Must match the USB relay board's channel names (`usbrelay` lists them). |
| Plugbot launch command (`--bluetooth_address`, `--device_serial`, `--hu_serial`) | `94:45:60:28:95:87`, `3B020DLJH001ZN`, `172.16.250.248:5555` | Must match the devices on the bench. |
| Plugbot launch command (`PYTHONPATH`, venv path) | Paths under `~/Documenti/Plugbot3_11_05_2025/` and `python3.12` site-packages | Must match the actual venv and its Python version. |
| Plugbot launch command (`--log_dir`, `-o`, `known_failures.json`) | `/home/emanuele/Downloads/Logs/out`, `<path>/known_failures.json` | Folders must exist and be writable. |

### 3.3 Prerequisites (checked by `_preflight_ok()`)

- `java` available in `PATH` (for example `sudo apt install default-jdk`).
- `jtracecapture.jar` present in `JTRACE_DIR`.
- `lxterminal` installed. It needs a running X/desktop session (`DISPLAY` set).

If any check fails, a message is logged and the test runs without traces.

### 3.4 Functions

| Function | Behaviour |
|----------|-----------|
| `start_traces(loop=None)` | Skips if a `jtracecapture` process is still running (checked with `pgrep`). Otherwise checks prerequisites, computes the loop tag (`Loop_N`), opens one `lxterminal` per SYS and IVI job, and one for ConMod using `start_conmod.sh`. The window titles are remembered so they can be closed later. |
| `stop_traces()` | Kills `start_conmod.sh` loops and all `jtracecapture.jar` processes (`pkill`), waits 1 s, closes the remembered windows with `wmctrl -c`, and clears the internal lists. |
| `_traces_running()` | Returns `True` if at least one `jtracecapture` process is alive (`pgrep -f`). |
| `_get_next_loop_tag(custom_loop=None)` | Increments an in-memory counter and returns `Loop_N`. |
| `reset_loop_counter()` | Sets the counter back to 0. Called from `teardown()`. |
| `_create_conmod_script(jar_path, loop_tag)` | Writes `start_conmod.sh` into `OUTPUT_DIR`. The script waits in a loop until `adb forward tcp:21002 tcp:21002` succeeds, then runs jTraceCapture with `-k 150`. |

**Window lifecycle:** each `lxterminal` runs its command directly and closes when that command ends. When a capture is stopped, its window closes automatically. `wmctrl` is only a fallback for windows that are still open.

### 3.5 ConMod details

The ConMod partition is reached through ADB, not over the network. The generated script:

1. Retries `adb -s <ADB_SERIAL> forward tcp:21002 tcp:21002` once per second until the device is present.
2. Starts jTraceCapture against `127.0.0.1:21002`.

The `-k 150` option is passed through to jTraceCapture unchanged. Check the jTraceCapture documentation for its exact meaning.

### 3.6 Loop numbering

The counter is incremented on every `start_traces()` call, so each IGN_ON produces a new `Loop_N` tag. The counter is reset in `teardown()`, so numbering restarts from `Loop_1` in the next Plugbot session.

---

## 4. Running the tests

The launch sequence is kept in a text file. In short:

**1. Activate the virtual environment**

```bash
cd ~/Documenti/Plugbot3_11_05_2025/Plugbot3_11_05_2025
source plugbot/bin/activate
```

**2. Run Plugbot with logging**

```bash
script -c 'export PYTHONPATH=<site-packages paths> && <venv>/bin/python3 -m plugbot wireless \
  --bluetooth_address=94:45:60:28:95:87 \
  --verbosity=1 \
  --connection_switch_method=can_bus_controller \
  --can_manager=oem \
  --device_serial=3B020DLJH001ZN \
  --hu_serial=172.16.250.248:5555 \
  --label_external_known_failures=<path>/known_failures.json \
  --log_dir=/home/emanuele/Downloads/Logs/out \
  -o /home/emanuele/Downloads/Logs/out' \
  /home/emanuele/Downloads/Logs/out/plugbot.log
```

Key flags:

| Flag | Effect |
|------|--------|
| `--can_manager=oem` | Loads `HuStateManagerOem` from this folder. |
| `--connection_switch_method=can_bus_controller` | Plugbot's connection switching method for the HU. |
| `--hu_serial=172.16.250.248:5555` | ADB-over-network target for the head unit. |
| `--log_dir` / `-o` | Output directory for Plugbot logs and results. |

`script` records the full terminal session to `plugbot.log`.

---

## 5. Output

Each test run produces:

- `jTraceCapture` files in `Plugbot_tracing/`, named by partition and loop (`traceSYS_Loop_1...`, `traceIVI_Loop_1...`, `traceConMod_Loop_1...`).
- `start_conmod.sh` in `Plugbot_tracing/`, regenerated for each loop.
- Plugbot logs in `--log_dir`.
- Error messages from `usbrelay` and the trace logger, printed to the console and the logging output.

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Error during send of the impulse` | `usbrelay` not installed, relay not connected, or missing udev permissions. |
| `esoTrace: 'java' non trovato` | Java not installed. |
| `esoTrace: jtracecapture.jar non trovato` | Jar not copied into `JTRACE_DIR`. |
| `esoTrace: 'lxterminal' non trovato` | Terminal emulator missing, or no DISPLAY (run from a desktop session). |
| Trace windows open but empty | Head unit not reachable at `172.16.250.248` (check the network). |
| Trace window closes immediately | jTraceCapture exited with an error (wrong IP, port, or jar path). Run the command manually in a terminal to see the message. |
| ConMod never starts | ADB device `ADB_SERIAL` not connected, or the USB serial has changed. |

---

## 7. Known limitations

- `cold_ign_off()` blocks for 5 minutes. The fixed wait is commented out in favour of a per-minute loop.
- Paths, IP addresses and ADB serials are hardcoded (see section 3.2). Moving the bench to another machine requires editing the constants and checking the list above.
- Trace windows close when their capture ends. `wmctrl` is used only as a fallback, so it is optional. Without it, a window that did not close by itself stays open until closed by hand.
