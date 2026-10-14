"""
esoTraceLogger_ubuntu.py

Avvia/ferma le acquisizioni jTraceCapture (SYS, IVI, ConMod) in sincronia
con ogni ciclo di test CP/AA (deep sleep e soft boot).

NOTA: JTRACE_DIR e OUTPUT_DIR sono hardcoded per la macchina del banco.
Verificarli prima di ogni avvio (vedi README, sezione 3.2).
"""

import shutil
import subprocess
import time
from pathlib import Path

ADB_SERIAL = "352425160185727"
ADB_PORT = "21002"

# TODO: verificare prima dell'avvio - path hardcoded per la macchina del banco.
JTRACE_DIR = Path("/home/emanuele/Downloads/Plugbot_tracing")
JAR_NAME = "jtracecapture.jar"

OUTPUT_DIR = Path("/home/emanuele/Downloads/Plugbot_tracing")

_JOBS = [
    ("SYS", "java -jar {jar} -o traceSYS_{loop_tag}.esotrace_#yyyyMMddhhmm# 172.16.250.248 -p 21005"),
    ("IVI", "java -jar {jar} -o traceIVI_{loop_tag}.esotrace_#yyyyMMddhhmm# 172.16.250.248 -p 21002"),
]

_processes = []      # processi lxterminal lanciati (solo per riferimento)
_window_titles = []  # titoli delle finestre aperte, usati per chiuderle
_loop_counter = 0    # inizializzato a 0 all'avvio del processo


def _log(msg):
    print(msg)


def _get_next_loop_tag(custom_loop=None) -> str:
    """Incrementa e restituisce sempre Loop_1, Loop_2, ... in memoria."""
    global _loop_counter

    if custom_loop is not None:
        _loop_counter = custom_loop
    else:
        _loop_counter += 1

    return f"Loop_{_loop_counter}"


def reset_loop_counter():
    """Azzera il contatore dei loop (chiamato da teardown)."""
    global _loop_counter
    _loop_counter = 0


def _preflight_ok():
    """Verifica i prerequisiti prima di avviare le acquisizioni; logga cosa manca."""
    ok = True

    if shutil.which("java") is None:
        _log("esoTrace: 'java' non trovato nel PATH (installa un JRE/JDK, es. 'sudo apt install default-jdk').")
        ok = False

    if not (JTRACE_DIR / JAR_NAME).exists():
        _log(f"esoTrace: {JAR_NAME} non trovato in {JTRACE_DIR}. Copia il jar in questa cartella.")
        ok = False

    if shutil.which("lxterminal") is None:
        _log(
            "esoTrace: 'lxterminal' non trovato. Installa un emulatore di terminale grafico "
            "('sudo apt install lxterminal') e assicurati che il banco giri con una sessione "
            "desktop/X attiva (lxterminal richiede un DISPLAY)."
        )
        ok = False

    return ok


def _traces_running() -> bool:
    """True se almeno un processo jtracecapture è ancora attivo."""
    result = subprocess.run(["pgrep", "-f", JAR_NAME], capture_output=True, text=True)
    return result.returncode == 0


def _create_conmod_script(jar_path: Path, loop_tag: str) -> Path:
    """Crea lo script per ConMod inserendo il suffisso Loop_X nel file di log."""
    script_path = OUTPUT_DIR / "start_conmod.sh"
    content = (
        "#!/bin/bash\n"
        f"cd \"{OUTPUT_DIR}\"\n"
        f"echo \"[ConMod] [{loop_tag}] In attesa del device {ADB_SERIAL}...\"\n"
        f"until adb -s {ADB_SERIAL} forward tcp:{ADB_PORT} tcp:{ADB_PORT} 2>/dev/null; do\n"
        "    sleep 1\n"
        "done\n"
        f"echo \"[ConMod] Port forward tcp:{ADB_PORT} attivo! Avvio jTraceCapture...\"\n"
        f"java -jar \"{jar_path}\" -o traceConMod_{loop_tag}.esotrace_#yyyyMMddhhmm# 127.0.0.1 -p {ADB_PORT} -k 150\n"
    )
    script_path.write_text(content)
    script_path.chmod(0o755)
    return script_path


