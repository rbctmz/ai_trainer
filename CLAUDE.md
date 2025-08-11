# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered personal endurance training coach project that integrates with Garmin Connect to provide personalized training recommendations. The project is built using Python with Streamlit for the web interface.

## Architecture and Structure

Based on the development plan, the project follows this structure:

```
ai_trainer/
├── app.py                 # Main Streamlit application
├── config/
│   ├── __init__.py
│   └── settings.py        # Configuration and constants
├── data/
│   ├── __init__.py
│   ├── garmin_client.py   # Garmin Connect API integration
│   ├── data_processor.py  # Activity data processing
│   └── database.py        # SQLite database operations
├── models/
│   ├── __init__.py
│   ├── banister.py        # Banister fitness/fatigue model
│   ├── hrv_analyzer.py    # Heart Rate Variability analysis
│   ├── ai_providers.py    # Universal AI provider architecture
│   └── ai_coach_universal.py # Universal AI coaching system
├── utils/
│   ├── __init__.py
│   ├── metrics.py         # Training metrics calculations (TSS, NP, etc.)
│   └── visualizations.py  # Plotly visualization functions
├── tests/                 # Test files
├── debug/                 # Debug scripts
├── examples/              # Demo and example scripts
├── docs/                  # Documentation files
├── requirements.txt
└── .env                   # Environment variables
```

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python -m venv ai_trainer_env

# Activate environment
source ai_trainer_env/bin/activate  # Linux/Mac
# ai_trainer_env\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Start the Streamlit application
streamlit run app.py
```

### Testing
```bash
# Run all tests
python -m pytest tests/

# Run specific test files
python tests/test_ai_coach.py
python tests/test_provider_features.py

# Run debug scripts
python debug/debug_ollama.py

# Run examples
python examples/demo_ai_features.py
```

## Key Dependencies

- **streamlit**: Web interface framework
- **pandas**: Data manipulation and analysis  
- **numpy**: Numerical computations
- **scipy**: Scientific computing (optimization, signal processing)
- **plotly**: Interactive visualizations
- **garminconnect**: Garmin Connect API client
- **python-fitparse**: FIT file parsing
- **pyhrv**: Heart rate variability analysis
- **scikit-learn**: Machine learning algorithms
- **openai**: OpenAI API integration
- **anthropic**: Anthropic Claude API integration  
- **google-generativeai**: Google Gemini API integration
- **ollama**: Local AI model integration
- **sqlalchemy**: Database ORM

## Core Components

### Garmin Integration
- Authentication with Garmin Connect credentials
- Automatic activity synchronization
- HRV and sleep data retrieval
- Activity details and metrics extraction

### Training Models
- **Banister Model**: Fitness and fatigue prediction using exponential averages
- **HRV Analysis**: Recovery assessment using RMSSD and DFA α1
- **Training Metrics**: TSS, NP, CTL, ATL, TSB calculations

### Universal AI Coaching
- Multi-provider architecture supporting OpenAI, Anthropic, Google, Ollama
- Automatic provider selection and fallback
- Personalized training analysis and recommendations
- Weekly planning with goal-based customization
- Workout-specific analysis and guidance
- Metrics explanation in simple language
- Context-aware question answering

### Data Storage
- SQLite database for local data caching
- Activity data persistence
- User settings and preferences
- HRV tracking history

## Environment Variables

Required variables in `.env`:

**AI Providers (choose one or more):**
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic Claude API key  
- `GOOGLE_API_KEY`: Google AI Studio API key
- `OLLAMA_HOST`: Ollama server URL (default: http://localhost:11434)
- `DEFAULT_AI_PROVIDER`: Preferred provider (openai, anthropic, google, ollama)

**Garmin Connect:**
- `GARMIN_EMAIL`: Garmin Connect email (optional - can be entered in UI)
- `GARMIN_PASSWORD`: Garmin Connect password (optional - can be entered in UI)

**User Settings:**
- `USER_FTP`: Functional Threshold Power (default: 250W)
- `USER_LTHR`: Lactate Threshold Heart Rate (default: 170 bpm)
- `USER_MAX_HR`: Maximum Heart Rate (default: 185 bpm)

## Key Features

1. **Training Dashboard**: Overview of recent activities, metrics, and trends
2. **Activity Analysis**: Detailed breakdown of individual workouts
3. **HRV Monitoring**: Recovery tracking and threshold estimation
4. **Performance Modeling**: Banister model for fitness/fatigue balance
5. **Universal AI Coaching**: Multi-provider AI system with personalized recommendations, planning, and education
6. **Data Synchronization**: Automatic Garmin Connect integration

## Development Notes

- The project uses metric units (km, minutes, watts, bpm)
- Training Stress Score (TSS) is central to the fitness modeling
- HRV analysis focuses on RMSSD and DFA α1 metrics
- Universal AI architecture allows switching between providers seamlessly
- AI coaching prompts are optimized for endurance training context
- Provider factory pattern enables easy addition of new AI services
- All user data is stored locally in SQLite database

## Troubleshooting

### AI Provider Issues
- **Provider shows as ❌**: Check API key in `.env` file
- **Slow responses**: Try faster models (GPT-3.5, Claude-haiku) or local Ollama
- **Google protobuf error**: Run `pip install protobuf==4.24.0`
- **Ollama connection**: Ensure `ollama serve` is running

### Common Commands for Problems
```bash
# Install missing AI libraries
pip install anthropic google-generativeai ollama

# Fix Google Gemini protobuf conflicts:
# Quick fix - use the launch script
./run.sh

# Or set environment variable before running
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
streamlit run app.py

# For permanent fix
./setup_env.sh

# Reset environment if needed
rm -rf ai_trainer_env && python -m venv ai_trainer_env

# Check Ollama status
ollama list
ollama pull llama2

# Run dependency fixes automatically
python3 fix_dependencies.py
```

### Data Issues
- **Empty dashboard**: Sync with Garmin Connect first
- **Date parsing errors**: Check `CLAUDE.md` for date handling patterns
- **Duplicate TSS entries**: Banister model automatically handles via groupby