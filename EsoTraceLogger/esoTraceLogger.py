import subprocess
import time

_processes = []

def start_traces():
    global _processes
    
    #Avoid opening more windows if already present
    if any(p.poll() is None for p in _processes):
        print("Traces already active")
        return
    _processes.clear()
    
    workdir = "/home/connectivity/python/CP_AA_loop_test-main/jtrace"

    jobs = [
        ("SYS",   "java -jar jtracecapture.jar -o traceSYS.esotrace_#yyyyMMddhhmm# 172.16.250.248 -p 21005"),
        ("IVI",   "java -jar jtracecapture.jar -o traceIVI.esotrace_#yyyyMMddhhmm# 172.16.250.248 -p 21002"),
        #("ConMod", "java -jar jtracecapture.jar -o traceConMod.esotrace_#yyyyMMddhhmm# 127.0.0.1 -p 21002 -k 150")
    ]
    #subprocess.run(["adb","connect","172.16.250.248:5555"], check = True)
    #subprocess.run(["adb","-s","352425160194968","forward","tcp:21002","tcp:21002"], check=True)

    for title, cmd in jobs:
        p = subprocess.Popen(
            [
                "lxterminal",
                "--title", title,
                "--command",
                f"bash -c 'cd {workdir} && {cmd}; exec bash'"
            ],
            cwd=workdir
        )
        _processes.append(p)
        
def stop_traces():
    
    subprocess.run(
        ["pkill", "-f", "jtracecapture.jar"],
        check=False
    )
    time.sleep(1)
    
    for title in ["SYS","IVI"]:
        subprocess.run(
        ["wmctrl", "-c", title],
        check =False
    )
    _processes.clear()
    
    #Remove ADB forward
    #subprocess.run(
    #    ["adb","forward","--remove","tcp:21002"],
    #   check = false
    #)
    
    
