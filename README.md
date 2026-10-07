# Global Focus (Study Guard v2) 🛡️

AI-powered focus app that keeps you on-task across any browser or Windows application. Uses the **Jev (TypeSafe)** decision model via OpenRouter to evaluate active foreground windows in real-time, redirecting distractions to motivational interstitials and logging long-term analytics into SQLite.

---

## ✨ Features

- **Cross-App & Cross-Browser Monitoring**: Evaluates active window titles (Chrome, Edge, Firefox, Brave, IDEs, desktop EXEs).
- **Jev AI Classification**: Real-time System One decisions (on_task, 	ransitioning, distracted) powered by OpenRouter without hallucination.
- **Smart Navigation Handling**: Neutral navigation points (e.g. YouTube homepage, Google search, new tabs, File Explorer) are treated as transitioning and never blocked.
- **Dual Guarding Modes**:
  - **🛑 Block Mode**: Distracting browser tabs get seamlessly redirected to a local motivational interstitial quote (/blocked); non-browser apps get minimized.
  - **👁️ Observer Mode**: Silently monitors and categorizes study time without interrupting.
- **Reusable Categories / Classes**: Define your study subjects once (DBMS, OS, CAO, Coding & Dev, etc.) and start sessions with a click.
- **Long-Term Analytics (SQLite)**: Tracks lifetime study time, session logs, and category breakdowns.
- **Tamper-Evident HMAC Hash Chain**: Built-in cryptographic hash chain validates that local database entries haven't been manually forged or altered.
- **Optional Guardian Reports**: Optional email reports sent via SMTP (e.g., Gmail App Password) with weekly study statistics and integrity verification stamps.
- **Modern HTML5 Web UI**: Dark-themed dashboard built with Vanilla JS and Chart.js, served locally via Flask with system tray docking.

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.10+ on Windows
- An [OpenRouter API Key](https://openrouter.ai/settings/keys)

### 2. Install Dependencies
`ash
pip install -r requirements.txt
`

### 3. Configure API Key
When you launch the app for the first time, navigate to the **Settings** tab and paste your OpenRouter API key, or create/edit config.json in the root folder:
`json
{
  "ApiKey": "sk-or-v1-your-key-here"
}
`

### 4. Run Study Guard
Run the batch launcher:
`at
START_STUDY_GUARD.bat
`
Or run directly via python:
`ash
python app.py
`
The dashboard will open automatically in your browser at http://localhost:7432.