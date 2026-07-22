# MIRA

MIRA (Model Inference and Response Annotation) is a multipage Streamlit workspace for comparing model responses, recording structured human ratings, editing final responses, and resuming saved review projects.

## Project structure

- `app.py`: pages, review workflow, navigation, and project persistence
- `mira_data.py`: upload parsing, rating columns, and data normalization
- `mira_theme.py`: shared visual theme and embedded presentation assets
- `.streamlit/config.toml`: non-secret Streamlit configuration
- `.streamlit/secrets.toml.example`: authentication configuration template

## Local setup

Use Python 3.12 or newer; Python 3.9 is end-of-life and cannot resolve the hardened dependency set.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
.venv/bin/python -m streamlit run app.py
```

Fill `.streamlit/secrets.toml` with the Google OAuth web-client values. For deployment, enter these values in Streamlit Community Cloud under **App settings → Secrets**. Never commit the real secrets file, OAuth client JSON, uploaded datasets, autosaves, or private keys.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m py_compile app.py mira_data.py mira_theme.py
.venv/bin/python -m bandit -r app.py mira_data.py mira_theme.py
```

Install development checks with `pip install -r requirements-dev.txt`.
