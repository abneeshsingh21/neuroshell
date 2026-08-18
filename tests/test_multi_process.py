# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License").
import pytest
import subprocess
import time
import sys


def test_concurrent_subprocesses_execution():
    """Verify that multiple concurrent subprocesses execute and finish cleanly."""
    cmds = [
        [sys.executable, "-c", "import time; time.sleep(0.1); print('Task 1 complete')"],
        [sys.executable, "-c", "import time; time.sleep(0.1); print('Task 2 complete')"],
        [sys.executable, "-c", "import time; time.sleep(0.1); print('Task 3 complete')"]
    ]
    
    start = time.time()
    procs = [subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for c in cmds]
    
    outputs = []
    for p in procs:
        stdout, _ = p.communicate()
        outputs.append(stdout.strip())
        assert p.returncode == 0
        
    duration = time.time() - start
    assert "Task 1 complete" in outputs[0]
    assert "Task 2 complete" in outputs[1]
    assert "Task 3 complete" in outputs[2]
    # Parallel duration should be roughly max of tasks (around 0.2s), far less than serial sum (0.3s+)
    assert duration < 1.0


def test_process_tree_termination():
    """Verify process teardown cleanly kills long-running tasks."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    assert proc.poll() is None
    proc.terminate()
    proc.wait(timeout=2.0)
    assert proc.poll() is not None
