import os, subprocess, sys
from pathlib import Path
root = Path('/private/tmp/ai-trainer-daily-fix-20261001')
source = Path('/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer')
python = '/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python'
env = {
'PATH': '/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
'HOME': '/Users/gregkisel', 'TMPDIR': str(root / 'runtime'),
'PYTHONPATH': str(root / 'guard') + ':' + str(source),
'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
'DATABASE_PATH': str(root / 'runtime/default.db'), 'DEMO_DATABASE_PATH': str(root / 'runtime/demo.db'),
'CHATS_DIR': str(root / 'runtime/chats'), 'DEFAULT_AI_PROVIDER': 'mock',
'GARMIN_EMAIL': '', 'GARMIN_PASSWORD': '', 'INTERVALS_ICU_API_KEY': '',
'OPENAI_API_KEY': '', 'ANTHROPIC_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'GOOGLE_API_KEY': '',
'PRIMARY_ACTIVITY_SOURCE':'intervals', 'PRIMARY_WELLNESS_SOURCE':'intervals',
'ATHLETE_TIMEZONE':'Europe/Moscow', 'TZ':'Europe/Moscow',
'NEXT_TELEMETRY_DISABLED': '1', 'NEXT_PUBLIC_SHOW_DEV_TOOLS': 'false',
'TODAY_UI_SCREENSHOTS': str(root / 'evidence/screenshots'),
}
args = sys.argv[1:]
if args[0] == 'pytest':
    command = [python, '-m', 'pytest', '-p', 'no:cacheprovider', *args[1:]]
elif args[0] == 'python':
    command = [python, *args[1:]]
else:
    command = args
raise SystemExit(subprocess.call(command, cwd=source, env=env))
