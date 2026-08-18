"""Quick validation of all 19 NeuroShell extension modules."""
import sys

sys.path.insert(0, ".")

from extensions.agent_mode import AutonomousAgent, SmartErrorRecovery
from extensions.desktop_features import (
    CommandPalette,
    DiffPreview,
    NotebookMode,
    SmartAutocomplete,
    SnippetManager,
    ThemeEngine,
)
from extensions.enterprise import AuditTrail, VulnerabilityScanner, WorkflowEngine
from extensions.platform_features import MachineSync, NeuroShellAPI, SmartNotifications, VoiceCommandEngine
from extensions.session_memory import SessionMemory
from extensions.smart_intel import detect_project, explain_command, score_risk

agent = AutonomousAgent()
plan = agent.plan("set up a django project called mysite")
print(f"1. Agent Mode:        {len(plan.steps)} steps planned")

recovery = SmartErrorRecovery(is_windows=True)
fix = recovery.diagnose("pip install x", "ModuleNotFoundError: No module named flask", 1)
print(f"2. Error Recovery:    fix = {fix}")

mem = SessionMemory()
print(f"3. Session Memory:    {mem.get_stats()['total_entries']} entries")

info = explain_command("chmod 755 script.sh")
print(f"4. Live Explainer:    {info['description']} -> {len(info['details'])} details")

risk = score_risk("rm -rf /")
print(f"5. Risk Scoring:      {risk.badge} ({risk.score}/10)")

ctx = detect_project(".")
print(f"6. Project Context:   {ctx.project_type if ctx else 'none'} detected")

wf = WorkflowEngine()
task = wf.parse("every day at 9 run git pull")
print(f"7. Workflow Engine:   cron = {task.cron_expression}")

scanner = VulnerabilityScanner()
scans = scanner.get_scan_commands(".")
print(f"8. Vuln Scanner:      {len(scans)} checks available")

audit = AuditTrail()
print(f"9. Audit Trail:       role={audit.get_stats()['role']}")

palette = CommandPalette()
results = palette.search("docker")
print(f"10. Command Palette:  {palette.count} cmds, {len(results)} matched docker")

snippets = SnippetManager()
print(f"11. Snippet Manager:  {len(snippets.list_all())} snippets")

themes = ThemeEngine()
print(f"12. Theme Engine:     {len(themes.list_themes())} themes ({themes.current_name})")

nb = NotebookMode()
nb.add_command("echo hello", "hello", 0, 5)
nb.add_note("Test note")
print(f"13. Notebook Mode:    {len(nb.cells)} cells")

diff = DiffPreview()
preview = diff.get_preview("rm -rf temp/")
print(f"14. Diff Preview:     {preview[1] if preview else 'none'}")

ac = SmartAutocomplete()
completions = ac.complete("git ")
print(f"15. Autocomplete:     {len(completions)} suggestions")

voice = VoiceCommandEngine()
print(f"16. Voice Command:    available={voice.available}")

notif = SmartNotifications()
print(f"17. Notifications:    threshold={notif._threshold_ms}ms")

api = NeuroShellAPI()
print(f"18. REST API:         port={api.port}")

sync = MachineSync()
print("19. Machine Sync:     ready")

print("\n=== ALL 19 MODULES LOADED SUCCESSFULLY ===")
