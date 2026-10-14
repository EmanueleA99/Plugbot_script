"""Custom HU State Manager per la scheda USBB-Relay04 (Seriale: QAAMZ).

Gestisce il KL15 ad impulsi per i test PCTS di Android Auto.
"""

import logging
import subprocess
import time
from can_bus_tool import base_hu_state_manager

# Import del modulo logger
try:
    import esoTraceLogger_ubuntu as esotrace
except ImportError:
    esotrace = None
    logging.warning("Modulo esoTraceLogger_ubuntu non trovato. I log non partiranno.")


@base_hu_state_manager.BaseHuStateManager.register("oem")
class HuStateManagerOem(base_hu_state_manager.BaseHuStateManager):
    """Gestisce gli stati dell'Head Unit simulando impulsi sul tasto KL15."""

    def __init__(self):
        super().__init__()
        self.relay_1 = "QAAMZ_1"
        self.relay_2 = "QAAMZ_2"
        # Teniamo traccia dello stato virtuale del quadro (True = Acceso, False = Spento)
        self.is_ign_on = False
        # Flag per tracciare se veniamo da un cold boot profondo
        self.proveniente_da_cold_boot = False

    def _invia_impulso_pulsante(self):
        """Simula la pressione e il rilascio rapido del pulsante di accensione."""
        try:
            # 1. Premi il pulsante (Chiudi i relè portando a massa ZAT1 e ZAT2)
            cmd_on = f"usbrelay {self.relay_1}=1 {self.relay_2}=1"
            subprocess.check_output(cmd_on, shell=True, stderr=subprocess.STDOUT)

            # 2. Mantieni premuto per 300 millisecondi (tempo tipico di un "tap" col dito)
            time.sleep(0.3)

            # 3. Rilascia il pulsante (Riapri i relè togliendo la massa)
            cmd_off = f"usbrelay {self.relay_1}=0 {self.relay_2}=0"
            subprocess.check_output(cmd_off, shell=True, stderr=subprocess.STDOUT)

            logging.debug("KL15 signal send with success")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during send of the impulse: {e.output.decode('utf-8')}")

    def setup(self) -> int:
        """Configura il manager prima dei test."""
        logging.info("Startup: Check relè open.")
        try:
            cmd = f"usbrelay {self.relay_1}=0 {self.relay_2}=0"
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            # NOTA: All'avvio dei test PCTS, il framework richiede che l'HU parta da spenta.
            self.is_ign_on = False
            return base_hu_state_manager.SUCCESS
        except subprocess.CalledProcessError:
            return base_hu_state_manager.ERROR

    def teardown(self) -> int:
        """Ripristina lo stato iniziale rilasciando i relè."""
        logging.info("Teardown of state manager.")
        if esotrace:
            esotrace.stop_traces()
            esotrace.reset_loop_counter()  # Riparte da Loop_1 alla prossima sessione
        return self.setup()

    def ign_on(self) -> int:
        """Garantisce che l'accensione sia su ON (KL15 ON)."""
        if not self.is_ign_on:
            if self.proveniente_da_cold_boot:
                logging.info("Execution IGN_ON after Cold Boot: Deep sleep detected. Double impulse sent.")

                # 1° Impulso: Sveglia il PMIC/SoC dallo standby
                logging.debug("First wake up impulse")
                self._invia_impulso_pulsante()

                # Pausa di assestamento (1.5 secondi di solito bastano per far reagire l'hardware)
                time.sleep(1.5)

                # 2° Impulso: Accensione vera e propria dell'infotainment
                logging.debug("Second wake up impulse - turned on")
                self._invia_impulso_pulsante()

                # Reset del flag
                self.proveniente_da_cold_boot = False
            else:
                logging.info("IGN_ON standard: Single impulse for TURN ON the ignition.")
                self._invia_impulso_pulsante()

            self.is_ign_on = True

            # Avvio delle acquisizioni jTrace
            if esotrace:
                esotrace.start_traces()

        else:
            logging.info("IGN_ON requested, it's already turned on. JUMP.")
        return base_hu_state_manager.SUCCESS

    def warm_ign_off(self) -> int:
        """Garantisce che l'accensione vada su OFF (Modalità WARM)."""
        if self.is_ign_on:
            logging.info("Executing WARM_IGN_OFF: Send impulse for shut off the ignition.")
            self._invia_impulso_pulsante()
            self.is_ign_on = False
            self.proveniente_da_cold_boot = False  # Non è un cold boot

            # Stop delle acquisizioni jTrace
            if esotrace:
                esotrace.stop_traces()

        else:
            logging.info("WARM_IGN_OFF requested, it's already turned OFF. JUMP.")
        return base_hu_state_manager.SUCCESS

    def cold_ign_off(self) -> int:
        """Garantisce che l'accensione vada su OFF (Modalità COLD)."""
        if self.is_ign_on:
            logging.debug("Executing COLD_IGN_OFF: Send impulse for shut off the ignition.")
            self._invia_impulso_pulsante()
            self.is_ign_on = False
            self.proveniente_da_cold_boot = True  # Segnamo che siamo in Cold Boot

            # Stop delle acquisizioni jTrace
            if esotrace:
                esotrace.stop_traces()

            MINUTI_ATTESA = 5
            # SECONDI_ATTESA = MINUTI_ATTESA * 60
            logging.debug(f"Start waiting for {MINUTI_ATTESA} minutes for Suspend to RAM...")
            for i in range(MINUTI_ATTESA, 0, -1):
                logging.debug(f"Still {i} minutes to wait...")
                time.sleep(60)
        else:
            logging.info("COLD_IGN_OFF requested, it's already turned OFF. JUMP.")

        return base_hu_state_manager.SUCCESS
