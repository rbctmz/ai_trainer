# 🧪 Tests Directory

This directory contains all test files for the AI Trainer project.

## Structure

- `test_*.py` - Unit and integration tests
- `debug_*.py` - Debugging scripts for specific components
- `add_*.py` - Scripts for adding test data
- `clean_*.py` - Database cleanup utilities

## Running Tests

From the project root:

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python tests/test_ai_providers.py

# Debug specific component
python tests/debug_hrv.py
```

## Important Notes

⚠️ **ALWAYS create test files in this directory, NOT in the project root!**

When creating new test files:
1. Place them in the `tests/` directory
2. Use descriptive names: `test_<component>.py`
3. Add sys.path manipulation if needed to import project modules:

```python
import sys
sys.path.append('..')  # Add parent directory to path
```