def start_traces(loop=None):
    """Avvia le acquisizioni jTraceCapture per SYS, IVI e ConMod, una per finestra lxterminal."""
    global _processes, _window_titles

    # Evita di aprire nuove finestre se ci sono ancora acquisizioni attive.
    if _traces_running():
        _log("esoTrace: tracce già attive, avvio saltato")
        return

    _processes.clear()
    _window_titles.clear()

    if not _preflight_ok():
        _log("esoTrace: avvio tracce saltato per prerequisiti mancanti (il test prosegue comunque, senza trace)")
        return

    JTRACE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    jar_path = (JTRACE_DIR / JAR_NAME).resolve()

    # Calcola il tag (es. "Loop_1", "Loop_2")
    loop_tag = _get_next_loop_tag(custom_loop=loop)
    _log(f"esoTrace: === AVVIO TRACCE [{loop_tag}] ===")

    # 1. Avvio SYS e IVI. Senza "exec bash" la finestra si chiude quando jTraceCapture termina.
    for title, cmd_template in _JOBS:
        cmd = cmd_template.format(jar=JAR_NAME, loop_tag=loop_tag)
        window_title = f"{title}_{loop_tag}"
        try:
            p = subprocess.Popen(
                [
                    "lxterminal",
                    "--title", window_title,
                    "--command",
                    f"bash -c 'cd \"{OUTPUT_DIR}\" && {cmd}'"
                ],
                cwd=str(OUTPUT_DIR)
            )
            _processes.append(p)
            _window_titles.append(window_title)
            _log(f"esoTrace: avviata acquisizione {title} ({loop_tag}) in {OUTPUT_DIR}")
        except Exception as e:
            _log(f"esoTrace: impossibile avviare acquisizione {title}: {e}")

    # 2. Avvio cattura ConMod tramite script dedicato
    conmod_script = _create_conmod_script(jar_path, loop_tag)
    conmod_title = f"ConMod_{loop_tag}"
    try:
        p_conmod = subprocess.Popen(
            [
                "lxterminal",
                "--title", conmod_title,
                "--command", f"bash \"{conmod_script}\""
            ],
            cwd=str(OUTPUT_DIR)
        )
        _processes.append(p_conmod)
        _window_titles.append(conmod_title)
        _log("esoTrace: avviata finestra ConMod con attesa connessione ADB")
    except Exception as e:
        _log(f"esoTrace: impossibile avviare acquisizione ConMod: {e}")


def stop_traces():
    """Termina tutte le acquisizioni jTraceCapture attive e chiude le relative finestre."""
    global _processes, _window_titles

    # 1. Termina eventuali loop di attesa di ConMod rimasti attivi
    try:
        subprocess.run(["pkill", "-f", "start_conmod.sh"], check=False)
    except Exception:
        pass

    # 2. Termina tutti i processi jTraceCapture
    try:
        subprocess.run(["pkill", "-f", JAR_NAME], check=False)
    except Exception as e:
        _log(f"esoTrace: errore durante pkill: {e}")

    time.sleep(1)

    # 3. Chiusura di eventuali finestre rimaste aperte (fallback, wmctrl opzionale)
    for window_title in _window_titles:
        try:
            subprocess.run(["wmctrl", "-c", window_title], check=False)
        except FileNotFoundError:
            # wmctrl non installato: le finestre si chiudono comunque da sole al termine dei processi
            pass
        except Exception as e:
            _log(f"esoTrace: errore durante chiusura finestra {window_title}: {e}")

    _processes.clear()
    _window_titles.clear()
    _log("esoTrace: acquisizioni terminate")
