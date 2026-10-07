# Global Focus 🛡️

**Global Focus (Study Guard v2)** is a Windows study companion that helps you stay focused across browsers and desktop applications. It uses the **Jev (TypeSafe)** model through OpenRouter to classify your current activity as `on_task`, `transitioning`, or `distracted`.

## Features

- **Cross-app monitoring** across Chrome, Edge, Firefox, Brave, IDEs, and other Windows applications.
- **AI activity classification** using Jev (TypeSafe) via OpenRouter.
- **Smart navigation handling** for pages like Google Search, YouTube homepage, new tabs, and File Explorer.
- **Block Mode** redirects distracting browser tabs to a local `/blocked` page and minimizes distracting applications.
- **Observer Mode** monitors activity without blocking anything.
- **Study categories** such as DBMS, OS, CAO, Coding & Development, etc.
- **SQLite analytics** for study time, sessions, and category breakdowns.
- **Tamper-evident logs** using an HMAC hash chain.
- **Optional email reports** with study statistics and integrity checks.
- **Local dashboard** built with Flask, Vanilla JS, and Chart.js.

## Setup

### Requirements

- Windows
- Python 3.10+
- [OpenRouter API Key](https://openrouter.ai/settings/keys)

### Install

```bash
pip install -r requirements.txt
```

### Configure API Key

Add your key through the **Settings** tab, or create `config.json`:

```json
{
  "ApiKey": "sk-or-v1-your-key-here"
}
```

### Run

Using the Windows launcher:

```bat
START_STUDY_GUARD.bat
```

Or directly:

```bash
python app.py
```

The dashboard will open at:

```text
http://localhost:7432
```

