import sys, json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
detection  = json.loads(Path('.graphify_detect.json').read_text())
analysis   = json.loads(Path('.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

labels = {}
for k, v in analysis['communities'].items():
    v_str = ' '.join(v[:10]).lower()
    if 'claw' in v_str: labels[int(k)] = "Claw CLI Commands"
    elif 'auth' in v_str and 'key' in v_str: labels[int(k)] = "Authentication Flow"
    elif 'auth' in v_str and 'login' in v_str: labels[int(k)] = "Login Flow"
    elif 'cli_output' in v_str or 'color' in v_str: labels[int(k)] = "CLI Output & Colors"
    elif 'backup' in v_str or 'snapshot' in v_str: labels[int(k)] = "Backup & Snapshots"
    elif 'codex' in v_str or 'model' in v_str: labels[int(k)] = "Model Management"
    elif 'banner' in v_str: labels[int(k)] = "CLI Banner Display"
    elif 'debug' in v_str or 'dump' in v_str: labels[int(k)] = "Debug & Telemetry"
    elif 'skills' in v_str: labels[int(k)] = "Skills Management"
    elif 'plugin' in v_str: labels[int(k)] = "Plugin Context"
    elif 'clipboard' in v_str: labels[int(k)] = "Clipboard Utilities"
    elif 'webhook' in v_str: labels[int(k)] = "Webhooks"
    elif 'doctor' in v_str: labels[int(k)] = "Doctor Diagnostic"
    elif 'nous' in v_str: labels[int(k)] = "Nous Subscription"
    elif 'uninstall' in v_str: labels[int(k)] = "Uninstaller"
    elif 'pairing' in v_str: labels[int(k)] = "Pairing Commands"
    elif 'env' in v_str: labels[int(k)] = "Environment Loader"
    elif 'tips' in v_str: labels[int(k)] = "Tips Display"
    elif 'soul' in v_str: labels[int(k)] = "Default Soul"
    elif 'command' in v_str: labels[int(k)] = "Command Lookup"
    else: labels[int(k)] = "Misc Components"

questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, '/Users/sss/devprog/devprog_sss/AI_prog/AI_Agents/hermes-agent/hermes_cli', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
Path('.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}))
print('Report updated with community labels')